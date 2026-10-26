from __future__ import annotations

from dataclasses import dataclass

from app.models import Game, GamePlayer, Stratagem, Unit
from app.seeds import stratagems as stratagem_seeds
from app.services.in_game import (
    battle_formations,
    charging,
    deployment,
    embarked,
    fighting,
    objectives,
    selected_objectives,
)
from app.services.list_building import enhancements as enhancement_rules

# Stratagems whose game action targets one of the player's units and does
# something on the battlefield (beyond what the combat calculator does with
# their conditions and effects). What each needs of the stratagem is in its
# faction's stratagem_rules.py ACTIONS (see stratagem_seeds.action_config):
#
# - "secure_on_destruction" (e.g. Cached Acquisition): used on a unit
#   destroyed this phase within range of an objective its player controlled
#   - that objective is secured (see app/services/in_game/objectives.py).
# - "longer_consolidation" (e.g. Priority Reclamation): used on the unit about
#   to consolidate, if it isn't within `enemy_clear` of an enemy unit - until
#   the end of the phase, it can consolidate up to `distance`, provided it
#   ends within range of one of its player's `ending_within` objectives.
# - "extra_selected_objective" (e.g. Infoslave Skull): used on a unit with a
#   `model_keywords` model and an objective within `within` of it that isn't
#   one of its player's `selection` objectives - it's one too, until the start
#   of their next Command phase (see
#   app/services/in_game/selected_objectives.py).
# - "reactive_embark" (e.g. Reactive Safeguard): used on a unit within range
#   of one of its player's `within` objectives that an enemy unit charging
#   this phase could reach with its charge roll - it embarks in one of the
#   player's `transport_keywords` TRANSPORTs it's wholly within 3" of, with
#   room for it.
#
# The objective or transport is picked from the unit's choices.

SECURE_ON_DESTRUCTION = "secure_on_destruction"
LONGER_CONSOLIDATION = "longer_consolidation"
EXTRA_SELECTED_OBJECTIVE = "extra_selected_objective"
REACTIVE_EMBARK = "reactive_embark"
ACTIONS = (SECURE_ON_DESTRUCTION, LONGER_CONSOLIDATION, EXTRA_SELECTED_OBJECTIVE, REACTIVE_EMBARK)


@dataclass
class Choice:
    # Something a stratagem's use on a unit also targets: an objective, or a
    # transport (its id, and how to tell it apart).
    id: int
    name: str


def _this_phase(game: Game, record) -> bool:
    return (
        record.battle_round == game.battle_round
        and record.turn_seat == game.turn_seat
        and record.phase == game.phase
    )


def _just_destroyed(game: Game, unit: Unit):
    # The record of the unit's destruction this phase, if it was destroyed.
    return next(
        (
            r
            for r in game.models_destroyed
            if r.unit_id == unit.id and r.unit_destroyed and _this_phase(game, r)
        ),
        None,
    )


def _charged_by(game: Game, unit: Unit) -> bool:
    # Whether an enemy unit charging this phase (its charge rolled, not yet
    # made) could reach the unit.
    for enemy in charging.charging_units(game):
        charge = charging.unit_charge(game, enemy)
        if charge is not None and not charge.completed and charging.in_reach(
            game, enemy, unit, charging.charge_roll(game, enemy)
        ):
            return True
    return False


def choices(game: Game, player: GamePlayer, stratagem: Stratagem, unit: Unit) -> list[Choice]:
    # What else the stratagem's use on the unit could target now.
    config = stratagem_seeds.action_config(stratagem.name)
    action = stratagem.game_action
    if action == SECURE_ON_DESTRUCTION:
        record = _just_destroyed(game, unit)
        if record is None:
            return []
        ids = {o.objective_id for o in record.controlled_objectives}
        return [
            Choice(o.id, selected_objectives.label(game, o))
            for o in objectives.objectives(game)
            if o.id in ids
        ]
    if action == EXTRA_SELECTED_OBJECTIVE:
        name = config.get("selection")
        taken = selected_objectives.objective_ids(game, player.seat, name)
        return [
            Choice(o.id, selected_objectives.label(game, o))
            for o in selected_objectives.within_of_model(
                game, unit, set(config.get("model_keywords", ())), config.get("within", 0.0)
            )
            if o.id not in taken
        ]
    if action == REACTIVE_EMBARK:
        keywords = set(config.get("transport_keywords", ()))
        return [
            Choice(c.id, c.faction_unit.name)
            for c in embarked.transports_in_reach(game, unit)
            if any(
                keywords <= enhancement_rules.model_keywords(c, m) for m in c.unit_models
            )
            and embarked.capacity_reason(game, unit, c) is None
        ]
    return []


