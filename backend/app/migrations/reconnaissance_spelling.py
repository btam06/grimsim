from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Disposition

# The Reconnaissance disposition was first seeded misspelt: the row is renamed
# in place, keeping its links to detachments and missions (unless one with the
# right name already exists).
OLD, NEW = "Reconnaisance", "Reconnaissance"


async def run(session: AsyncSession) -> None:
    taken = (
        await session.execute(select(Disposition).where(Disposition.name == NEW))
    ).scalar_one_or_none()
    old = (
        await session.execute(select(Disposition).where(Disposition.name == OLD))
    ).scalar_one_or_none()
    if old is not None and taken is None:
        old.name = NEW
        await session.flush()
