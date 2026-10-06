from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import ArmyList, Detachment, Unit
from app.schemas import ArmyListIn, ArmyListOut

router = APIRouter(prefix="/lists", tags=["lists"])


def _to_out(army_list: ArmyList, unit_ids: list[int]) -> ArmyListOut:
    return ArmyListOut(
        id=army_list.id,
        name=army_list.name,
        points_limit=army_list.points_limit,
        faction_id=army_list.faction_id,
        detachment_id=army_list.detachment_id,
        unit_ids=unit_ids,
    )


@router.get("", response_model=list[ArmyListOut])
async def list_lists(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(ArmyList).options(selectinload(ArmyList.units)).order_by(ArmyList.id)
    )
    return [
        _to_out(army_list, [u.id for u in army_list.units])
        for army_list in result.scalars().all()
    ]


@router.post("", response_model=ArmyListOut, status_code=201)
async def create_list(payload: ArmyListIn, session: AsyncSession = Depends(get_session)):
    detachment = (
        await session.execute(select(Detachment).where(Detachment.id == payload.detachment_id))
    ).scalar_one_or_none()
    if detachment is None:
        raise HTTPException(status_code=400, detail="invalid detachment_id")
    if detachment.faction_id != payload.faction_id:
        raise HTTPException(
            status_code=400, detail="detachment does not belong to the selected faction"
        )

    army_list = ArmyList(
        name=payload.name,
        points_limit=payload.points_limit,
        faction_id=payload.faction_id,
        detachment_id=payload.detachment_id,
    )
    session.add(army_list)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc

    units: list[Unit] = []
    if payload.unit_ids:
        result = await session.execute(select(Unit).where(Unit.id.in_(payload.unit_ids)))
        units = list(result.scalars().all())
        if len(units) != len(set(payload.unit_ids)):
            await session.rollback()
            raise HTTPException(status_code=400, detail="one or more unit_ids not found")
        for unit in units:
            unit.list_id = army_list.id

    await session.commit()
    return _to_out(army_list, [u.id for u in units])


@router.put("/{list_id}", response_model=ArmyListOut)
async def update_list(
    list_id: int, payload: ArmyListIn, session: AsyncSession = Depends(get_session)
):
    army_list = (
        await session.execute(select(ArmyList).where(ArmyList.id == list_id))
    ).scalar_one_or_none()
    if army_list is None:
        raise HTTPException(status_code=404, detail="list not found")

    detachment = (
        await session.execute(select(Detachment).where(Detachment.id == payload.detachment_id))
    ).scalar_one_or_none()
    if detachment is None:
        raise HTTPException(status_code=400, detail="invalid detachment_id")
    if detachment.faction_id != payload.faction_id:
        raise HTTPException(
            status_code=400, detail="detachment does not belong to the selected faction"
        )

    army_list.name = payload.name
    army_list.points_limit = payload.points_limit
    army_list.faction_id = payload.faction_id
    army_list.detachment_id = payload.detachment_id

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc

    if payload.unit_ids:
        result = await session.execute(select(Unit).where(Unit.id.in_(payload.unit_ids)))
        new_units = list(result.scalars().all())
        if len(new_units) != len(set(payload.unit_ids)):
            await session.rollback()
            raise HTTPException(status_code=400, detail="one or more unit_ids not found")
        for unit in new_units:
            unit.list_id = army_list.id

    await session.commit()

    result = await session.execute(
        select(ArmyList).options(selectinload(ArmyList.units)).where(ArmyList.id == list_id)
    )
    army_list = result.scalar_one()
    return _to_out(army_list, [u.id for u in army_list.units])
