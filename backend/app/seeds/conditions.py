from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import (
    ALWAYS,
    ANTI_INFANTRY_2,
    ANTI_INFANTRY_3,
    ANTI_INFANTRY_4,
    ANTI_VEHICLE_2,
    ANTI_VEHICLE_3,
    ANTI_VEHICLE_4,
    CRITICAL_HIT,
    CRITICAL_WOUND,
    MOVED_LESS_THAN_3,
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
        WITHIN_HALF_RANGE,
        "Within Half Range",
        "The shooting model is within half the weapon's range.",
    ),
    (
        MOVED_LESS_THAN_3,
        "Moved Less Than 3\"",
        "The attacking unit moved less than 3\" this turn.",
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
