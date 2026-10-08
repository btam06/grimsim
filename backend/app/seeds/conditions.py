from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import ALWAYS, CRITICAL_HIT, CRITICAL_WOUND
from app.models import Condition

# (keyword, name, description) - keyword must match a function registered in
# app/combat_rules/conditions.py.
ENTRIES = [
    (CRITICAL_HIT, "Critical Hit", "The hit roll for this attack was a natural 6."),
    (CRITICAL_WOUND, "Critical Wound", "The wound roll for this attack was a natural 6."),
    (ALWAYS, "Always", "Always applies, regardless of step or roll."),
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
