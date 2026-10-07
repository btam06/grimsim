from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Faction

NAMES = [
    "Adeptus Sororitas",
    "Adeptus Custodes",
    "Adeptus Mechanicus",
    "Astra Militarum",
    "Grey Knights",
    "Imperial Agents",
    "Imperial Knights",
    "Space Marines",
    "Chaos Daemons",
    "Chaos Knights",
    "Chaos Space Marines",
    "Death Guard",
    "Emperor's Children",
    "Thousand Sons",
    "World Eaters",
    "Aeldari",
    "Drukhari",
    "Genestealer Cults",
    "Leagues of Votann",
    "Necrons",
    "Orks",
    "T'au Empire",
    "Tyranids",
]


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Faction.name))).scalars().all())
    missing = [Faction(name=name) for name in NAMES if name not in existing]
    if missing:
        session.add_all(missing)
        await session.commit()
