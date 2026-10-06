from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Disposition
from app.schemas import DispositionIn, DispositionOut

router = APIRouter(prefix="/dispositions", tags=["dispositions"])


@router.get("", response_model=list[DispositionOut])
async def list_dispositions(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Disposition).order_by(Disposition.id))
    return result.scalars().all()


@router.post("", response_model=DispositionOut, status_code=201)
async def create_disposition(payload: DispositionIn, session: AsyncSession = Depends(get_session)):
    disposition = Disposition(**payload.model_dump())
    session.add(disposition)
    await session.commit()
    return disposition
