from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Condition, Stratagem

# Hellfire Rounds was first seeded with one Space Marines condition
# (hellfire_anti_non_vehicle_4); it's now two core ones, combined
# (anti_non_vehicle_4 and without_devastating_wounds). Its conditions and
# effects are cleared so the stratagem seed fills them in from stratagems.json
# again, and the old condition row goes.
STRATAGEM = "Hellfire Rounds"
OLD_CONDITION = "hellfire_anti_non_vehicle_4"


async def run(session: AsyncSession) -> None:
    stratagem = (
        await session.execute(
            select(Stratagem)
            .options(selectinload(Stratagem.conditions), selectinload(Stratagem.effects))
            .where(Stratagem.name == STRATAGEM)
        )
    ).scalar_one_or_none()
    if stratagem is not None and any(c.keyword == OLD_CONDITION for c in stratagem.conditions):
        stratagem.conditions = []
        stratagem.effects = []
        await session.flush()
    await session.execute(delete(Condition).where(Condition.keyword == OLD_CONDITION))
