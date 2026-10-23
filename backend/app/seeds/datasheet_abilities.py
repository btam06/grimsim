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
    'Scouts 6"': "Descriptive only: a pre-battle move.",
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

COMBINED = ("ENTRIES", "CALCULATOR_NOTES", "RULES", "ARMY_RULES", "OPTIONS", "OPTION_OWNERS")
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
