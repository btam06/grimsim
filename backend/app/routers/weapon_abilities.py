from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import WeaponAbility
from app.schemas import WeaponAbilityIn, WeaponAbilityOut

router = APIRouter(prefix="/weapon-abilities", tags=["weapon-abilities"])


@router.get("", response_model=list[WeaponAbilityOut])
async def list_weapon_abilities(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(WeaponAbility).order_by(WeaponAbility.id))
    return result.scalars().all()


@router.post("", response_model=WeaponAbilityOut, status_code=201)
async def create_weapon_ability(
    payload: WeaponAbilityIn, session: AsyncSession = Depends(get_session)
):
    ability = WeaponAbility(**payload.model_dump())
    session.add(ability)
    await session.commit()
    return ability
