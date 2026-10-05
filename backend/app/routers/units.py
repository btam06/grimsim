from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Model, Unit
from app.schemas import UnitIn, UnitOut

router = APIRouter(prefix="/units", tags=["units"])


def _to_out(unit: Unit) -> UnitOut:
    return UnitOut(id=unit.id, name=unit.name, model_ids=[model.id for model in unit.models])


@router.get("", response_model=list[UnitOut])
async def list_units(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Unit).options(selectinload(Unit.models)).order_by(Unit.id)
    )
    return [_to_out(unit) for unit in result.scalars().all()]


@router.post("", response_model=UnitOut, status_code=201)
async def create_unit(payload: UnitIn, session: AsyncSession = Depends(get_session)):
    models: list[Model] = []
    if payload.model_ids:
        result = await session.execute(select(Model).where(Model.id.in_(payload.model_ids)))
        models = list(result.scalars().all())
        if len(models) != len(set(payload.model_ids)):
            raise HTTPException(status_code=400, detail="one or more model_ids not found")

    unit = Unit(name=payload.name, models=models)
    session.add(unit)
    await session.commit()
    return _to_out(unit)
