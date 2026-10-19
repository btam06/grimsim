from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Disposition

NAMES = [
    "Reconnaissance",
    "Purge the Foe",
    "Priority Assets",
    "Take and Hold",
    "Disruption",
]


# {old name: new name} - existing rows are renamed in place, keeping their
# links to detachments.
RENAMED = {"Reconnaisance": "Reconnaissance"}


async def seed(session: AsyncSession) -> None:
    taken = set((await session.execute(select(Disposition.name))).scalars().all())
    for row in (
        await session.execute(select(Disposition).where(Disposition.name.in_(RENAMED)))
    ).scalars():
        if RENAMED[row.name] not in taken:
            row.name = RENAMED[row.name]
    await session.flush()

    existing = set((await session.execute(select(Disposition.name))).scalars().all())
    missing = [Disposition(name=name) for name in NAMES if name not in existing]
    if missing:
        session.add_all(missing)
        await session.commit()
