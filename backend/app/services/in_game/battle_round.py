from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from fastapi import HTTPException

from app.models import Game, GamePlayer, GameRuleChoice
from app.seeds import factions as faction_seeds
from app.services.in_game import deployment

# The start of a battle round: before its first turn, rules that happen "at
# the start of the battle round" (or of particular ones - "the first battle
# round", "the first, third and fifth battle rounds") get their moment. A
# rule applies if one of a player's units has it on the battlefield - an
# ability, an army rule, an enhancement or upgrade - or it's one of their
# detachments' rules. When a rule that applies needs a decision - it has
# options to choose (see below), or its text gives the player a choice ("you
# can select...", "this unit can make a Normal move") - the battle round
# starts with this step (see app/services/in_game/game.py), listing every
# rule that applies; otherwise it goes straight to the first turn.
#
# An army rule with options (e.g. Doctrina Imperatives: the Protector or
# Conqueror Imperative - the same options as the combat calculator's) is chosen
# then, for the round: the player's units with that rule have the chosen
# option when they attack or are attacked that round. Some rules offer
# choices of their own (faction ROUND_START_CHOICES), and some choices last
# the rest of the battle and can't be made again (LASTING_CHOICES) - e.g.
# Harbingers of Dread's Dread abilities, chosen in the first, third and
# fifth battle rounds, one at a time or two rolled at random.

# The game's phase during this step - not one of a turn's PHASES.
START_OF_ROUND = "start_of_round"

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
# A rule's text gives the player a choice to make.
_DECISION = re.compile(r"\b(?:select|selects|choose|chooses|can)\b", re.IGNORECASE)
_START = re.compile(
    r"\bat the start of (?:the |each |every |a )?"
    r"((?:(?:first|second|third|fourth|fifth)(?:,\s*|\s+and\s+|\s+or\s+)?)*)"
    r"\s*battle rounds?\b",
    re.IGNORECASE,
)


def rounds_for(text: str | None) -> set[int] | None:
    # The battle rounds a rule happens at the start of (every one: {1..5}),
    # from its text - or None if it doesn't happen at the start of one.
    if not text:
        return None
    found: set[int] = set()
    for match in _START.finditer(text):
        ordinals = re.findall(r"first|second|third|fourth|fifth", match.group(1), re.IGNORECASE)
        found |= {ORDINALS[o.lower()] for o in ordinals} if ordinals else {1, 2, 3, 4, 5}
    return found or None


@dataclass
class RoundStartRule:
    # A rule that happens at the start of this battle round: what kind it is
    # ("ability", "army rule", "enhancement" or "detachment rule"), its name
    # and text, and the units it's from (none for a detachment rule).
    kind: str
    name: str
    description: str
    units: list[str] = field(default_factory=list)
    # For an army rule: which one, and its options (none if it has none).
    faction_ability_id: int | None = None
    options: list[str] = field(default_factory=list)
    option_descriptions: dict[str, str] = field(default_factory=dict)
    # Required: one of its options must be chosen (there's no "none").
    required: bool = False

    @property
    def decision(self) -> bool:
        # Whether it needs the player to decide something: it has options, or
        # its text gives them a choice.
        return bool(self.options) or bool(_DECISION.search(self.description))


def player_rules(game: Game, player: GamePlayer, battle_round: int) -> list[RoundStartRule]:
    # The player's rules that happen at the start of `battle_round`.
    found: dict[tuple[str, str], RoundStartRule] = {}

    def add(
        kind: str, name: str, description: str | None, unit: str | None, ability=None
    ) -> None:
        rounds = rounds_for(description)
        if rounds is None or battle_round not in rounds:
            return
        rule = found.get((kind, name))
        if rule is None:
            rule = found[(kind, name)] = RoundStartRule(
                kind=kind, name=name, description=description or ""
            )
            if ability is not None:
                key = (ability.faction.name, name)
                rule.faction_ability_id = ability.id
                rule.options = list(faction_seeds.rule_options(*key))
                rule.option_descriptions = faction_seeds.option_descriptions(*key)
                if key in faction_seeds.ROUND_START_CHOICES:
                    taken = set(chosen_options(game, player.seat, ability.id, earlier=True))
                    rule.options = [
                        o for o in faction_seeds.ROUND_START_CHOICES[key] if o not in taken
                    ]
                    rule.option_descriptions = faction_seeds.ROUND_START_DESCRIPTIONS.get(key, {})
                rule.required = faction_seeds.required(*key)
        if unit and unit not in rule.units:
            rule.units.append(unit)

    for detachment in player.army_list.detachments:
        for rule in detachment.rules:
            add("detachment rule", rule.name, rule.description, None)
    placed = deployment.positions(game)
    for unit in deployment.deployable_units(player):
        if not deployment.is_deployed(unit, placed):
            continue
        name = unit.faction_unit.name
        if unit.upgrade is not None:
            add("enhancement", unit.upgrade.name, unit.upgrade.description, name)
        for unit_model in deployment.models_on_battlefield(game, unit):
            model = unit_model.model
            if unit_model.enhancement is not None:
                enhancement = unit_model.enhancement
                add("enhancement", enhancement.name, enhancement.description, name)
            for ability in model.abilities:
                add("ability", ability.name, ability.description, name)
            for ability in model.faction_abilities:
                add("army rule", ability.name, ability.description, name, ability)
    return list(found.values())


