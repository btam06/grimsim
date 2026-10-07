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
        ap=weapon.ap,
        attacks=weapon.attacks,
        skill=weapon.skill,
        weapon_type=weapon.weapon_type,
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


@router.put("/{weapon_id}", response_model=WeaponOut)
async def update_weapon(
    weapon_id: int, payload: WeaponIn, session: AsyncSession = Depends(get_session)
):
    weapon = (
        await session.execute(
            select(Weapon).options(selectinload(Weapon.abilities)).where(Weapon.id == weapon_id)
        )
    ).scalar_one_or_none()
    if weapon is None:
        raise HTTPException(status_code=404, detail="weapon not found")

    abilities: list[WeaponAbility] = []
    if payload.ability_ids:
        result = await session.execute(
            select(WeaponAbility).where(WeaponAbility.id.in_(payload.ability_ids))
        )
        abilities = list(result.scalars().all())
        if len(abilities) != len(set(payload.ability_ids)):
            raise HTTPException(status_code=400, detail="one or more ability_ids not found")

    weapon.name = payload.name
    weapon.model_id = payload.model_id
    weapon.damage = payload.damage
    weapon.range = payload.range
    weapon.strength = payload.strength
    weapon.ap = payload.ap
    weapon.attacks = payload.attacks
    weapon.skill = payload.skill
    weapon.weapon_type = payload.weapon_type
    weapon.abilities = abilities

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid model_id") from exc
    return _to_out(weapon)


@router.delete("/{weapon_id}", status_code=204)
async def delete_weapon(weapon_id: int, session: AsyncSession = Depends(get_session)):
    weapon = (
        await session.execute(select(Weapon).where(Weapon.id == weapon_id))
    ).scalar_one_or_none()
    if weapon is None:
        raise HTTPException(status_code=404, detail="weapon not found")

    await session.delete(weapon)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="cannot delete weapon: it is currently equipped by one or more units",
        ) from exc
