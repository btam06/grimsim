from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Keyword

NAMES = [
    "ADEPTUS MECHANICUS",
    "AIRCRAFT",
    "BATTLELINE",
    "CHARACTER",
    "CULT MECHANICUS",
    "DEDICATED TRANSPORT",
    "DOMINUS",
    "ELECTRO-PRIESTS",
    "EPIC HERO",
    "FLY",
    "FRAME",
    "GRENADES",
    "HASTARII",
    "IMPERIUM",
    "INFANTRY",
    "JUMP PACK",
    "KATAPHRON",
    "LEGIO CYBERNETICA",
    "MANIPULUS",
    "MARSHAL",
    "MOBILE",
    "MONSTER",
    "MOUNTED",
    "PTERAXII",
    "RANGERS",
    "SICARIAN",
    "SKITARII",
    "SMOKE",
    "SYDONIAN",
    "TECH-PRIEST",
    "TRANSPORT",
    "VANGUARD",
    "VEHICLE",
    "WALKER",
]


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Keyword.name))).scalars().all())
    missing = [Keyword(name=name) for name in NAMES if name not in existing]
    if missing:
        session.add_all(missing)
        await session.commit()
