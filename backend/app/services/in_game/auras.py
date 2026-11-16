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
    # (Relics of the Matriarchs' are chosen each battle round - see auras.)
    from app.seeds.factions.adepta_sororitas import unit_abilities as sororitas

    if ability in datasheet_ability_seeds.COMMAND_CHOICES or ability == sororitas.RELICS:
        return {}
    # (Nor one chosen as it's used - e.g. Triarch Abilities.)
    if ability in datasheet_ability_seeds.ACTIVATIONS:
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
            # (Its datasheet abilities, and its wargear's - e.g. a gloom prism.)
            names = [a.name for a in unit_model.model.abilities] + [
                a.name for g in unit_model.wargear for a in g.abilities
            ]
            for ability in names:
                for name, option in _passive(ability).items():
                    reach = option.aura_range + range_bonus(game, unit_model, ability)
                    found.append(Aura(unit, unit_model, ability, name, reach))
    # Relics of the Matriarchs: those chosen this battle round.
    from app.seeds.factions.adepta_sororitas import unit_abilities as sororitas

    for unit in deployment.deployable_units(player):
        chosen = sororitas.chosen_relics(game, unit)
        if not chosen:
            continue
        options = datasheet_ability_seeds.OPTIONS.get(sororitas.RELICS, {})
        for unit_model in sororitas.relic_models(game, unit):
            for name in chosen:
                if name in options:
                    found.append(Aura(unit, unit_model, sororitas.RELICS, name, options[name].aura_range))
    # Options chosen as an ability's used (e.g. Triarch Abilities), this
    # battle round.
    from app.services.in_game import activations

    for unit in deployment.deployable_units(player):
        for name, how in datasheet_ability_seeds.ACTIVATIONS.items():
            if how["effect"] != "choose":
                continue
            option = activations.chosen(game, unit, name)
            options = datasheet_ability_seeds.OPTIONS.get(name, {})
            if option is None or option not in options:
                continue
            # (From the model it says - e.g. Szarekh - or any with it.)
            holders = [
                m
                for m in deployment.models_on_battlefield(game, unit)
                if any(a.name == name for a in m.model.abilities)
            ]
            source = next(
                (m for m in holders if m.model.name == how.get("from_model")),
                holders[0] if holders else None,
            )
            if source is not None:
                found.append(Aura(unit, source, name, option, options[option].aura_range))
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


def range_bonus(game: Game, unit_model: UnitModel, ability: str) -> float:
    # What a rule has added to the model's aura's range (e.g. Atomic Energy
    # Manipulator: 3" each Fight phase it destroyed models, to at most 12" -
    # datasheet_abilities AURA_RANGE_GROWTH).
    from app.services.in_game import mission_state

    config = datasheet_ability_seeds.AURA_RANGE_GROWTH
    found = next(
        (c for a in unit_model.model.abilities if a.name in config and config[a.name]["aura"] == ability
         for c in (config[a.name],)),
        None,
    )
    if found is None:
        return 0.0
    grown = len(mission_state.marked(game, f"{AURA_GROWN}{unit_model.id}"))
    base = next(iter(datasheet_ability_seeds.OPTIONS.get(ability, {}).values())).aura_range
    return min(grown * found["by"], found["most"] - base)


# A model's aura grown once (see range_bonus): a mark of this kind + its unit
# model id.
AURA_GROWN = "aura_grown:"


def grow_at_end_of_fight(game: Game) -> None:
    # The end of the Fight phase: each model with an AURA_RANGE_GROWTH ability
    # that destroyed one or more models this phase grows its aura.
    from app.services.in_game import mission_state, turn_record

    config = datasheet_ability_seeds.AURA_RANGE_GROWTH
    if not config or game.phase != "fight":
        return
    # (Who destroyed what is recorded by unit: its unit's kills this phase.)
    killers = {
        r.destroyed_by_unit_id
        for r in turn_record.models_destroyed(game, game.battle_round, game.turn_seat)
        if r.phase == "fight"
    }
    for player in game.players:
        for unit in deployment.deployable_units(player):
            for unit_model in deployment.models_on_battlefield(game, unit):
                if not any(a.name in config for a in unit_model.model.abilities):
                    continue
                kind = f"{AURA_GROWN}{unit_model.id}"
                if any(
                    m.battle_round == game.battle_round and m.turn_seat == game.turn_seat
                    for m in mission_state.marked(game, kind)
                ):
                    continue
                if unit.id in killers:
                    mission_state.mark(game, player.seat, kind, unit.id)


def in_range(game: Game, aura: Aura, unit: Unit) -> bool:
    # Whether one of the unit's models is within the aura's range of its
    # model - and the unit has the keywords it reaches (see RuleOption).
    option = _option(aura)
    if option is not None and (option.aura_keywords or option.aura_excluded):
        keywords = {k.name for m in unit.unit_models for k in m.model.keywords}
        if not set(option.aura_keywords) <= keywords or set(option.aura_excluded) & keywords:
            return False
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


def enemy_rules(game: Game, attacker: Unit) -> list:
    # Rules for the attacker's attacks from enemy auras it's within range of
    # (datasheet_abilities ENEMY_AURAS - e.g. Harassment Swarm: -1 to hit for
    # a unit, not a MONSTER or VEHICLE, within 3" of the Macrocytes' unit),
    # each ability once.
    config = datasheet_ability_seeds.ENEMY_AURAS
    if not config:
        return []
    seat = deployment.owner(game, attacker).seat
    keywords = {k.name for m in attacker.unit_models for k in m.model.keywords}
    mine = [_base(game, m) for m in deployment.models_on_battlefield(game, attacker)]
    found = []
    for name, how in sorted(config.items()):
        if keywords & set(how.get("excluded", ())):
            continue
        hit = False
        for player in game.players:
            if player.seat == seat:
                continue
            for unit in deployment.deployable_units(player):
                models = deployment.models_on_battlefield(game, unit)
                if not any(a.name == name for m in models for a in m.model.abilities):
                    continue
                # (Measured from the whole unit - "within 3" of this unit".)
                if any(
                    gap(_base(game, m), b) <= how["range"] + TOLERANCE for m in models for b in mine
                ):
                    hit = True
        if hit:
            found += list(how["rules"])
    return found


def _reaching(game: Game, unit: Unit) -> list:
    # The RuleOptions of its player's auras that reach the unit.
    seat = deployment.owner(game, unit).seat
    return [o for a in auras(game, seat) if in_range(game, a, unit) and (o := _option(a)) is not None]


def move_bonus(game: Game, unit: Unit) -> int:
    # What auras reaching it add to its Move (e.g. Relentless March: 2") -
    # each option once.
    seen = {}
    for option in _reaching(game, unit):
        if option.move:
            seen[id(option)] = option.move
    return sum(seen.values())


def charge_rerolls(game: Game, unit: Unit) -> bool:
    # Whether an aura reaching it lets it re-roll Charge rolls (e.g. Phaeron of
    # the Blades).
    return any(o.charge_rerolls for o in _reaching(game, unit))
