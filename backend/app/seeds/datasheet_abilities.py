from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules import Rule
from app.combat_rules.conditions import (
    ALWAYS,
    ATTACKER_DAMAGED,
    RANGED_ATTACK,
)
from app.combat_rules.effects import (
    BENEFIT_OF_COVER,
    DEADLY_DEMISE,
    MINUS_ONE_TO_HIT,
    REROLL_FAILED_HITS,
)
from app.models import Condition, DatasheetAbility, Effect

# Core datasheet abilities, shared by every faction (each faction's own are in
# app/seeds/factions/<faction>/datasheet_abilities.py, in the same shape).
# (name, description, [condition keywords], [effect keywords])
CORE_ENTRIES = [
    (
        "Lone Operative",
        "This unit can only be selected as the target of a ranged attack if the attacking model "
        "is within 12\".",
        [],
        [],
    ),
    (
        "Reroll Failed Hits",
        "This unit may always re-roll failed hit rolls.",
        [ALWAYS],
        [REROLL_FAILED_HITS],
    ),
    (
        "Deadly Demise D3",
        "When this model is destroyed, roll one D6. On a 6, each unit within 6\" of it "
        "suffers D3 mortal wounds.",
        [ALWAYS],
        [DEADLY_DEMISE],
    ),
    (
        "Deadly Demise D6",
        "When this model is destroyed, roll one D6. On a 6, each unit within 6\" of it "
        "suffers D6 mortal wounds.",
        [ALWAYS],
        [DEADLY_DEMISE],
    ),
    (
        "Deadly Demise 1",
        "When this model is destroyed, roll one D6. On a 6, each unit within 6\" of it "
        "suffers 1 mortal wound.",
        [ALWAYS],
        [DEADLY_DEMISE],
    ),
    (
        "Stealth",
        "Each time a ranged attack targets this unit, this unit has the Benefit of Cover.",
        [],
        [],
    ),
    (
        "Infiltrators",
        "During deployment, this unit can be set up anywhere on the battlefield that is more "
        "than 9\" horizontally away from the enemy deployment zone and all enemy models.",
        [],
        [],
    ),
    (
        "Damaged: 1-5 Wounds Remaining",
        "While this model has 1-5 wounds remaining, subtract 3 from this model's Objective "
        "Control characteristic and each time this model makes an attack, subtract 1 from the "
        "Hit roll.",
        [],
        [],
    ),
    (
        "Firing Deck 2",
        "Each time this TRANSPORT is selected to shoot, it can use the ranged weapons of up to "
        "2 models embarked within it as if it were equipped with them. Until the end of the "
        "turn, the units embarked within it are not eligible to shoot.",
        [],
        [],
    ),
    (
        "Firing Deck 7",
        "Each time this TRANSPORT is selected to shoot, it can use the ranged weapons of up to "
        "7 models embarked within it as if it were equipped with them. Until the end of the "
        "turn, the units embarked within it are not eligible to shoot.",
        [],
        [],
    ),
    (
        "Scouts 9\"",
        "At the start of the first battle round, before the first turn begins, this unit can "
        "make a Normal move of up to 9\".",
        [],
        [],
    ),
    (
        "Scouts 6\"",
        "At the start of the first battle round, before the first turn begins, this unit can "
        "make a Normal move of up to 6\".",
        [],
        [],
    ),
    (
        "Fights First",
        "Units with this ability that are eligible to fight do so in the Fights First step, "
        "provided every model in the unit has this ability.",
        [],
        [],
    ),
    (
        "Deep Strike",
        "During the Declare Battle Formations step, if every model in this unit has this "
        "ability, you can set it up in Reserves instead of setting it up on the battlefield. "
        "If you do, in the Reinforcements step of one of your Movement phases you can set up "
        "this unit anywhere on the battlefield that is more than 9\" horizontally away from "
        "all enemy models.",
        [],
        [],
    ),
]