def round_start_rules(game: Game, battle_round: int) -> dict[int, list[RoundStartRule]]:
    # Each player's (by seat) rules that happen at the start of the round.
    return {p.seat: player_rules(game, p, battle_round) for p in game.players}


def needs_decisions(game: Game, battle_round: int) -> bool:
    # Whether any rule at the start of the round needs a player to decide
    # something - then the round starts with this step.
    return any(
        rule.decision for rules in round_start_rules(game, battle_round).values() for rule in rules
    )


# --- choosing options for army rules ---


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _round_choices(game: Game, seat: int) -> list[GameRuleChoice]:
    return [
        c for c in game.rule_choices if c.seat == seat and c.battle_round == game.battle_round
    ]


# A round-start choice of "two at random": two D6 select from the rule's
# other choices, in order (e.g. Harbingers of Dread: 1 Despair ... 6 Dominion).
ROLL_TWO = "Roll two D6"


def choices(game: Game, seat: int) -> dict[int, str]:
    # The options the player chose this battle round, by faction ability id
    # (several, together, for a roll).
    found: dict[int, list[str]] = {}
    for c in _round_choices(game, seat):
        found.setdefault(c.faction_ability_id, []).append(c.option)
    return {ability_id: " + ".join(options) for ability_id, options in found.items()}


def _ability(game: Game, faction_ability_id: int):
    return next(
        (
            a
            for p in game.players
            for u in p.army_list.units
            for m in u.unit_models
            for a in m.model.faction_abilities
            if a.id == faction_ability_id
        ),
        None,
    )


def lasting(game: Game, faction_ability_id: int) -> bool:
    # Whether the ability's choices last the rest of the battle.
    ability = _ability(game, faction_ability_id)
    return ability is not None and (
        (ability.faction.name, ability.name) in faction_seeds.LASTING_CHOICES
    )


def chosen_options(
    game: Game, seat: int, faction_ability_id: int, earlier: bool = False
) -> list[str]:
    # The options the player has chosen for the ability: this battle round's
    # - and, for one whose choices last, every battle round's (only earlier
    # ones, if `earlier`).
    if lasting(game, faction_ability_id):
        rounds = (lambda r: r < game.battle_round) if earlier else (lambda r: True)
    else:
        rounds = (lambda r: False) if earlier else (lambda r: r == game.battle_round)
    return [
        c.option
        for c in game.rule_choices
        if c.seat == seat and c.faction_ability_id == faction_ability_id and rounds(c.battle_round)
    ]


def active_options(game: Game, seat: int) -> list[str]:
    # The options active for the player's army now (for the combat
    # calculator's rule options - only those it knows): this battle round's,
    # and those that last the battle.
    ability_ids = {c.faction_ability_id for c in game.rule_choices if c.seat == seat}
    return [
        option
        for ability_id in ability_ids
        for option in chosen_options(game, seat, ability_id)
        if option in faction_seeds.OPTION_OWNERS
    ]


def choose(game: Game, seat: int, faction_ability_id: int, option: str | None) -> None:
    # The player picks an option for one of their army rules with options
    # this battle round (or none), at its start.
    if game.status != "in_progress" or game.phase != START_OF_ROUND:
        raise _bad_request("options are chosen at the start of the battle round")
    player = next(p for p in game.players if p.seat == seat)
    rule = next(
        (
            r
            for r in player_rules(game, player, game.battle_round)
            if r.faction_ability_id == faction_ability_id
        ),
        None,
    )
    if rule is None or not rule.options:
        raise _bad_request("that player has no army rule with options to choose this round")
    if option is None and rule.required:
        raise _bad_request(f"{rule.name} must have one of its options chosen")
    if option is not None and option not in rule.options:
        raise _bad_request(f"{rule.name} has no option {option!r}")
    for existing in _round_choices(game, seat):
        if existing.faction_ability_id == faction_ability_id:
            game.rule_choices.remove(existing)
    if option is None:
        return
    picked = [option]
    if option == ROLL_TWO:
        # Two D6: what they select - each only once, and not what was chosen
        # before (duplicates have no effect).
        ability = _ability(game, faction_ability_id)
        key = (ability.faction.name, ability.name)
        table = [o for o in faction_seeds.ROUND_START_CHOICES[key] if o != ROLL_TWO]
        dice = sorted(random.randint(1, 6) for _ in range(2))
        earlier = set(chosen_options(game, seat, faction_ability_id, earlier=True))
        rolled = [table[d - 1] for d in dict.fromkeys(dice)]
        picked = [f"{ROLL_TWO}: {dice[0]} and {dice[1]}"] + [o for o in rolled if o not in earlier]
    for name in picked:
        game.rule_choices.append(
            GameRuleChoice(
                battle_round=game.battle_round,
                seat=seat,
                faction_ability_id=faction_ability_id,
                option=name,
            )
        )


def missing_choices(game: Game) -> list[str]:
    # What has to be chosen before the round's first turn: each player's army
    # rules with a required option (e.g. Doctrina Imperatives) not yet chosen.
    missing = []
    for player in game.players:
        chosen = choices(game, player.seat)
        for rule in player_rules(game, player, game.battle_round):
            if rule.required and rule.faction_ability_id not in chosen:
                missing.append(f"{player.user.name}'s {rule.name}")
    return missing
