from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import ArmyList, Detachment, Unit
from app.schemas import ArmyListIn, ArmyListOut

router = APIRouter(prefix="/lists", tags=["lists"])


def _to_out(army_list: ArmyList) -> ArmyListOut:
    return ArmyListOut(
        id=army_list.id,
        name=army_list.name,
        points_limit=army_list.points_limit,
        faction_id=army_list.faction_id,
        detachment_ids=[d.id for d in army_list.detachments],
    )


async def _build_detachments(
    session: AsyncSession, detachment_ids: list[int], faction_id: int
) -> list[Detachment]:
    if not detachment_ids:
        return []
    result = await session.execute(select(Detachment).where(Detachment.id.in_(detachment_ids)))
    detachments = list(result.scalars().all())
    if len(detachments) != len(set(detachment_ids)):
        raise HTTPException(status_code=400, detail="one or more detachment_ids not found")
    if any(d.faction_id != faction_id for d in detachments):
        raise HTTPException(
            status_code=400, detail="detachment does not belong to the selected faction"
        )
    return detachments


@router.get("", response_model=list[ArmyListOut])
async def list_lists(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(ArmyList).options(selectinload(ArmyList.detachments)).order_by(ArmyList.id)
    )
    return [_to_out(army_list) for army_list in result.scalars().all()]


@router.post("", response_model=ArmyListOut, status_code=201)
async def create_list(payload: ArmyListIn, session: AsyncSession = Depends(get_session)):
    detachments = await _build_detachments(session, payload.detachment_ids, payload.faction_id)

    army_list = ArmyList(
        name=payload.name,
        points_limit=payload.points_limit,
        faction_id=payload.faction_id,
        detachments=detachments,
    )
    session.add(army_list)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc
    return _to_out(army_list)


@router.put("/{list_id}", response_model=ArmyListOut)
async def update_list(
    list_id: int, payload: ArmyListIn, session: AsyncSession = Depends(get_session)
):
    army_list = (
        await session.execute(
            select(ArmyList)
            .options(selectinload(ArmyList.detachments))
            .where(ArmyList.id == list_id)
        )
    ).scalar_one_or_none()
    if army_list is None:
        raise HTTPException(status_code=404, detail="list not found")

    detachments = await _build_detachments(session, payload.detachment_ids, payload.faction_id)

    army_list.name = payload.name
    army_list.points_limit = payload.points_limit
    army_list.faction_id = payload.faction_id
    army_list.detachments = detachments

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc
    return _to_out(army_list)


@router.delete("/{list_id}", status_code=204)
async def delete_list(list_id: int, session: AsyncSession = Depends(get_session)):
    army_list = (
        await session.execute(select(ArmyList).where(ArmyList.id == list_id))
    ).scalar_one_or_none()
    if army_list is None:
        raise HTTPException(status_code=404, detail="list not found")

    await session.execute(update(Unit).where(Unit.list_id == list_id).values(list_id=None))
    await session.delete(army_list)
    await session.commit()
