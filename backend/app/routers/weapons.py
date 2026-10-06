from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Weapon, WeaponAbility
from app.schemas import WeaponIn, WeaponOut

router = APIRouter(prefix="/weapons", tags=["weapons"])


def _to_out(weapon: Weapon) -> WeaponOut:
    return WeaponOut(
        id=weapon.id,
        name=weapon.name,
        model_id=weapon.model_id,
        damage=weapon.damage,
        range=weapon.range,
        strength=weapon.strength,
        attacks=weapon.attacks,
        ability_ids=[ability.id for ability in weapon.abilities],
    )


@router.get("", response_model=list[WeaponOut])
async def list_weapons(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Weapon).options(selectinload(Weapon.abilities)).order_by(Weapon.id)
    )
    return [_to_out(weapon) for weapon in result.scalars().all()]


@router.post("", response_model=WeaponOut, status_code=201)
async def create_weapon(payload: WeaponIn, session: AsyncSession = Depends(get_session)):
    abilities: list[WeaponAbility] = []
    if payload.ability_ids:
        result = await session.execute(
            select(WeaponAbility).where(WeaponAbility.id.in_(payload.ability_ids))
        )
        abilities = list(result.scalars().all())
        if len(abilities) != len(set(payload.ability_ids)):
            raise HTTPException(status_code=400, detail="one or more ability_ids not found")

    weapon = Weapon(**payload.model_dump(exclude={"ability_ids"}), abilities=abilities)
    session.add(weapon)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid model_id") from exc
    return _to_out(weapon)
