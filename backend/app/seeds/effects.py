from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.effects import (
    ADD_EXTRA_ATTACK,
    ADD_EXTRA_HIT,
    ASSAULT,
    AUTO_PASS_WOUND,
    FORCE_CRITICAL_WOUND,
    HAZARDOUS,
    IGNORE_COVER,
    IGNORE_COVER_UNIT,
    NO_SAVE,
    PISTOL,
    PLUS_ONE_SKILL_MELEE,
    PLUS_ONE_SKILL_RANGED,
    PLUS_ONE_TO_HIT,
    REROLL_FAILED_HITS,
)
from app.models import Effect

# (keyword, name, description) - keyword must match a function registered in
# app/combat_rules/effects.py.
ENTRIES = [
    (
        AUTO_PASS_WOUND,
        "Auto-Pass Wound",
        "The wound roll for this attack automatically succeeds.",
    ),
    (
        ADD_EXTRA_HIT,
        "Add Extra Hit",
        "Adds one additional hit to the attack chain.",
    ),
    (
        IGNORE_COVER,
        "Ignores Cover",
        "This attack's hit roll is not worsened by the defender being in cover.",
    ),
    (
        NO_SAVE,
        "No Save",
        "The save roll for this attack is skipped entirely (no armor or invulnerable save).",
    ),
    (
        FORCE_CRITICAL_WOUND,
        "Force Critical Wound",
        "This attack's wound counts as a critical wound regardless of the actual roll.",
    ),
    (
        ADD_EXTRA_ATTACK,
        "Add Extra Attack",
        "Adds one additional attack to the chain for this weapon, with its own hit roll.",
    ),
    (
        IGNORE_COVER_UNIT,
        "Ignores Cover (Unit)",
        "The whole attacking unit, not just this model, ignores the in-cover penalty.",
    ),
    (
        HAZARDOUS,
        "Hazardous",
        "The firing model makes a hazard roll, risking a self-inflicted wound.",
    ),
    (
        PLUS_ONE_TO_HIT,
        "+1 to Hit",
        "This attack's hit roll needs 1 less to succeed.",
    ),
    (
        REROLL_FAILED_HITS,
        "Re-roll Failed Hits",
        "If this attack's hit roll fails, it is rolled once more and the second result is used instead.",
    ),
    (
        PLUS_ONE_SKILL_RANGED,
        "+1 Skill (Ranged)",
        "This attack's hit roll needs 1 less to succeed, but only for a ranged weapon.",
    ),
    (
        PLUS_ONE_SKILL_MELEE,
        "+1 Skill (Melee)",
        "This attack's hit roll needs 1 less to succeed, but only for a melee weapon.",
    ),
    (
        ASSAULT,
        "Assault",
        "This weapon may still be fired even if its bearer's unit advanced this turn.",
    ),
    (
        PISTOL,
        "Pistol",
        "This weapon may be fired while its bearer is in engagement range.",
    ),
]


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Effect.keyword))).scalars().all())
    missing = [
        Effect(keyword=keyword, name=name, description=description)
        for keyword, name, description in ENTRIES
        if keyword not in existing
    ]
    if missing:
        session.add_all(missing)
        await session.commit()
