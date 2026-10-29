from __future__ import annotations

import random
from dataclasses import dataclass

from fastapi import HTTPException

from app.combat_rules import CommandChoice, RuleOption
from app.models import (
    FactionAbility,
    Game,
    GameCommandChoice,
    GameCommandHeal,
    GameRuleChoice,
    Unit,
    UnitModel,
)
from app.seeds import datasheet_abilities as datasheet_ability_seeds
from app.seeds import factions as faction_seeds
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
# then the option is only that unit's. Some are selected in another of their
# owner's phases instead (CommandChoice.phase - e.g. Author of the Codex: in
# the Movement phase, for a visible ADEPTUS ASTARTES unit within 12", a
# combat doctrine active for it as well as any others), and last until the
# start of their next Command phase all the same. An option that targets an enemy unit
# (Invocation of Machine Vengeance: any enemy unit on the battlefield, seen
# or not) has it selected with it - then the option only applies to attacks
# against that unit.
#
# Other abilities heal a model at the start of its owner's Command phase
# (datasheet_abilities COMMAND_HEALS - e.g. Self-repair Mechanisms: D3 lost
# wounds).
#
# Some army rules have their player select one of their options (or none)
# then too (faction COMMAND_PHASE_CHOICES - e.g. Combat Doctrines), for every
# unit with the rule, until the start of their next Command phase; some
# options can only be selected once per battle (ONCE_PER_BATTLE). While
# active, it's one of those units' rule options in combat, and can let them
# shoot or declare a charge after Advancing or Falling Back (ELIGIBLE_AFTER).


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


def command_abilities(game: Game, seat: int, phase: str | None = None) -> list[CommandAbility]:
    # The player's units on the battlefield with such abilities (once per
    # unit and ability), in list order - those selected in `phase`, if given.
    player = next(p for p in game.players if p.seat == seat)
    config = {
        name: choice
        for name, choice in _choices_config().items()
        if phase is None or choice.phase == phase
    }
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
    # The ability's options: {option name: RuleOption} - or, for one whose
    # options are an army rule's (e.g. Author of the Codex), that rule's (with
    # what each does).
    config = _choices_config().get(ability)
    if config is not None and config.faction_options is not None:
        descriptions = faction_seeds.COMMAND_PHASE_DESCRIPTIONS.get(config.faction_options, {})
        return {
            name: RuleOption(description=descriptions.get(name, ""))
            for name in faction_seeds.rule_options(*config.faction_options)
        }
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


def _targets_enemy(choice: ActiveChoice) -> bool:
    option = options(choice.ability).get(choice.option)
    return option is not None and option.targets_enemy


def options_for(
    game: Game, seat: int, unit: Unit, attacking: Unit | None = None
) -> list[str]:
    # The active options that can apply to the unit (one that applies to
    # another unit doesn't, nor an aura - see app/services/in_game/auras.py,
    # which checks its range) - the calculator works out which it gains. One
    # with an enemy target (e.g. Invocation of Machine Vengeance) only when
    # the unit is attacking that target.
    found = active_army_options(game, seat) + [
        o for o in always_active_options(unit) if o not in active_army_options(game, seat)
    ]
    for choice in active_choices(game, seat):
        if _aura(choice):
            continue
        if _targets_enemy(choice):
            if attacking is not None and attacking.id == choice.target_unit_id:
                found.append(choice.option)
        elif _applies_to(choice, unit):
            found.append(choice.option)
    return found


def _aura(choice: ActiveChoice) -> bool:
    option = options(choice.ability).get(choice.option)
    return option is not None and option.aura_range is not None


