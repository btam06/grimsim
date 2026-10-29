from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TerrainAreaShape, TerrainFeatureShape
from app.seeds import terrain_layouts as terrain_seed

# The terrain kit has more of a shape than first seeded (e.g. Priority Assets
# Mirror 03 uses four Ruin wall L (2.75 x 6.25), where the kit was first
# given two): seeding only adds missing shapes, so a layout using the new
# count would be refused. Raise each shape's count to the data file's.


async def run(session: AsyncSession) -> None:
    data = terrain_seed.load()
    for model, key in ((TerrainAreaShape, "area_shapes"), (TerrainFeatureShape, "feature_shapes")):
        counts = {entry["name"]: entry["count"] for entry in data.get(key, [])}
        for shape in (await session.execute(select(model))).scalars():
            if counts.get(shape.name, 0) > shape.count:
                shape.count = counts[shape.name]
