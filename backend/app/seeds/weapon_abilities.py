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
    CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE,
    CRITICAL_WOUND,
    MOVED_LESS_THAN_3,
    PRE_WEAPON_NOT_MONSTER_OR_VEHICLE,
    TARGET_NOT_MONSTER_OR_VEHICLE,
    WITHIN_HALF_RANGE,
)
from app.combat_rules.effects import (
    ADD_EXTRA_ATTACK,
    ADD_EXTRA_HIT,
    ADD_SIX_ATTACKS,
    ASSAULT,
    AUTO_PASS_WOUND,
    CANNOT_ATTACK,
    FORCE_CRITICAL_WOUND,
    HAZARDOUS,
    IGNORE_COVER,
    NO_SAVE,
    PISTOL,
    PLUS_ONE_TO_HIT,
    PRECISION,
)
from sqlalchemy.orm import selectinload

from app.models import Condition, Effect, WeaponAbility

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Sustained 1",
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
        "Lethal Hits: non-Monster/Vehicle",
        "Lethal Hits, but only against a unit with no MONSTER or VEHICLE model.",
        [CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE],
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
        "If the attacker applies precision, attacks target leaders first, then supports, then other models.",
        [ALWAYS],
        [PRECISION],
    ),
    (
        "Rapid Fire 1",
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
    (
        "Assault",
        "This weapon may still be fired even if the attacking unit advanced this turn.",
        [ALWAYS],
        [ASSAULT],
    ),
    (
        "Pistol",
        "This weapon may be fired while the attacking unit is in engagement range, without becoming a melee weapon.",
        [ALWAYS],
        [PISTOL],
    ),
    (
        "Close-Quarters",
        "This weapon may be fired while the attacking unit is in engagement range (as Pistol).",
        [ALWAYS],
        [PISTOL],
    ),
    (
        "Hunter: Monster/Vehicle",
        "This profile can only target units that contain a MONSTER or VEHICLE model.",
        [TARGET_NOT_MONSTER_OR_VEHICLE],
        [CANNOT_ATTACK],
    ),
    (
        "Blitz Dem Gitz!",
        "If this weapon targets a unit (excluding MONSTER/VEHICLE units), it has +6 A.",
        [PRE_WEAPON_NOT_MONSTER_OR_VEHICLE],
        [ADD_SIX_ATTACKS],
    ),
]


# {old name: new name} for entries that have been renamed. Existing rows are
# renamed in place (keeping them attached to their weapons) rather than a
# second row being seeded under the new name.
RENAMED = {
    "SUSTAINED 1": "Sustained 1",
    "RAPID FIRE 1": "Rapid Fire 1",
}


async def _rename(session: AsyncSession) -> None:
    rows = (
        await session.execute(select(WeaponAbility).where(WeaponAbility.name.in_(RENAMED)))
    ).scalars().all()
    taken = set(
        (
            await session.execute(
                select(WeaponAbility.name).where(WeaponAbility.name.in_(RENAMED.values()))
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if RENAMED[row.name] not in taken:
            row.name = RENAMED[row.name]
    await session.flush()


async def seed(session: AsyncSession) -> None:
    await _rename(session)
    for name, description, condition_keywords, effect_keywords in ENTRIES:
        existing = (
            await session.execute(
                select(WeaponAbility)
                .options(selectinload(WeaponAbility.conditions), selectinload(WeaponAbility.effects))
                .where(WeaponAbility.name == name)
            )
        ).scalar_one_or_none()
        # An existing row is left alone unless it was seeded before this entry
        # had any conditions/effects (e.g. "Precision") - then fill them in.
        if existing is not None and (existing.conditions or existing.effects):
            continue

        conditions = (
            await session.execute(select(Condition).where(Condition.keyword.in_(condition_keywords)))
        ).scalars().all()
        effects = (
            await session.execute(select(Effect).where(Effect.keyword.in_(effect_keywords)))
        ).scalars().all()
        if len(conditions) != len(condition_keywords) or len(effects) != len(effect_keywords):
            continue  # conditions/effects haven't been seeded yet

        if existing is not None:
            if conditions or effects:
                existing.description = description
                existing.conditions = list(conditions)
                existing.effects = list(effects)
            continue

        session.add(
            WeaponAbility(
                name=name,
                description=description,
                conditions=list(conditions),
                effects=list(effects),
            )
        )
    await session.commit()
