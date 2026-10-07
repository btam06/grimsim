from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Disposition, Faction


async def get_faction_id(session: AsyncSession, faction_name: str) -> int | None:
    return (
        await session.execute(select(Faction.id).where(Faction.name == faction_name))
    ).scalar_one_or_none()


async def get_dispositions_by_name(session: AsyncSession) -> dict[str, Disposition]:
    result = await session.execute(select(Disposition))
    return {d.name: d for d in result.scalars().all()}