def eligible_after(game: Game, unit: Unit, action: str, to: str) -> bool:
    # Whether an active option lets the unit `to` ("shoot", "charge": declare
    # a charge) after `action` ("advanced", "fell_back") this turn: its own,
    # one that applies to it, or its army rule's (e.g. the Tactical
    # Doctrine).
    seat = deployment.owner(game, unit).seat
    held = _held_army_rules(unit)
    army_options = [o for a, o in _active_army_choices(game, seat) if a in held]
    for option in army_options + always_active_options(unit):
        if to in faction_seeds.ELIGIBLE_AFTER.get(option, {}).get(action, ()):
            return True
    for choice in active_choices(game, seat):
        if choice.target_unit_id is not None and choice.target_unit_id != unit.id:
            continue
        if choice.target_unit_id is None and choice.unit_id != unit.id:
            continue
        option = options(choice.ability).get(choice.option)
        if option is not None and action in option.eligible_after and to in option.eligible_for:
            return True
        # One named for an army rule's option (e.g. Author of the Codex's
        # doctrines) lets it as that does.
        if to in faction_seeds.ELIGIBLE_AFTER.get(choice.option, {}).get(action, ()):
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
        near = [
            m
            for m in models
            if gap(source, _base(game, m)) <= (config.target_range or 0) + TOLERANCE
        ]
        if near and (not config.target_visible or _sees(game, ability, unit, near)):
            found.append(unit)
    return found


def _sees(game: Game, ability: CommandAbility, unit: Unit, models: list[UnitModel]) -> bool:
    # Whether the model with the ability can see one of `models` (of `unit` -
    # itself, if it's the same unit).
    # (Imported here: shooting imports this module.)
    from app.services.in_game import shooting

    if unit.id == ability.unit.id:
        return True
    source = _base(game, ability.model)
    sight = shooting.Sight(game)
    return any(sight.sees(source, _base(game, m)) for m in models)


def enemy_targets(game: Game, ability: CommandAbility) -> list[Unit]:
    # The enemy units an option that targets one could pick: any on the
    # battlefield (visible or not, however far).
    seat = deployment.owner(game, ability.unit).seat
    placed = deployment.positions(game)
    return [
        unit
        for player in game.players
        if player.seat != seat
        for unit in deployment.deployable_units(player)
        if deployment.is_deployed(unit, placed)
    ]


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
    # one that needn't have one, none) in their Command phase - or the phase
    # it's selected in.
    if game.status != "in_progress" or game.turn_seat != seat:
        raise _bad_request("abilities' options are selected in their owner's turn")
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
    if game.phase != ability.config.phase:
        raise _bad_request(
            f"{ability_name} is selected in its owner's {ability.config.phase} phase"
        )
    if option is None:
        if ability.config.required:
            raise _bad_request(f"{ability_name} must have one of its options selected")
    elif option not in options(ability_name):
        raise _bad_request(f"{ability_name} has no option {option!r}")
    if option is not None and options(ability_name)[option].targets_enemy:
        if target_unit_id not in {u.id for u in enemy_targets(game, ability)}:
            raise _bad_request(f"{option} needs an enemy unit on the battlefield as its target")
    elif option is not None and ability.config.target_keywords:
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
    for ability in command_abilities(game, seat, "command"):
        if not ability.config.required or (ability.unit.id, ability.ability) in chosen:
            continue
        if ability.config.target_keywords and not targets(game, ability):
            continue
        missing.append(f"{ability.unit.faction_unit.name}'s {ability.ability}")
    return missing


# --- army rules selected in the Command phase ---


@dataclass
class ArmyRule:
    # An army rule (faction ability) of the player's whose option is selected
    # in their Command phase, and the names of their units with it on the
    # battlefield.
    ability: FactionAbility
    units: list[str]

    @property
    def key(self) -> tuple[str, str]:
        return (self.ability.faction.name, self.ability.name)


def army_rules(game: Game, seat: int) -> list[ArmyRule]:
    # The player's such army rules (once each), in list order.
    player = next(p for p in game.players if p.seat == seat)
    found: dict[int, ArmyRule] = {}
    for unit in deployment.deployable_units(player):
        for unit_model in deployment.models_on_battlefield(game, unit):
            for ability in unit_model.model.faction_abilities:
                if (ability.faction.name, ability.name) not in faction_seeds.COMMAND_PHASE_CHOICES:
                    continue
                rule = found.setdefault(ability.id, ArmyRule(ability, []))
                if unit.faction_unit.name not in rule.units:
                    rule.units.append(unit.faction_unit.name)
    return list(found.values())


