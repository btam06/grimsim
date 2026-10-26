from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.migrations import run_all
from app.models import Condition, Disposition, Effect, Stratagem


async def test_reconnaissance_renamed_in_place(session: AsyncSession):
    old = Disposition(name="Reconnaisance")
    session.add(old)
    await session.commit()
    old_id = old.id

    await run_all(session)
    # Again: nothing more to do.
    await run_all(session)

    rows = (
        await session.execute(
            select(Disposition.id, Disposition.name).where(
                Disposition.name.in_(["Reconnaisance", "Reconnaissance"])
            )
        )
    ).all()
    assert rows == [(old_id, "Reconnaissance")]


async def test_hellfire_rounds_loses_its_old_condition(session: AsyncSession):
    old = Condition(keyword="hellfire_anti_non_vehicle_4", name="Old", description="Old")
    effect = Effect(keyword="force_critical_wound", name="Force", description="Force")
    stratagem = Stratagem(name="Hellfire Rounds", cp=1, is_core=True)
    stratagem.conditions = [old]
    stratagem.effects = [effect]
    session.add(stratagem)
    await session.commit()

    await run_all(session)

    session.expire_all()
    stratagem = (
        await session.execute(
            select(Stratagem)
            .options(selectinload(Stratagem.conditions), selectinload(Stratagem.effects))
            .where(Stratagem.name == "Hellfire Rounds")
        )
    ).scalar_one()
    # Cleared, for the stratagem seed to fill in again.
    assert stratagem.conditions == [] and stratagem.effects == []
    keywords = (await session.execute(select(Condition.keyword))).scalars().all()
    assert "hellfire_anti_non_vehicle_4" not in keywords
