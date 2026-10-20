from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import BaseSize
from app.schemas import BaseSizeIn, BaseSizeOut

router = APIRouter(prefix="/base-sizes", tags=["base-sizes"])


@router.get("", response_model=list[BaseSizeOut])
async def list_base_sizes(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(BaseSize).order_by(BaseSize.id))
    return result.scalars().all()


@router.post("", response_model=BaseSizeOut, status_code=201)
async def create_base_size(payload: BaseSizeIn, session: AsyncSession = Depends(get_session)):
    base_size = BaseSize(name=payload.name.strip())
    session.add(base_size)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="base size already exists") from exc
    return base_size