def target_reason(
    game: Game, player: GamePlayer, stratagem: Stratagem, unit: Unit
) -> str | None:
    # Why the stratagem can't be used on the unit now (its owner and
    # keywords already checked), or None if it can.
    config = stratagem_seeds.action_config(stratagem.name)
    action = stratagem.game_action
    if action == SECURE_ON_DESTRUCTION:
        if _just_destroyed(game, unit) is None:
            return "it wasn't just destroyed"
        if not choices(game, player, stratagem, unit):
            return "it wasn't within range of an objective marker they controlled"
        return None
    if not deployment.models_on_battlefield(game, unit):
        return "it isn't on the battlefield"
    if action == LONGER_CONSOLIDATION:
        fight = fighting.just_fought(game)
        if fight is None or fight.unit_id != unit.id:
            return "it isn't about to consolidate"
        clear = config.get("enemy_clear", 0.0)
        if any(
            charging.distance(game, unit, enemy) <= clear + deployment.TOLERANCE
            for enemy in charging.enemy_units(game, unit)
        ):
            return f'it is within {clear:g}" of an enemy unit'
        return None
    if action == EXTRA_SELECTED_OBJECTIVE:
        if config.get("selection") not in selected_objectives.configs(game, player.seat):
            return f"they have no {config.get('selection')} objective markers"
        if not choices(game, player, stratagem, unit):
            return "no other objective marker is in range of it"
        return None
    if action == REACTIVE_EMBARK:
        if battle_formations.is_transport(unit):
            return "a TRANSPORT can't embark in another"
        if not selected_objectives.unit_within(game, unit, config.get("within")):
            return f"it isn't within range of their {config.get('within')} objective marker"
        if not _charged_by(game, unit):
            return "no enemy unit charging this phase could reach it"
        if not choices(game, player, stratagem, unit):
            return 'no transport it fits in is within 3" of every model'
        return None
    return None


def carry_out(
    game: Game, player: GamePlayer, stratagem: Stratagem, unit: Unit, choice_id: int | None
) -> None:
    # The stratagem's used on the unit (already checked it can be), with the
    # objective or transport picked.
    config = stratagem_seeds.action_config(stratagem.name)
    action = stratagem.game_action
    if action == LONGER_CONSOLIDATION:
        return
    if choice_id not in {c.id for c in choices(game, player, stratagem, unit)}:
        raise ValueError(f"{stratagem.name} needs one of its choices for that unit")
    if action == SECURE_ON_DESTRUCTION:
        objectives.secure(game, choice_id, player.seat)
    elif action == EXTRA_SELECTED_OBJECTIVE:
        selected_objectives.add_extra(game, player.seat, config["selection"], choice_id)
    elif action == REACTIVE_EMBARK:
        embarked.embark_now(game, unit, deployment.find_unit(game, choice_id))


def consolidation(game: Game, unit: Unit) -> tuple[float, str | None]:
    # How far the unit's models can consolidate this phase, and the objectives
    # it must then end within range of one of if they go further than usual
    # (None: no such stratagem was used on it).
    player = deployment.owner(game, unit)
    for use in player.stratagem_uses:
        if (
            use.stratagem.game_action == LONGER_CONSOLIDATION
            and use.target_unit_id == unit.id
            and use.battle_round == game.battle_round
            and use.turn_seat == game.turn_seat
            and use.phase == game.phase
        ):
            config = stratagem_seeds.action_config(use.stratagem.name)
            return config.get("distance", fighting.CONSOLIDATE), config.get("ending_within")
    return fighting.CONSOLIDATE, None
