from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Disposition

NAMES = [
    "Reconnaisance",
    "Purge the Foe",
    "Priority Assets",
    "Take and Hold",
    "Disruption",
]


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Disposition.name))).scalars().all())
    missing = [Disposition(name=name) for name in NAMES if name not in existing]
    if missing:
        session.add_all(missing)
        await session.commit()
