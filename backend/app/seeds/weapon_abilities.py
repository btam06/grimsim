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
    MOVED_LESS_THAN_3,
    PRE_WEAPON_NOT_MONSTER_OR_VEHICLE,
    TARGET_INFANTRY,
    TARGET_MONSTER_OR_VEHICLE,
    TARGET_NOT_MONSTER_OR_VEHICLE,
    WITHIN_HALF_RANGE,
)
from app.combat_rules.effects import (
    ADD_EXTRA_ATTACK,
    ADD_EXTRA_HIT,
    ADD_SIX_ATTACKS,
    ADD_TWO_EXTRA_HITS,
    ADD_THREE_ATTACKS,
    ASSAULT,
    AUTO_PASS_WOUND,
    BLAST,
    CANNOT_ATTACK,
    FORCE_CRITICAL_WOUND,
    HAZARDOUS,
    HEAVY,
    IGNORE_COVER,
    MELTA_3,
    NO_SAVE,
    PISTOL,
    PLUS_ONE_TO_HIT,
    PRECISION,
    REROLL_FAILED_WOUNDS,
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
        "Sustained 2",
        "Each critical hit (an unmodified roll of 6 to hit) scores 2 additional hits.",
        [CRITICAL_HIT],
        [ADD_TWO_EXTRA_HITS],
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
        "Anti-Monster 4+",
        "Against a defending unit that contains a MONSTER model, a wound roll of 4+ is a critical wound.",
        [ANTI_MONSTER_4],
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
        [HEAVY],
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
    (
        "Rapid Fire 3",
        "When the shooting model is within half range, this weapon makes 3 additional attacks.",
        [WITHIN_HALF_RANGE],
        [ADD_THREE_ATTACKS],
    ),
    (
        "Blast",
        "This weapon makes 1 additional attack for every five models in the target unit.",
        [ALWAYS],
        [BLAST],
    ),
    (
        # Descriptive only: the calculator doesn't model line of sight, and
        # Indirect Fire only changes anything against a target that isn't visible.
        "Indirect Fire",
        "This weapon can target units that are not visible to the attacking model.",
        [],
        [],
    ),
    (
        "Twin-linked",
        "Each time an attack is made with this weapon, you can re-roll that attack's Wound roll.",
        [ALWAYS],
        [REROLL_FAILED_WOUNDS],
    ),
    (
        "Blistering Salvoes: Infantry",
        "Each time an attack is made with this weapon that targets an INFANTRY unit, add 1 to the Hit roll.",
        [TARGET_INFANTRY],
        [PLUS_ONE_TO_HIT],
    ),
    (
        "Blistering Salvoes: Monster/Vehicle",
        "Each time an attack is made with this weapon that targets a MONSTER or VEHICLE unit, add 1 to the Hit roll.",
        [TARGET_MONSTER_OR_VEHICLE],
        [PLUS_ONE_TO_HIT],
    ),
    (
        "Melta 3",
        "When the target is within half range, each attack made with this weapon inflicts 3 extra damage.",
        [WITHIN_HALF_RANGE],
        [MELTA_3],
    ),
    (
        # Descriptive only: the calculator already fires every weapon ticked.
        "Extra Attacks",
        "This weapon can be used in addition to the bearer's other melee weapons.",
        [],
        [],
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


# Entries whose conditions/effects have changed since they were first seeded.
# Existing rows with these names have them reset to the entry above on
# startup (rather than being left alone, as other existing rows are).
RESYNCED = {
    # Was a generic +1 to hit; now the HEAVY flag, so Heavy from more than one
    # source still counts once.
    "Heavy",
}


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
        # had any conditions/effects (e.g. "Precision") - then fill them in -
        # or it's listed in RESYNCED.
        if (
            existing is not None
            and (existing.conditions or existing.effects)
            and name not in RESYNCED
        ):
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