# How the calculator handles core abilities where that isn't obvious from
# their conditions/effects (or RULES/OPTIONS descriptions): {ability name:
# note}. Shown with the ability.
CORE_CALCULATOR_NOTES = {
    "Deadly Demise D3": "Only whether it explodes is resolved, not the D3 mortal wounds.",
    "Deadly Demise 1": "Only whether it explodes is resolved, not the mortal wound.",
    "Deadly Demise D6": "Only whether it explodes is resolved, not the D6 mortal wounds.",
    "Infiltrators": "Descriptive only: a deployment rule.",
    "Deep Strike": "Descriptive only: a deployment rule.",
    "Fights First": "Descriptive only here: in a game, it decides the fight order.",
    'Scouts 6"': (
        "Descriptive only in the calculator; in a game, a Normal move of up to 6\" before the "
        "first turn (see app/services/in_game/scouts.py)."
    ),
    "Firing Deck 2": (
        "Descriptive only in the calculator; in a game, the transport can fire the ranged "
        "weapons of up to 2 embarked models (see app/services/in_game/shooting.py)."
    ),
    "Firing Deck 7": (
        "Descriptive only in the calculator; in a game, the transport can fire the ranged "
        "weapons of up to 7 embarked models (see app/services/in_game/shooting.py)."
    ),
    "Lone Operative": (
        "Descriptive only in the calculator; in a game, models more than 12\" away can't shoot "
        "it."
    ),
}

# Code-defined rules for core abilities, by name - for rules the
# conditions/effects stored on the row can't express, chiefly defensive ones
# ("each time an attack targets this unit"): a stored ability only ever
# modifies its own unit's attacks, while a Rule with side="defender" modifies
# attacks made against its unit. Applied to a unit if any of its models has the
# ability. Rows listed here are seeded with no conditions/effects of their own.
CORE_RULES = {
    "Damaged: 1-5 Wounds Remaining": [
        Rule(
            conditions=(ATTACKER_DAMAGED,),
            effects=(MINUS_ONE_TO_HIT,),
            description=(
                "-1 to hit when \"Attacking model is Damaged\" is ticked under Modifiers (the "
                "OC change is outside the calculator)."
            ),
        ),
    ],
    "Stealth": [
        Rule(
            conditions=(RANGED_ATTACK,),
            effects=(BENEFIT_OF_COVER,),
            side="defender",
            description=(
                "Ranged attacks against this unit treat it as in cover (doesn't stack with "
                "being in cover)."
            ),
        ),
    ],
}


def calculator_notes(name: str) -> list[str]:
    # How the calculator handles an ability (core or any faction's): its note,
    # and its rules' descriptions.
    combined = _combine()
    note = combined["CALCULATOR_NOTES"].get(name)
    rules = combined["RULES"].get(name, []) + combined["ARMY_RULES"].get(name, [])
    return ([note] if note else []) + [rule.description for rule in rules if rule.description]


