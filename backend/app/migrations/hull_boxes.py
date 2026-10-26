from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BaseSize, Model

# Hulls now measured as a box: the Skorpius Dunerider and Disintegrator (first
# seeded on "Use model") and the Impulsor (first seeded on a 100mm base).
# Seeding only fills in a model's base when it has none, so models still on
# their old base are moved to the box here (its base size row added if it
# isn't yet).
BOXES = {
    "Skorpius Dunerider": ("Use model", "155 x 90mm box"),
    "Skorpius Disintegrator": ("Use model", "155 x 90mm box"),
    "Impulsor": ("100mm", "155 x 90mm box"),
}


async def run(session: AsyncSession) -> None:
    models = (
        await session.execute(
            select(Model).options(selectinload(Model.base_size)).where(Model.name.in_(BOXES))
        )
    ).scalars().all()
    stale = [
        m for m in models if m.base_size is not None and m.base_size.name == BOXES[m.name][0]
    ]
    for model in stale:
        name = BOXES[model.name][1]
        box = (
            await session.execute(select(BaseSize).where(BaseSize.name == name))
        ).scalar_one_or_none()
        if box is None:
            box = BaseSize(name=name)
            session.add(box)
            await session.flush()
        model.base_size = box
    await session.flush()
