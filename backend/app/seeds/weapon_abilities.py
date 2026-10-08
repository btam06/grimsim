from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import ALWAYS, CRITICAL_HIT, CRITICAL_WOUND
from app.combat_rules.effects import ADD_EXTRA_HIT, AUTO_PASS_WOUND, IGNORE_COVER, NO_SAVE
from app.models import Condition, Effect, WeaponAbility

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "SUSTAINED 1",
        "Each critical hit (an unmodified roll of 6 to hit) scores 1 additional hit.",
        [CRITICAL_HIT],
        [ADD_EXTRA_HIT],
    ),
    (
        "Ignores Cover",
        "This weapon's attacks are not worsened by the defender being in cover.",
        [ALWAYS],
        [IGNORE_COVER],
    ),
    (
        "Lethal Hits",
        "Each critical hit (an unmodified roll of 6 to hit) automatically wounds.",
        [CRITICAL_HIT],
        [AUTO_PASS_WOUND],
    ),
    (
        "Devastating Wounds",
        "Each critical wound (an unmodified roll of 6 to wound) allows no save.",
        [CRITICAL_WOUND],
        [NO_SAVE],
    ),
]


async def seed(session: AsyncSession) -> None:
    for name, description, condition_keywords, effect_keywords in ENTRIES:
        existing = (
            await session.execute(select(WeaponAbility.id).where(WeaponAbility.name == name))
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
            WeaponAbility(
                name=name,
                description=description,
                conditions=list(conditions),
                effects=list(effects),
            )
        )
    await session.commit()