def _army_rule_choices(game: Game, seat: int) -> list[GameRuleChoice]:
    # The player's choices for army rules selected in the Command phase (one
    # per Command phase - its battle round).
    keys = faction_seeds.COMMAND_PHASE_CHOICES
    abilities = {
        a.id: a
        for p in game.players
        for u in p.army_list.units
        for m in u.unit_models
        for a in m.model.faction_abilities
    }
    return [
        c
        for c in game.rule_choices
        if c.seat == seat
        and c.faction_ability_id in abilities
        and (abilities[c.faction_ability_id].faction.name, abilities[c.faction_ability_id].name)
        in keys
    ]


def _active_army_choices(game: Game, seat: int) -> list[tuple[int, str]]:
    # The (faction ability id, option) active for the player now: selected in
    # their most recent Command phase.
    latest = last_command_round(game, seat)
    return [
        (c.faction_ability_id, c.option)
        for c in _army_rule_choices(game, seat)
        if c.battle_round == latest
    ]


def active_army_options(game: Game, seat: int) -> list[str]:
    # The options active for the player's units with those army rules (the
    # calculator applies each only to units with its rule).
    return [option for _, option in _active_army_choices(game, seat)]


def always_active_options(unit: Unit) -> list[str]:
    # Army rule options active for the unit all the time because of one of
    # its models' abilities (datasheet_abilities ALWAYS_ACTIVE_OPTIONS - e.g.
    # Codex Adept: every Combat Doctrine).
    config = datasheet_ability_seeds.ALWAYS_ACTIVE_OPTIONS
    found: list[str] = []
    for unit_model in unit.unit_models:
        for ability in unit_model.model.abilities:
            for option in config.get(ability.name, ()):
                if option not in found:
                    found.append(option)
    return found


def _held_army_rules(unit: Unit) -> set[int]:
    return {a.id for m in unit.unit_models for a in m.model.faction_abilities}


def army_rule_options(game: Game, seat: int, rule: ArmyRule) -> list[str]:
    # The options the player can select for the rule this Command phase: all
    # of them - less those selected in earlier ones, for a rule whose options
    # can each be selected once per battle (or more, with a detachment that
    # lets them - e.g. Assault Mastery).
    names = list(faction_seeds.rule_options(*rule.key))
    if rule.key not in faction_seeds.ONCE_PER_BATTLE:
        return names
    earlier = [
        c.option
        for c in _army_rule_choices(game, seat)
        if c.faction_ability_id == rule.ability.id and c.battle_round < game.battle_round
    ]
    player = next(p for p in game.players if p.seat == seat)
    allowed = {name: 1 for name in names}
    for detachment in player.army_list.detachments:
        for option, extra in faction_seeds.EXTRA_SELECTIONS.get(detachment.name, {}).items():
            if option in allowed:
                allowed[option] += extra
    return [n for n in names if earlier.count(n) < allowed[n]]


def army_rule_this_phase(game: Game, seat: int, faction_ability_id: int) -> GameRuleChoice | None:
    # The option the player has selected for the rule in this Command phase.
    return next(
        (
            c
            for c in _army_rule_choices(game, seat)
            if c.faction_ability_id == faction_ability_id and c.battle_round == game.battle_round
        ),
        None,
    )


def choose_army_rule(
    game: Game, seat: int, faction_ability_id: int, option: str | None
) -> None:
    # The player selects an option (or none) for one of their army rules in
    # their Command phase.
    if not is_command_phase(game) or game.turn_seat != seat:
        raise _bad_request("army rules' options are selected in their owner's Command phase")
    rule = next(
        (r for r in army_rules(game, seat) if r.ability.id == faction_ability_id), None
    )
    if rule is None:
        raise _bad_request("that player has no army rule with options to select now")
    if option is not None and option not in army_rule_options(game, seat, rule):
        if option in faction_seeds.rule_options(*rule.key):
            raise _bad_request(f"{option} has already been selected this battle")
        raise _bad_request(f"{rule.ability.name} has no option {option!r}")
    existing = army_rule_this_phase(game, seat, faction_ability_id)
    if existing is not None:
        game.rule_choices.remove(existing)
    if option is not None:
        game.rule_choices.append(
            GameRuleChoice(
                battle_round=game.battle_round,
                seat=seat,
                faction_ability_id=faction_ability_id,
                option=option,
            )
        )


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
