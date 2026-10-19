from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Disposition, PrimaryMission, SecondaryMission
from app.schemas import (
    PrimaryMissionIn,
    PrimaryMissionOut,
    SecondaryMissionIn,
    SecondaryMissionOut,
)

secondary_router = APIRouter(prefix="/secondary-missions", tags=["secondary-missions"])
primary_router = APIRouter(prefix="/primary-missions", tags=["primary-missions"])


@secondary_router.get("", response_model=list[SecondaryMissionOut])
async def list_secondary_missions(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(SecondaryMission).order_by(SecondaryMission.id))
    return result.scalars().all()


@secondary_router.post("", response_model=SecondaryMissionOut, status_code=201)
async def create_secondary_mission(
    payload: SecondaryMissionIn, session: AsyncSession = Depends(get_session)
):
    mission = SecondaryMission(**payload.model_dump())
    session.add(mission)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400, detail="secondary mission name must be unique"
        ) from exc
    return mission


@secondary_router.delete("/{mission_id}", status_code=204)
async def delete_secondary_mission(
    mission_id: int, session: AsyncSession = Depends(get_session)
):
    mission = (
        await session.execute(select(SecondaryMission).where(SecondaryMission.id == mission_id))
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="secondary mission not found")
    await session.delete(mission)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400, detail="cannot delete secondary mission: it has been used in a game"
        ) from exc


@primary_router.get("", response_model=list[PrimaryMissionOut])
async def list_primary_missions(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(PrimaryMission).order_by(PrimaryMission.id))
    return result.scalars().all()


@primary_router.post("", response_model=PrimaryMissionOut, status_code=201)
async def create_primary_mission(
    payload: PrimaryMissionIn, session: AsyncSession = Depends(get_session)
):
    ids = {payload.player_disposition_id, payload.opponent_disposition_id}
    found = (
        await session.execute(select(Disposition.id).where(Disposition.id.in_(ids)))
    ).scalars().all()
    if len(found) != len(ids):
        raise HTTPException(status_code=400, detail="invalid disposition id")

    mission = PrimaryMission(**payload.model_dump())
    session.add(mission)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="there is already a primary mission for that pair of dispositions",
        ) from exc
    return mission


@primary_router.delete("/{mission_id}", status_code=204)
async def delete_primary_mission(mission_id: int, session: AsyncSession = Depends(get_session)):
    mission = (
        await session.execute(select(PrimaryMission).where(PrimaryMission.id == mission_id))
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="primary mission not found")
    await session.delete(mission)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400, detail="cannot delete primary mission: it has been used in a game"
        ) from exc
