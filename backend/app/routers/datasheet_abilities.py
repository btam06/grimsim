from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DatasheetAbility
from app.schemas import DatasheetAbilityIn, DatasheetAbilityOut

router = APIRouter(prefix="/datasheet-abilities", tags=["datasheet-abilities"])


@router.get("", response_model=list[DatasheetAbilityOut])
async def list_datasheet_abilities(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(DatasheetAbility).order_by(DatasheetAbility.id))
    return result.scalars().all()


@router.post("", response_model=DatasheetAbilityOut, status_code=201)
async def create_datasheet_ability(
    payload: DatasheetAbilityIn, session: AsyncSession = Depends(get_session)
):
    ability = DatasheetAbility(**payload.model_dump())
    session.add(ability)
    await session.commit()
    return ability
