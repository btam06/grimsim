from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Effect
from app.schemas import EffectOut

router = APIRouter(prefix="/effects", tags=["effects"])


@router.get("", response_model=list[EffectOut])
async def list_effects(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Effect).order_by(Effect.id))
    return result.scalars().all()
