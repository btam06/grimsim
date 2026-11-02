from __future__ import annotations

from dataclasses import dataclass

from app.models import Unit, UnitModel
from app.engine.state import Game
from app.seeds import datasheet_abilities as datasheet_ability_seeds
from app.seeds.factions.chaos_knights import dread
from app.services.in_game import command_phase, deployment
from app.services.in_game.deployment import TOLERANCE, gap

# Auras, in a game: an option of a datasheet ability with an aura_range (see
# RuleOption) applies to friendly units with a model within that range of the
# model with the ability, base to base - its own unit included.
#
# - An aura ability with no choice to make (every option has a range, and
#   it isn't selected in the Command phase - e.g. Infectious Murder-madness,
#   Nullstone Field Generator) is always on.
# - An option selected in the Command phase with a range (e.g. Shroudpsalm)
#   is on while it's active (see app/services/in_game/command_phase.py).
#
# The combat calculator then gives each unit in range the option (as if it
# had been picked there).


@dataclass
class Aura:
    # An aura on the battlefield: the unit and model it's from, the ability
    # and option, and its range.
    unit: Unit
    model: UnitModel
    ability: str
    option: str
    range: float


def _passive(ability: str) -> dict:
    # The ability's options if it's an aura with no choice to make, else {}.
    if ability in datasheet_ability_seeds.COMMAND_CHOICES:
        return {}
    options = datasheet_ability_seeds.OPTIONS.get(ability, {})
    if options and all(o.aura_range for o in options.values()):
        return options
    return {}


def auras(game: Game, seat: int) -> list[Aura]:
    # The player's auras on the battlefield now.
    player = next(p for p in game.players if p.seat == seat)
    found = []
    for unit in deployment.deployable_units(player):
        for unit_model in deployment.models_on_battlefield(game, unit):
            for ability in unit_model.model.abilities:
                for name, option in _passive(ability.name).items():
                    found.append(Aura(unit, unit_model, ability.name, name, option.aura_range))
    abilities = {(a.unit.id, a.ability): a for a in command_phase.command_abilities(game, seat)}
    for choice in command_phase.active_choices(game, seat):
        option = command_phase.options(choice.ability).get(choice.option)
        source = abilities.get((choice.unit_id, choice.ability))
        if option is not None and option.aura_range and source is not None:
            found.append(
                Aura(source.unit, source.model, choice.ability, choice.option, option.aura_range)
            )
    return found


def _base(game: Game, unit_model: UnitModel):
    p = deployment.positions(game)[unit_model.id]
    return deployment.base_at(unit_model, p.x, p.y, p.rotation)


def in_range(game: Game, aura: Aura, unit: Unit) -> bool:
    # Whether one of the unit's models is within the aura's range of its
    # model.
    source = _base(game, aura.model)
    return any(
        gap(source, _base(game, m)) <= aura.range + TOLERANCE
        for m in deployment.models_on_battlefield(game, unit)
    )


def _option(aura: Aura):
    return datasheet_ability_seeds.OPTIONS.get(aura.ability, {}).get(aura.option)


def _wholly_within(aura: Aura) -> bool:
    # An aura that reaches only models wholly within its range (see RuleOption).
    option = _option(aura)
    return option is not None and option.wholly_within


def aura_options(game: Game, unit: Unit) -> list[str]:
    # The options of its owner's auras the unit is within range of (those
    # that reach models one by one aside - see model_rules).
    seat = deployment.owner(game, unit).seat
    return list(
        dict.fromkeys(
            a.option
            for a in auras(game, seat)
            if not _wholly_within(a) and in_range(game, a, unit)
        )
    )


def model_rules(game: Game, unit: Unit) -> dict[int, list]:
    # The rules of its owner's auras that reach models one by one (e.g.
    # Emanatus Force Field), for each of the unit's models wholly within
    # range: {unit model id: [Rule]}.
    from app.services.in_game import regions

    seat = deployment.owner(game, unit).seat
    found: dict[int, list] = {}
    for aura in auras(game, seat):
        if not _wholly_within(aura):
            continue
        source = _base(game, aura.model)
        for unit_model in deployment.models_on_battlefield(game, unit):
            if regions.base_wholly_within_of(_base(game, unit_model), [source], aura.range):
                found.setdefault(unit_model.id, []).extend(_option(aura).rules)
    return found


def ranges(game: Game, unit: Unit) -> list[tuple[UnitModel, str, float]]:
    # What reaches out from the unit's models, to show while it moves: its
    # auras (model, option, range) - and how far an ability selected in the
    # Command phase can reach to pick a unit (e.g. Rod of the War Forge's 6").
    seat = deployment.owner(game, unit).seat
    found = [(a.model, a.option, a.range) for a in auras(game, seat) if a.unit.id == unit.id]
    for ability in command_phase.command_abilities(game, seat):
        if ability.unit.id == unit.id and ability.config.target_range:
            found.append((ability.model, ability.ability, ability.config.target_range))
    # Harbingers of Dread's auras (see app/seeds/factions/chaos_knights/dread.py).
    found += [(m, "Dread auras", reach) for m, reach in dread.aura_models(game, unit)]
    return found
