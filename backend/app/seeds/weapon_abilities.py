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
from app.combat_rules.effects import (
    ADD_EXTRA_ATTACK,
    ADD_EXTRA_HIT,
    AUTO_PASS_WOUND,
    FORCE_CRITICAL_WOUND,
    HAZARDOUS,
    IGNORE_COVER,
    NO_SAVE,
    PLUS_ONE_TO_HIT,
)
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
    (
        "Anti-Infantry 2+",
        "Against a defending unit that contains an INFANTRY model, a wound roll of 2+ is a critical wound.",
        [ANTI_INFANTRY_2],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Infantry 3+",
        "Against a defending unit that contains an INFANTRY model, a wound roll of 3+ is a critical wound.",
        [ANTI_INFANTRY_3],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Infantry 4+",
        "Against a defending unit that contains an INFANTRY model, a wound roll of 4+ is a critical wound.",
        [ANTI_INFANTRY_4],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Vehicle 2+",
        "Against a defending unit that contains a VEHICLE model, a wound roll of 2+ is a critical wound.",
        [ANTI_VEHICLE_2],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Vehicle 3+",
        "Against a defending unit that contains a VEHICLE model, a wound roll of 3+ is a critical wound.",
        [ANTI_VEHICLE_3],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Vehicle 4+",
        "Against a defending unit that contains a VEHICLE model, a wound roll of 4+ is a critical wound.",
        [ANTI_VEHICLE_4],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Precision",
        "No mechanical effect.",
        [],
        [],
    ),
    (
        "RAPID FIRE 1",
        "When the shooting model is within half range, this weapon makes 1 additional attack.",
        [WITHIN_HALF_RANGE],
        [ADD_EXTRA_ATTACK],
    ),
    (
        "Hazardous",
        "After shooting, the firing model makes a hazard roll, risking a self-inflicted wound.",
        [ALWAYS],
        [HAZARDOUS],
    ),
    (
        "Heavy",
        "If the attacking unit moved less than 3\" this turn, this weapon's attacks get +1 to hit.",
        [MOVED_LESS_THAN_3],
        [PLUS_ONE_TO_HIT],
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
