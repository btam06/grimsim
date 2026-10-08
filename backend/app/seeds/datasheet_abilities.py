from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import ALWAYS
from app.combat_rules.effects import REROLL_FAILED_HITS
from app.models import Condition, DatasheetAbility, Effect

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Reroll Failed Hits",
        "This unit may always re-roll failed hit rolls.",
        [ALWAYS],
        [REROLL_FAILED_HITS],
    ),
]


async def seed(session: AsyncSession) -> None:
    for name, description, condition_keywords, effect_keywords in ENTRIES:
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
