from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Faction, FactionUnit
from app.schemas import FactionUnitIn, FactionUnitOut

router = APIRouter(prefix="/faction-units", tags=["faction-units"])


@router.get("", response_model=list[FactionUnitOut])
async def list_faction_units(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(FactionUnit).order_by(FactionUnit.id))
    return result.scalars().all()


@router.post("", response_model=FactionUnitOut, status_code=201)
async def create_faction_unit(
    payload: FactionUnitIn, session: AsyncSession = Depends(get_session)
):
    faction = (
        await session.execute(select(Faction).where(Faction.id == payload.faction_id))
    ).scalar_one_or_none()
    if faction is None:
        raise HTTPException(status_code=400, detail="invalid faction_id")

    faction_unit = FactionUnit(**payload.model_dump())
    session.add(faction_unit)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400, detail="faction unit name must be unique within its faction"
        ) from exc
    return faction_unit


@router.delete("/{faction_unit_id}", status_code=204)
async def delete_faction_unit(
    faction_unit_id: int, session: AsyncSession = Depends(get_session)
):
    faction_unit = (
        await session.execute(select(FactionUnit).where(FactionUnit.id == faction_unit_id))
    ).scalar_one_or_none()
    if faction_unit is None:
        raise HTTPException(status_code=404, detail="faction unit not found")

    await session.delete(faction_unit)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="cannot delete faction unit: it is still referenced by one or more units",
        ) from exc
