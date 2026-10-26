from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FactionUnit

# The Skitarii Marshal was first seeded misspelt ("Skitarii Marshall"): the
# row is renamed in place, keeping the units built from it (unless one with
# the right name already exists in that faction).
OLD, NEW = "Skitarii Marshall", "Skitarii Marshal"


async def run(session: AsyncSession) -> None:
    for old in (
        await session.execute(select(FactionUnit).where(FactionUnit.name == OLD))
    ).scalars():
        taken = (
            await session.execute(
                select(FactionUnit).where(
                    FactionUnit.name == NEW, FactionUnit.faction_id == old.faction_id
                )
            )
        ).scalar_one_or_none()
        if taken is None:
            old.name = NEW
    await session.flush()
