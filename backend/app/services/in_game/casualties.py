from __future__ import annotations

import random

from app.models import Game, GameModelDamage, Unit
from app.services.in_game import deployment, duty_in_death, turn_record

# Wounds and destroyed models in a game. A model that loses all its wounds is
# destroyed: taken off the battlefield (its position removed), so everything
# that looks at the battlefield (coherency, sight, Engagement Range...) no
# longer sees it, and a unit with none left is gone. Only this game: the
# model stays in its list. A rule can leave a destroyed model on the
# battlefield for a while (Duty in Death - see
# app/services/in_game/duty_in_death.py): it's still there, but has no
# wounds left to lose.


def damage(game: Game) -> dict[int, GameModelDamage]:
    # Each damaged (or destroyed) model's record, by unit model id.
    return {d.unit_model_id: d for d in game.model_damage}


def wounds_remaining(game: Game, unit: Unit) -> dict[int, int]:
    # The wounds each of the unit's models on the battlefield has left, by
    # unit model id (destroyed ones aren't there).
    placed = deployment.positions(game)
    lost = damage(game)
    return {
        m.id: m.wounds - (lost[m.id].wounds_lost if m.id in lost else 0)
        for m in unit.unit_models
        if m.id in placed and not (m.id in lost and lost[m.id].destroyed)
    }


def _lose(game: Game, unit_model, wounds: int, destroyed_by: Unit | None = None) -> None:
    # The model loses `wounds` (to none left, at most) - and if it has none
    # left, it's destroyed and taken off the battlefield (and that's recorded
    # - by `destroyed_by`'s attacks, if given; see
    # app/services/in_game/turn_record.py).
    if wounds <= 0:
        return
    record = damage(game).get(unit_model.id)
    if record is None:
        record = GameModelDamage(unit_model_id=unit_model.id, wounds_lost=0, destroyed=False)
        game.model_damage.append(record)
    record.wounds_lost = min(unit_model.wounds, record.wounds_lost + wounds)
    if record.wounds_lost >= unit_model.wounds:
        record.destroyed = True
        if unit_model.id in deployment.positions(game):
            unit = deployment.find_unit(game, unit_model.unit_id)
            if not duty_in_death.lingers(game, unit, unit_model, destroyed_by):
                _remove(game, unit, unit_model, destroyed_by)


def _remove(game: Game, unit: Unit, unit_model, destroyed_by: Unit | None) -> None:
    # Takes a destroyed model off the battlefield (and records that).
    position = deployment.positions(game)[unit_model.id]
    if len(deployment.models_on_battlefield(game, unit)) == 1:
        # The last of its unit: rules for that happen before it's removed
        # (e.g. Executioner).
        # (Imported here: battle_shock imports this module.)
        from app.services.in_game import battle_shock

        battle_shock.unit_about_to_be_destroyed(game, unit_model, destroyed_by)
    # A transport with units inside: where it was, for them to emergency
    # disembark round (see app/services/in_game/emergency.py).
    from app.services.in_game import emergency

    emergency.record_wreck(game, unit, unit_model, position)
    game.model_positions.remove(position)
    turn_record.record_destruction(game, unit_model, destroyed_by)


def remove_from_battlefield(game: Game, unit_model_id: int, destroyed_by_id: int | None) -> None:
    # Takes a model that was destroyed earlier but left on the battlefield
    # (a lingering one) off it now - destroyed by the attacks of the unit
    # `destroyed_by_id`, if any.
    unit_model = next(
        m
        for p in game.players
        for u in p.army_list.units
        for m in u.unit_models
        if m.id == unit_model_id
    )
    if unit_model.id in deployment.positions(game):
        destroyed_by = (
            deployment.find_unit(game, destroyed_by_id) if destroyed_by_id is not None else None
        )
        _remove(game, deployment.find_unit(game, unit_model.unit_id), unit_model, destroyed_by)


def mortal_fnp(unit_model) -> int | None:
    # The Feel No Pain a model uses against mortal wounds: the better of its
    # Feel No Pain and its Feel No Pain against mortal wounds, if it has
    # either.
    model = unit_model.model
    values = [v for v in (model.feel_no_pain, model.feel_no_pain_mortal) if v]
    return min(values) if values else None


def resists(unit_model) -> bool:
    # Whether the model's Feel No Pain negates one mortal wound (a D6 roll).
    fnp = mortal_fnp(unit_model)
    return fnp is not None and random.randint(1, 6) >= fnp


def mortal_wounds(game: Game, unit: Unit, wounds: int) -> list[int]:
    # The unit suffers mortal wounds, one at a time: each to a wounded model
    # if it has one, otherwise to its first model on the battlefield - and
    # what's left over goes on to the next model. Each can be negated by the
    # model's Feel No Pain (see mortal_fnp). The models destroyed.
    destroyed = []
    for _ in range(wounds):
        left = wounds_remaining(game, unit)
        if not left:
            break
        models = {m.id: m for m in unit.unit_models}
        wounded = [i for i, w in left.items() if w < models[i].wounds]
        target = models[(wounded or sorted(left))[0]]
        if resists(target):
            continue
        _lose(game, target, 1)
        if damage(game)[target.id].destroyed:
            destroyed.append(target.id)
    return destroyed


def apply_attack(
    game: Game,
    attacker: Unit,
    defender: Unit,
    defender_wounds_before: dict[int, int],
    defender_wounds_after: dict[int, int],
    attacker_damage: dict[int, int],
) -> list[int]:
    # Applies an attack's result (see app/services/combat.py): the wounds each
    # defending model lost, and the hazardous wounds each attacking model
    # took. The models destroyed, by unit model id.
    destroyed = []
    for side, losses, by in (
        (
            defender,
            {i: defender_wounds_before[i] - w for i, w in defender_wounds_after.items()},
            attacker,
        ),
        # Its own Hazardous weapons: not destroyed by an enemy.
        (attacker, attacker_damage, None),
    ):
        for unit_model in side.unit_models:
            lost = losses.get(unit_model.id, 0)
            if lost <= 0:
                continue
            _lose(game, unit_model, lost, by)
            if damage(game)[unit_model.id].destroyed:
                destroyed.append(unit_model.id)
    return destroyed
