from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BaseSize

# The standard bases, round then oval, plus "Use model" for models that don't
# come with one (e.g. vehicle hulls) and flying bases.
NAMES = [
    "25mm",
    "28mm",
    "28.5mm",
    "32mm",
    "40mm",
    "50mm",
    "60mm",
    "80mm",
    "90mm",
    "100mm",
    "130mm",
    "160mm",
    "60 x 35mm",
    "75 x 42mm",
    "90 x 52mm",
    "105 x 70mm",
    "120 x 92mm",
    "150 x 95mm",
    "170 x 105mm",
    "Small flying base",
    "Large flying base",
    "Use model",
]


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(BaseSize.name))).scalars().all())
    missing = [BaseSize(name=name) for name in NAMES if name not in existing]
    if missing:
        session.add_all(missing)
        await session.commit()
