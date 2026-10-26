from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import (
    ALWAYS,
    ANTI_FLY_2,
    ANTI_INFANTRY_2,
    ANTI_INFANTRY_3,
    ANTI_INFANTRY_4,
    ANTI_INFANTRY_5,
    ANTI_MONSTER_4,
    ANTI_NON_VEHICLE_4,
    ANTI_VEHICLE_2,
    ANTI_VEHICLE_3,
    ANTI_VEHICLE_4,
    ANTI_WALKER_2,
    ATTACKER_DAMAGED,
    ATTACKER_IS_BATTLELINE,
    BEYOND_HALF_RANGE_ATTACK,
    ATTACKER_LED_BY_CHARACTER,
    CHARGED,
    CRITICAL_HIT,
    CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE,
    CRITICAL_WOUND,
    DEFENDER_BATTLE_SHOCKED,
    DEFENDER_BELOW_HALF_STRENGTH,
    DEFENDER_BELOW_STARTING_STRENGTH,
    DEFENDER_CONTROLLING_OBJECTIVE,
    DEFENDER_IN_RANGE_OF_OBJECTIVE,
    HALF_RANGE_ATTACK,
    MELEE_ATTACK,
    MOVED_LESS_THAN_3,
    PRE_WEAPON,
    PRE_WEAPON_NOT_MONSTER_OR_VEHICLE,
    RANGED_ATTACK,
    RANGED_CRITICAL_HIT,
    RANGED_MOVED_LESS_THAN_3,
    RANGED_VS_OBJECTIVE_TARGET,
    RILED_UP_RANGED_CRITICAL_HIT,
    STATIONARY_RANGED_CRITICAL_HIT,
    STRENGTH_EXCEEDS_TOUGHNESS,
    TARGET_HAS_CHARACTER,
    TARGET_INFANTRY,
    TARGET_ISOLATED,
    TARGET_TITANIC,
    TARGET_WITHIN_9,
    TARGET_LED_BY_CHARACTER,
    TARGET_MODEL_CHARACTER,
    TARGET_MONSTER_OR_VEHICLE,
    TARGET_NOT_MONSTER_OR_VEHICLE,
    WITHIN_HALF_RANGE,
    WITHOUT_DEVASTATING_WOUNDS,
)
from app.models import Condition

