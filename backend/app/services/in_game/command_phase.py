from __future__ import annotations

import random
from dataclasses import dataclass

from fastapi import HTTPException

from app.combat_rules import CommandChoice
from app.models import Game, GameCommandChoice, GameCommandHeal, Unit, UnitModel
from app.seeds import datasheet_abilities as datasheet_ability_seeds
from app.services.in_game import casualties, deployment
from app.services.in_game.battle_round import START_OF_ROUND
from app.services.in_game.deployment import TOLERANCE, gap

# The Command phase's abilities, in a game.
#
# Some abilities have their owner select one of their options in their
# Command phase (datasheet_abilities COMMAND_CHOICES - e.g. Belisarius Cawl's
# Canticles of the Omnissiah, Thulia Ghuld's Rod of the War Forge, a
# Cybernetica Datasmith's Battle Protocols). The player whose turn it is
# selects them while it's their Command phase; one that must be selected
# blocks the end of the phase until it is. The option is active until the
# start of their next Command phase - or, for a persistent one (Battle
# Protocols), until another is selected, starting as its default. While
# active, it's one of the unit's rule options when it attacks or is attacked
# (as the combat calculator's - see app/routers/combat.py), and can let a
# unit shoot and declare a charge after Advancing or Falling Back.
#
# An ability whose option applies to another unit (Rod of the War Forge: a
# SKITARII or THULIA GHULD unit within 6") has that unit selected with it -
# then the option is only that unit's.
#
# Other abilities heal a model at the start of its owner's Command phase
# (datasheet_abilities COMMAND_HEALS - e.g. Self-repair Mechanisms: D3 lost
# wounds).


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _choices_config() -> dict[str, CommandChoice]:
    return datasheet_ability_seeds.COMMAND_CHOICES


def is_command_phase(game: Game) -> bool:
    return game.status == "in_progress" and game.phase == "command"


@dataclass
class CommandAbility:
    # A unit on the battlefield with an ability whose option is selected in
    # the Command phase: the model that has it, and how it's selected.
    unit: Unit
    model: UnitModel
    ability: str
    config: CommandChoice


def command_abilities(game: Game, seat: int) -> list[CommandAbility]:
    # The player's units on the battlefield with such abilities (once per
    # unit and ability), in list order.
    player = next(p for p in game.players if p.seat == seat)
    config = _choices_config()
    found: dict[tuple[int, str], CommandAbility] = {}
    for unit in deployment.deployable_units(player):
        for unit_model in deployment.models_on_battlefield(game, unit):
            for ability in unit_model.model.abilities:
                if ability.name in config and (unit.id, ability.name) not in found:
                    found[(unit.id, ability.name)] = CommandAbility(
                        unit, unit_model, ability.name, config[ability.name]
                    )
    return list(found.values())


def options(ability: str) -> dict:
    # The ability's options: {option name: RuleOption}.
    return datasheet_ability_seeds.OPTIONS.get(ability, {})


def last_command_round(game: Game, seat: int) -> int:
    # The battle round of the player's most recent Command phase to have
    # begun (0: none yet).
    if game.turn_seat is None or game.phase == START_OF_ROUND:
        return game.battle_round - 1
    if seat == game.turn_seat or seat == game.first_seat:
        return game.battle_round
    return game.battle_round - 1


@dataclass
class ActiveChoice:
    unit_id: int
    ability: str
    option: str
    target_unit_id: int | None = None
    # Its default (a persistent ability nothing's been selected for yet).
    default: bool = False


def active_choices(game: Game, seat: int) -> list[ActiveChoice]:
    # The options active for the player's units now, one per unit and
    # ability whose model with it is on the battlefield.
    abilities = {(a.unit.id, a.ability): a for a in command_abilities(game, seat)}
    latest = last_command_round(game, seat)
    found: dict[tuple[int, str], ActiveChoice] = {}
    for choice in game.command_choices:
        key = (choice.unit_id, choice.ability)
        if choice.seat != seat or key not in abilities:
            continue
        current = (
            choice.battle_round <= latest
            if abilities[key].config.persistent
            else choice.battle_round == latest
        )
        if current:
            found[key] = ActiveChoice(
                choice.unit_id, choice.ability, choice.option, choice.target_unit_id
            )
    for key, ability in abilities.items():
        if key not in found and ability.config.persistent and ability.config.default:
            found[key] = ActiveChoice(key[0], key[1], ability.config.default, default=True)
    return list(found.values())


def _applies_to(choice: ActiveChoice, unit: Unit) -> bool:
    return choice.target_unit_id is None or choice.target_unit_id == unit.id


def options_for(game: Game, seat: int, unit: Unit) -> list[str]:
    # The active options that can apply to the unit (one that applies to
    # another unit doesn't, nor an aura - see app/services/in_game/auras.py,
    # which checks its range) - the calculator works out which it gains.
    return [
        c.option
        for c in active_choices(game, seat)
        if _applies_to(c, unit) and not _aura(c)
    ]


def _aura(choice: ActiveChoice) -> bool:
    option = options(choice.ability).get(choice.option)
    return option is not None and option.aura_range is not None


