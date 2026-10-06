from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Faction
from app.schemas import FactionIn, FactionOut

router = APIRouter(prefix="/factions", tags=["factions"])


@router.get("", response_model=list[FactionOut])
async def list_factions(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Faction).order_by(Faction.id))
    return result.scalars().all()


@router.post("", response_model=FactionOut, status_code=201)
async def create_faction(payload: FactionIn, session: AsyncSession = Depends(get_session)):
    faction = Faction(**payload.model_dump())
    session.add(faction)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="faction name must be unique") from exc
    return faction


@router.delete("/{faction_id}", status_code=204)
async def delete_faction(faction_id: int, session: AsyncSession = Depends(get_session)):
    faction = (
        await session.execute(select(Faction).where(Faction.id == faction_id))
    ).scalar_one_or_none()
    if faction is None:
        raise HTTPException(status_code=404, detail="faction not found")

    await session.delete(faction)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="cannot delete faction: it is still referenced by models, detachments, or lists",
        ) from exc