# (keyword, name, description) - keyword must match a function registered in
# app/combat_rules/conditions.py.
# Core conditions; each faction's own are in its conditions.py ENTRIES.
CORE_ENTRIES = [
    (CRITICAL_HIT, "Critical Hit", "The hit roll for this attack was a natural 6."),
    (CRITICAL_WOUND, "Critical Wound", "The wound roll for this attack was a natural 6."),
    (ALWAYS, "Always", "Always applies, regardless of step or roll."),
    (
        ANTI_INFANTRY_2,
        "Anti-Infantry 2+",
        "The wound roll was a 2+ against a defending unit that contains an INFANTRY model.",
    ),
    (
        ANTI_INFANTRY_3,
        "Anti-Infantry 3+",
        "The wound roll was a 3+ against a defending unit that contains an INFANTRY model.",
    ),
    (
        ANTI_INFANTRY_4,
        "Anti-Infantry 4+",
        "The wound roll was a 4+ against a defending unit that contains an INFANTRY model.",
    ),
    (
        ANTI_VEHICLE_2,
        "Anti-Vehicle 2+",
        "The wound roll was a 2+ against a defending unit that contains a VEHICLE model.",
    ),
    (
        ANTI_VEHICLE_3,
        "Anti-Vehicle 3+",
        "The wound roll was a 3+ against a defending unit that contains a VEHICLE model.",
    ),
    (
        ANTI_VEHICLE_4,
        "Anti-Vehicle 4+",
        "The wound roll was a 4+ against a defending unit that contains a VEHICLE model.",
    ),
    (
        ANTI_MONSTER_4,
        "Anti-Monster 4+",
        "The wound roll was a 4+ against a defending unit that contains a MONSTER model.",
    ),
    (
        WITHIN_HALF_RANGE,
        "Within Half Range",
        "The shooting model is within half the weapon's range.",
    ),
    (
        MOVED_LESS_THAN_3,
        "Moved Less Than 3\"",
        "The attacking unit moved less than 3\" this turn.",
    ),
    (
        TARGET_MONSTER_OR_VEHICLE,
        "Target is Monster or Vehicle",
        "The defending unit contains a MONSTER or VEHICLE model. Applies at every step.",
    ),
    (
        RANGED_MOVED_LESS_THAN_3,
        "Ranged Weapon, Moved Less Than 3\"",
        "The weapon is ranged and the attacking unit moved less than 3\" this turn.",
    ),
    (
        ATTACKER_IS_BATTLELINE,
        "Attacker is Battleline",
        "The attacking unit contains a BATTLELINE model. Applies at every step.",
    ),
    (
        TARGET_NOT_MONSTER_OR_VEHICLE,
        "Target is not Monster or Vehicle",
        "The defending unit contains no MONSTER or VEHICLE model. Applies at every step.",
    ),
    (
        CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE,
        "Critical Hit vs non-Monster/Vehicle",
        "The hit roll was a natural 6 against a defending unit with no MONSTER or VEHICLE model.",
    ),
    (
        RILED_UP_RANGED_CRITICAL_HIT,
        "Riled Up Ranged Critical Hit",
        "A natural 6 to hit with a ranged weapon while the attacking unit is riled up.",
    ),
    (
        PRE_WEAPON_NOT_MONSTER_OR_VEHICLE,
        "Weapon Targets non-Monster/Vehicle",
        "Checked once per weapon: the defending unit has no MONSTER or VEHICLE model.",
    ),
    (
        TARGET_HAS_CHARACTER,
        "Target has Character",
        "The defending unit contains a CHARACTER model. Applies at every step.",
    ),
    (
        TARGET_LED_BY_CHARACTER,
        "Target Led by Character",
        "The defending unit is a CHARACTER leading other models. Applies at every step.",
    ),
    (
        TARGET_INFANTRY,
        "Target is Infantry",
        "The defending unit contains an INFANTRY model. Applies at every step.",
    ),
    (
        RANGED_ATTACK,
        "Ranged Attack",
        "A ranged attack, checked before its hit roll.",
    ),
    (
        PRE_WEAPON,
        "Once per Weapon",
        "Checked once per weapon, not per attack - for effects that add attacks.",
    ),
    (
        DEFENDER_IN_RANGE_OF_OBJECTIVE,
        "Defender in Range of Objective",
        "The defending unit is within range of an objective marker.",
    ),
    (
        CHARGED,
        "Charged This Turn",
        "The attacking unit made a Charge move this turn.",
    ),
    (
        ANTI_FLY_2,
        "Anti-Fly 2+",
        "The wound roll was a 2+ against a defending unit that contains a FLY model.",
    ),
    (
        RANGED_CRITICAL_HIT,
        "Ranged Critical Hit",
        "A critical hit (unmodified 6 to hit) with a ranged weapon.",
    ),
    (
        STATIONARY_RANGED_CRITICAL_HIT,
        "Ranged Critical Hit While Stationary",
        "A ranged critical hit by a unit that Remained Stationary this turn.",
    ),
    (
        ANTI_INFANTRY_5,
        "Anti-Infantry 5+",
        "The wound roll was a 5+ against a defending unit that contains an INFANTRY model.",
    ),
    (
        MELEE_ATTACK,
        "Melee Attack",
        "A melee attack, checked before its hit roll.",
    ),
    (
        HALF_RANGE_ATTACK,
        "Attack Within Half Range",
        "An attack against a target within half range, checked before its hit roll.",
    ),
    (
        ATTACKER_LED_BY_CHARACTER,
        "Attacker Led by Character",
        "The attacking unit is a CHARACTER leading other models. Applies at every step.",
    ),
    (
        TARGET_MODEL_CHARACTER,
        "Target Model is a Character",
        "The defending model is a CHARACTER.",
    ),
    (
        STRENGTH_EXCEEDS_TOUGHNESS,
        "Strength Greater Than Toughness",
        "At the wound roll, the attack's Strength is greater than the target's Toughness.",
    ),
    (
        DEFENDER_BELOW_STARTING_STRENGTH,
        "Defender Below Starting Strength",
        "The defending unit is below its Starting Strength (or Below Half-strength).",
    ),
    (
        DEFENDER_BELOW_HALF_STRENGTH,
        "Defender Below Half-strength",
        "The defending unit is Below Half-strength.",
    ),
    (
        DEFENDER_BATTLE_SHOCKED,
        "Defender Battle-shocked",
        "The defending unit is Battle-shocked.",
    ),
    (
        ATTACKER_DAMAGED,
        "Attacker Damaged",
        "The attacking model is on its Damaged profile, checked before its hit roll.",
    ),
    (
        BEYOND_HALF_RANGE_ATTACK,
        "Attack Beyond Half Range",
        "An attack against a target that isn't within half range, checked before its hit roll.",
    ),
    (
        TARGET_ISOLATED,
        "Target Isolated",
        "No other units from the defender's army are within 6\" of it. Applies at every step.",
    ),
    (
        TARGET_TITANIC,
        "Target is Titanic",
        "The defending unit has a TITANIC model. Applies at every step.",
    ),
    (
        ANTI_WALKER_2,
        "Anti-Walker 2+",
        "The wound roll was a 2+ against a defending unit that contains a WALKER model.",
    ),
    (
        RANGED_VS_OBJECTIVE_TARGET,
        "Ranged Attack vs Target on Objective",
        "A ranged attack against a unit within range of an objective marker.",
    ),
    (
        DEFENDER_CONTROLLING_OBJECTIVE,
        "Defender Controlling an Objective",
        "The defending unit is controlling an objective. Applies at every step.",
    ),
    (
        TARGET_WITHIN_9,
        "Target Within 9\"",
        "The target is within 9\" of the attacking unit. Applies at every step.",
    ),
    (
        ANTI_NON_VEHICLE_4,
        "Anti-non-Vehicle 4+",
        "The wound roll was a 4+ against a defending unit with no VEHICLE model.",
    ),
    (
        WITHOUT_DEVASTATING_WOUNDS,
        "Without Devastating Wounds",
        "The attack's weapon doesn't have [DEVASTATING WOUNDS].",
    ),
]


def all_entries() -> list[tuple[str, str, str]]:
    # The core conditions' rows and every faction's.
    from app.seeds.factions import FACTIONS

    return CORE_ENTRIES + [
        entry
        for faction in FACTIONS
        for entry in getattr(getattr(faction, "conditions", None), "ENTRIES", [])
    ]


def __getattr__(name: str):
    # ENTRIES: every condition row, core and faction (built on first use, since
    # the factions package imports the combat rules this module uses).
    if name == "ENTRIES":
        return all_entries()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Condition.keyword))).scalars().all())
    missing = [
        Condition(keyword=keyword, name=name, description=description)
        for keyword, name, description in all_entries()
        if keyword not in existing
    ]
    if missing:
        session.add_all(missing)
        await session.commit()