async def seed(session: AsyncSession) -> None:
    # Adds the core and every faction's datasheet abilities that aren't there
    # yet, by name.
    for name, description, condition_keywords, effect_keywords in _combine()["ENTRIES"]:
        existing = (
            await session.execute(
                select(DatasheetAbility.id).where(DatasheetAbility.name == name)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        conditions = (
            await session.execute(select(Condition).where(Condition.keyword.in_(condition_keywords)))
        ).scalars().all()
        effects = (
            await session.execute(select(Effect).where(Effect.keyword.in_(effect_keywords)))
        ).scalars().all()
        if len(conditions) != len(condition_keywords) or len(effects) != len(effect_keywords):
            continue  # conditions/effects haven't been seeded yet

        session.add(
            DatasheetAbility(
                name=name,
                description=description,
                conditions=list(conditions),
                effects=list(effects),
            )
        )
    await session.commit()


# Selectable options for core abilities: {ability name: {option name:
# RuleOption}}. Like faction ability options (e.g. Doctrina Imperatives), the
# active one is chosen per combat. Aura ranges ("within 6\"") aren't modelled:
# an army-wide option reaches every unit of the same faction in the army list.
CORE_OPTIONS: dict = {}


# --- every faction's, together ---
#
# ENTRIES, CALCULATOR_NOTES, RULES and OPTIONS combine the core ones above with
# each faction's (its datasheet_abilities.py, where it has one), and
# OPTION_OWNERS maps each option to its ability. They're built on first use
# rather than at import, since faction files import this one (e.g. for
# CORE_RULES["Stealth"]).

COMBINED = (
    "ENTRIES",
    "CALCULATOR_NOTES",
    "RULES",
    "ARMY_RULES",
    "OPTIONS",
    "OPTION_OWNERS",
    "COMMAND_CHOICES",
    "COMMAND_HEALS",
    "ROUND_START_CP",
    "ALWAYS_ACTIVE_OPTIONS",
    "CONDITIONAL_LONE_OPERATIVE",
    "WARGEAR_WOUNDS",
    "SECURES_OBJECTIVES",
    "PSYKER_LEVELS",
    "PSYCHIC_ABILITIES",
    "SHOCK_DISEMBARK_AFTER",
    "CHARGE_REROLLS",
    "AFTER_CHARGE_BATTLE_SHOCK",
    "ACTION_AFTER",
    "ROLL_BONUSES",
    "SHOOT_SCOOT",
    "STRATAGEM_TARGET_CP",
    "START_OF_SHOOTING",
    "REACTIVE_MOVES",
    "RALLIES",
    "REPAIRS",
    "PSYCHIC_ROLLS",
    "TRANSPORT_AS_BODYGUARD",
)
_combined: dict | None = None


def _combine() -> dict:
    global _combined
    if _combined is None:
        from app.seeds.factions import FACTIONS

        sources = [
            {
                "ENTRIES": CORE_ENTRIES,
                "CALCULATOR_NOTES": CORE_CALCULATOR_NOTES,
                "RULES": CORE_RULES,
                "OPTIONS": CORE_OPTIONS,
                "ARMY_RULES": {},
                "COMMAND_CHOICES": {},
                "COMMAND_HEALS": {},
                "ROUND_START_CP": {},
                "ALWAYS_ACTIVE_OPTIONS": {},
                "CONDITIONAL_LONE_OPERATIVE": {},
                "WARGEAR_WOUNDS": {},
                "SECURES_OBJECTIVES": {},
                "PSYKER_LEVELS": {},
                "PSYCHIC_ABILITIES": {},
                "SHOCK_DISEMBARK_AFTER": {},
                "CHARGE_REROLLS": set(),
                "AFTER_CHARGE_BATTLE_SHOCK": {},
                "ACTION_AFTER": {},
                "ROLL_BONUSES": {},
                "SHOOT_SCOOT": {},
                "STRATAGEM_TARGET_CP": {},
                "START_OF_SHOOTING": {},
                "REACTIVE_MOVES": {},
                "RALLIES": {},
                "REPAIRS": {},
                "PSYCHIC_ROLLS": {},
                "TRANSPORT_AS_BODYGUARD": set(),
            }
        ] + [
            {
                name: getattr(faction.datasheet_abilities, name, default)
                for name, default in (
                    ("ENTRIES", []),
                    ("CALCULATOR_NOTES", {}),
                    ("RULES", {}),
                    ("OPTIONS", {}),
                    ("ARMY_RULES", {}),
                    ("COMMAND_CHOICES", {}),
                    ("COMMAND_HEALS", {}),
                    ("ROUND_START_CP", {}),
                    ("ALWAYS_ACTIVE_OPTIONS", {}),
                    ("CONDITIONAL_LONE_OPERATIVE", {}),
                    ("WARGEAR_WOUNDS", {}),
                    ("SECURES_OBJECTIVES", {}),
                    ("PSYKER_LEVELS", {}),
                    ("PSYCHIC_ABILITIES", {}),
                    ("SHOCK_DISEMBARK_AFTER", {}),
                    ("CHARGE_REROLLS", set()),
                    ("AFTER_CHARGE_BATTLE_SHOCK", {}),
                    ("ACTION_AFTER", {}),
                    ("ROLL_BONUSES", {}),
                    ("SHOOT_SCOOT", {}),
                    ("STRATAGEM_TARGET_CP", {}),
                    ("START_OF_SHOOTING", {}),
                    ("REACTIVE_MOVES", {}),
                    ("RALLIES", {}),
                    ("REPAIRS", {}),
                    ("PSYCHIC_ROLLS", {}),
                    ("TRANSPORT_AS_BODYGUARD", set()),
                )
            }
            for faction in FACTIONS
            if hasattr(faction, "datasheet_abilities")
        ]
        entries = [entry for source in sources for entry in source["ENTRIES"]]
        names = [entry[0] for entry in entries]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"datasheet abilities defined more than once: {duplicates}")
        options = {k: v for source in sources for k, v in source["OPTIONS"].items()}
        _combined = {
            "ENTRIES": entries,
            "CALCULATOR_NOTES": {
                k: v for source in sources for k, v in source["CALCULATOR_NOTES"].items()
            },
            "RULES": {k: v for source in sources for k, v in source["RULES"].items()},
            "OPTIONS": options,
            # Rules an ability gives the *other* units of its faction in the
            # same army list (e.g. Prophet of Destruction), by ability name.
            "ARMY_RULES": {k: v for source in sources for k, v in source["ARMY_RULES"].items()},
            # In a game: abilities whose option is selected in the Command
            # phase, and abilities that heal then (see each faction's file).
            "COMMAND_CHOICES": {
                k: v for source in sources for k, v in source["COMMAND_CHOICES"].items()
            },
            "COMMAND_HEALS": {
                k: v for source in sources for k, v in source["COMMAND_HEALS"].items()
            },
            # Abilities that gain CP at the start of the battle round while a
            # model with one is its player's WARLORD.
            "ROUND_START_CP": {
                k: v for source in sources for k, v in source["ROUND_START_CP"].items()
            },
            # Abilities that make army rule options active for their own unit
            # all the time (e.g. Codex Adept: every Combat Doctrine).
            "ALWAYS_ACTIVE_OPTIONS": {
                k: v for source in sources for k, v in source["ALWAYS_ACTIVE_OPTIONS"].items()
            },
            # Abilities that give their unit Lone Operative while it's within
            # a distance of a friendly unit with some keywords (e.g. Leader of
            # Astartes): {ability name: (distance, keywords)}.
            "CONDITIONAL_LONE_OPERATIVE": {
                k: v
                for source in sources
                for k, v in source["CONDITIONAL_LONE_OPERATIVE"].items()
            },
            # Wargear that adds to its bearer's Wounds characteristic (e.g.
            # Storm Shield: +1), by wargear name.
            "WARGEAR_WOUNDS": {
                k: v for source in sources for k, v in source["WARGEAR_WOUNDS"].items()
            },
            # Abilities that secure the objectives their unit is controlling
            # at the end of one of their player's phases: {name: phase}.
            "SECURES_OBJECTIVES": {
                k: v for source in sources for k, v in source["SECURES_OBJECTIVES"].items()
            },
            # A PSYKER's psyker level, by the ability that gives it, and each
            # psychic ability's psychic level (see app/services/in_game/psychic.py).
            "PSYKER_LEVELS": {
                k: v for source in sources for k, v in source["PSYKER_LEVELS"].items()
            },
            "PSYCHIC_ABILITIES": {
                k: v for source in sources for k, v in source["PSYCHIC_ABILITIES"].items()
            },
            # Transport abilities that let the units embarked in it make a shock
            # disembark move after it made one of these moves this phase (e.g.
            # Rapid Disembarkation: "advance") - see
            # app/services/in_game/embarked.py: {ability name: (move kind, ...)}.
            "SHOCK_DISEMBARK_AFTER": {
                k: v for source in sources for k, v in source["SHOCK_DISEMBARK_AFTER"].items()
            },
            # In a game (see app/services/in_game/charging.py): abilities that
            # let their unit re-roll its charge roll, and those that make each
            # enemy unit engaged with it after its charge move take a
            # Battle-shock test - {name: (modifier, keywords that spare an
            # enemy unit the modifier)}.
            "CHARGE_REROLLS": {n for source in sources for n in source["CHARGE_REROLLS"]},
            "AFTER_CHARGE_BATTLE_SHOCK": {
                k: v
                for source in sources
                for k, v in source["AFTER_CHARGE_BATTLE_SHOCK"].items()
            },
            # Abilities whose moves don't stop their unit starting an action
            # (see app/services/in_game/actions.py): {name: (move, ...)} -
            # "advanced", "fell_back".
            "ACTION_AFTER": {k: v for source in sources for k, v in source["ACTION_AFTER"].items()},
            # Abilities that add to their unit's Advance and charge rolls (see
            # app/services/in_game/movement.py roll_bonus): {name: {"rolls":
            # ("advance", "charge"), "bonus": n, "near": (keywords, inches,
            # bonus instead while within that of a friendly unit with them)}}.
            "ROLL_BONUSES": {k: v for source in sources for k, v in source["ROLL_BONUSES"].items()},
            # Abilities that let their unit move after shooting (see
            # app/services/in_game/shoot_scoot.py) - and how.
            "SHOOT_SCOOT": {k: v for source in sources for k, v in source["SHOOT_SCOOT"].items()},
            # Abilities that gain their player 1CP on a D6 roll of at least
            # this, each time a Stratagem targets their unit (see
            # app/services/in_game/game.py use_stratagem).
            "STRATAGEM_TARGET_CP": {
                k: v for source in sources for k, v in source["STRATAGEM_TARGET_CP"].items()
            },
            # Abilities used at the start of their player's Shooting phase on
            # an enemy unit (see app/services/in_game/shooting_start.py).
            "START_OF_SHOOTING": {
                k: v for source in sources for k, v in source["START_OF_SHOOTING"].items()
            },
            # Abilities that let their unit move in its opponent's Movement
            # phase when an enemy unit ends a move near it (see
            # app/services/in_game/reactive_move.py).
            "REACTIVE_MOVES": {
                k: v for source in sources for k, v in source["REACTIVE_MOVES"].items()
            },
            # Abilities that rally a friendly Battle-shocked unit (see
            # app/services/in_game/rally.py), and that repair a friendly model
            # in their player's Command phase (repair.py).
            "RALLIES": {k: v for source in sources for k, v in source["RALLIES"].items()},
            "REPAIRS": {k: v for source in sources for k, v in source["REPAIRS"].items()},
            # Psychic abilities without a psychic level, and what their
            # psychic roll does (see app/services/in_game/psychic.py).
            "PSYCHIC_ROLLS": {
                k: v for source in sources for k, v in source["PSYCHIC_ROLLS"].items()
            },
            # Abilities that let their model, while it's leading a unit, embark
            # in any TRANSPORT its Bodyguard unit can (see
            # app/services/in_game/embarked.py).
            "TRANSPORT_AS_BODYGUARD": {
                n for source in sources for n in source["TRANSPORT_AS_BODYGUARD"]
            },
            # {option name: ability name}. Option names are unique across every
            # ability (and every faction ability's options).
            "OPTION_OWNERS": {
                option_name: ability_name
                for ability_name, ability_options in options.items()
                for option_name in ability_options
            },
        }
    return _combined


def __getattr__(name: str):
    # ENTRIES, RULES, etc. (see above), looked up like ordinary module values.
    if name in COMBINED:
        return _combine()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
