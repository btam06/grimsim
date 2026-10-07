from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Condition
from app.schemas import ConditionOut

router = APIRouter(prefix="/conditions", tags=["conditions"])


@router.get("", response_model=list[ConditionOut])
async def list_conditions(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Condition).order_by(Condition.id))
    return result.scalars().all()
