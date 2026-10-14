from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Wargear, WargearAbility
from app.schemas import WargearIn, WargearOut

router = APIRouter(prefix="/wargear", tags=["wargear"])


def _to_out(item: Wargear) -> WargearOut:
    return WargearOut(
        id=item.id,
        name=item.name,
        model_id=item.model_id,
        description=item.description,
        ability_ids=[ability.id for ability in item.abilities],
    )


@router.get("", response_model=list[WargearOut])
async def list_wargear(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Wargear).options(selectinload(Wargear.abilities)).order_by(Wargear.id)
    )
    return [_to_out(item) for item in result.scalars().all()]


@router.post("", response_model=WargearOut, status_code=201)
async def create_wargear(payload: WargearIn, session: AsyncSession = Depends(get_session)):
    abilities: list[WargearAbility] = []
    if payload.ability_ids:
        result = await session.execute(
            select(WargearAbility).where(WargearAbility.id.in_(payload.ability_ids))
        )
        abilities = list(result.scalars().all())
        if len(abilities) != len(set(payload.ability_ids)):
            raise HTTPException(status_code=400, detail="one or more ability_ids not found")

    item = Wargear(**payload.model_dump(exclude={"ability_ids"}), abilities=abilities)
    session.add(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid model_id") from exc
    return _to_out(item)


@router.put("/{wargear_id}", response_model=WargearOut)
async def update_wargear(
    wargear_id: int, payload: WargearIn, session: AsyncSession = Depends(get_session)
):
    item = (
        await session.execute(
            select(Wargear).options(selectinload(Wargear.abilities)).where(Wargear.id == wargear_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="wargear not found")

    abilities: list[WargearAbility] = []
    if payload.ability_ids:
        result = await session.execute(
            select(WargearAbility).where(WargearAbility.id.in_(payload.ability_ids))
        )
        abilities = list(result.scalars().all())
        if len(abilities) != len(set(payload.ability_ids)):
            raise HTTPException(status_code=400, detail="one or more ability_ids not found")

    item.name = payload.name
    item.model_id = payload.model_id
    item.description = payload.description
    item.abilities = abilities

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid model_id") from exc
    return _to_out(item)


@router.delete("/{wargear_id}", status_code=204)
async def delete_wargear(wargear_id: int, session: AsyncSession = Depends(get_session)):
    item = (
        await session.execute(select(Wargear).where(Wargear.id == wargear_id))
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="wargear not found")

    await session.delete(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="cannot delete wargear: it is currently equipped by one or more units",
        ) from exc
