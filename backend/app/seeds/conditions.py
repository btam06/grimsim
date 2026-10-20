from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import (
    ALWAYS,
    ANTI_INFANTRY_2,
    ANTI_INFANTRY_3,
    ANTI_INFANTRY_4,
    ANTI_VEHICLE_2,
    ANTI_VEHICLE_3,
    ANTI_MONSTER_4,
    ANTI_VEHICLE_4,
    CRITICAL_HIT,
    CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE,
    CRITICAL_WOUND,
    ATTACKER_IS_BATTLELINE,
    MELEE_ATTACK_AGAINST_BATTLELINE,
    MOVED_LESS_THAN_3,
    PRE_WEAPON_NOT_MONSTER_OR_VEHICLE,
    RANGED_ATTACK,
    RANGED_MOVED_LESS_THAN_3,
    RILED_UP_RANGED_CRITICAL_HIT,
    TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,
    TARGET_HAS_CHARACTER,
    TARGET_INFANTRY,
    TARGET_LED_BY_CHARACTER,
    TARGET_MONSTER_OR_VEHICLE,
    TARGET_NOT_MONSTER_OR_VEHICLE,
    WITHIN_HALF_RANGE,
)
from app.models import Condition

# (keyword, name, description) - keyword must match a function registered in
# app/combat_rules/conditions.py.
ENTRIES = [
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
        MELEE_ATTACK_AGAINST_BATTLELINE,
        "Melee Attack Against Battleline",
        "A melee attack against a defending unit that contains a BATTLELINE model.",
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
        TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,
        "Target is Electro-priests Led by Character",
        "The defending unit is ELECTRO-PRIESTS led by a CHARACTER. Applies at every step.",
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
]


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Condition.keyword))).scalars().all())
    missing = [
        Condition(keyword=keyword, name=name, description=description)
        for keyword, name, description in ENTRIES
        if keyword not in existing
    ]
    if missing:
        session.add_all(missing)
        await session.commit()
