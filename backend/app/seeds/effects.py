from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.effects import ADD_EXTRA_HIT, AUTO_PASS_WOUND, IGNORE_COVER, NO_SAVE
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
