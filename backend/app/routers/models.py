from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Model
from app.schemas import ModelIn, ModelOut

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Model).order_by(Model.id))
    return result.scalars().all()


@router.post("", response_model=ModelOut, status_code=201)
async def create_model(payload: ModelIn, session: AsyncSession = Depends(get_session)):
    model = Model(**payload.model_dump())
    session.add(model)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc
    return model