def eligible_after(game: Game, unit: Unit, action: str) -> bool:
    # Whether an active option lets the unit shoot and declare a charge after
    # `action` ("advanced", "fell_back") this turn: its own, or one that
    # applies to it.
    seat = deployment.owner(game, unit).seat
    for choice in active_choices(game, seat):
        if choice.target_unit_id is not None and choice.target_unit_id != unit.id:
            continue
        if choice.target_unit_id is None and choice.unit_id != unit.id:
            continue
        option = options(choice.ability).get(choice.option)
        if option is not None and action in option.eligible_after:
            return True
    return False


def _base(game: Game, unit_model: UnitModel):
    p = deployment.positions(game)[unit_model.id]
    return deployment.base_at(unit_model, p.x, p.y, p.rotation)


def targets(game: Game, ability: CommandAbility) -> list[Unit]:
    # The friendly units an option of the ability could apply to: those with
    # one of its target keywords with a model within its range of the model
    # with it.
    config = ability.config
    if not config.target_keywords:
        return []
    seat = deployment.owner(game, ability.unit).seat
    player = next(p for p in game.players if p.seat == seat)
    source = _base(game, ability.model)
    found = []
    for unit in deployment.deployable_units(player):
        models = deployment.models_on_battlefield(game, unit)
        keywords = {k.name for m in models for k in m.model.keywords}
        if not keywords & set(config.target_keywords):
            continue
        if any(
            gap(source, _base(game, m)) <= (config.target_range or 0) + TOLERANCE for m in models
        ):
            found.append(unit)
    return found


def this_phase(game: Game, seat: int) -> list[GameCommandChoice]:
    # The options the player has selected in this Command phase.
    return [
        c for c in game.command_choices if c.seat == seat and c.battle_round == game.battle_round
    ]


def choose(
    game: Game,
    seat: int,
    unit_id: int,
    ability_name: str,
    option: str | None,
    target_unit_id: int | None = None,
) -> None:
    # The player selects an option for one of their units' abilities (or, for
    # one that needn't have one, none) in their Command phase.
    if not is_command_phase(game) or game.turn_seat != seat:
        raise _bad_request("abilities' options are selected in their owner's Command phase")
    ability = next(
        (
            a
            for a in command_abilities(game, seat)
            if a.unit.id == unit_id and a.ability == ability_name
        ),
        None,
    )
    if ability is None:
        raise _bad_request(f"that unit has no {ability_name} to select an option for")
    if option is None:
        if ability.config.required:
            raise _bad_request(f"{ability_name} must have one of its options selected")
    elif option not in options(ability_name):
        raise _bad_request(f"{ability_name} has no option {option!r}")
    if option is not None and ability.config.target_keywords:
        if target_unit_id not in {u.id for u in targets(game, ability)}:
            words = " or ".join(ability.config.target_keywords)
            raise _bad_request(
                f'{ability_name} needs a friendly {words} unit within '
                f'{ability.config.target_range:g}" of the model with it'
            )
    elif target_unit_id is not None:
        raise _bad_request(f"{ability_name} doesn't apply to another unit")
    for existing in this_phase(game, seat):
        if existing.unit_id == unit_id and existing.ability == ability_name:
            game.command_choices.remove(existing)
    if option is not None:
        game.command_choices.append(
            GameCommandChoice(
                battle_round=game.battle_round,
                seat=seat,
                unit_id=unit_id,
                ability=ability_name,
                option=option,
                target_unit_id=target_unit_id,
            )
        )


def missing_choices(game: Game) -> list[str]:
    # What has to be selected before the Command phase ends: each of the
    # player whose turn it is's abilities that must have an option, not yet
    # selected this phase - unless no unit could be its target.
    seat = game.turn_seat
    chosen = {(c.unit_id, c.ability) for c in this_phase(game, seat)}
    missing = []
    for ability in command_abilities(game, seat):
        if not ability.config.required or (ability.unit.id, ability.ability) in chosen:
            continue
        if ability.config.target_keywords and not targets(game, ability):
            continue
        missing.append(f"{ability.unit.faction_unit.name}'s {ability.ability}")
    return missing


# --- healing at the start of the Command phase ---


def heals(game: Game) -> list[GameCommandHeal]:
    # The models healed at the start of this Command phase.
    return [
        h
        for h in game.command_heals
        if h.battle_round == game.battle_round and h.seat == game.turn_seat
    ]


def heal(game: Game) -> None:
    # The start of the Command phase: each of the player whose turn it is's
    # models on the battlefield with a healing ability rolls its die and
    # regains up to that many lost wounds (once a phase).
    if heals(game):
        return
    dice = datasheet_ability_seeds.COMMAND_HEALS
    player = next(p for p in game.players if p.seat == game.turn_seat)
    records = casualties.damage(game)
    for unit in deployment.deployable_units(player):
        for unit_model in deployment.models_on_battlefield(game, unit):
            for ability in unit_model.model.abilities:
                if ability.name not in dice:
                    continue
                roll = random.randint(1, dice[ability.name])
                record = records.get(unit_model.id)
                healed = min(roll, record.wounds_lost) if record else 0
                if record:
                    record.wounds_lost -= healed
                game.command_heals.append(
                    GameCommandHeal(
                        battle_round=game.battle_round,
                        seat=game.turn_seat,
                        unit_model_id=unit_model.id,
                        ability=ability.name,
                        roll=roll,
                        healed=healed,
                    )
                )
