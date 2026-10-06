from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import ArmyList, Model, Unit, UnitModel, Wargear, Weapon
from app.schemas import UnitIn, UnitModelIn, UnitModelOut, UnitOut

router = APIRouter(prefix="/units", tags=["units"])


def _unit_model_to_out(unit_model: UnitModel) -> UnitModelOut:
    return UnitModelOut(
        id=unit_model.id,
        model_id=unit_model.model_id,
        weapon_ids=[w.id for w in unit_model.weapons],
        wargear_ids=[g.id for g in unit_model.wargear],
    )


def _to_out(unit: Unit) -> UnitOut:
    return UnitOut(
        id=unit.id,
        name=unit.name,
        points=unit.points,
        list_id=unit.list_id,
        unit_models=[_unit_model_to_out(um) for um in unit.unit_models],
    )


async def _build_unit_models(
    session: AsyncSession, entries: list[UnitModelIn]
) -> list[UnitModel]:
    unit_models: list[UnitModel] = []
    for entry in entries:
        model = (
            await session.execute(select(Model).where(Model.id == entry.model_id))
        ).scalar_one_or_none()
        if model is None:
            raise HTTPException(
                status_code=400, detail=f"model_id {entry.model_id} not found"
            )

        weapons: list[Weapon] = []
        if entry.weapon_ids:
            result = await session.execute(
                select(Weapon).where(Weapon.id.in_(entry.weapon_ids))
            )
            weapons = list(result.scalars().all())
            if len(weapons) != len(set(entry.weapon_ids)):
                raise HTTPException(status_code=400, detail="one or more weapon_ids not found")
            if any(w.model_id != entry.model_id for w in weapons):
                raise HTTPException(
                    status_code=400, detail="weapon does not belong to the selected model"
                )

        wargear: list[Wargear] = []
        if entry.wargear_ids:
            result = await session.execute(
                select(Wargear).where(Wargear.id.in_(entry.wargear_ids))
            )
            wargear = list(result.scalars().all())
            if len(wargear) != len(set(entry.wargear_ids)):
                raise HTTPException(status_code=400, detail="one or more wargear_ids not found")
            if any(g.model_id != entry.model_id for g in wargear):
                raise HTTPException(
                    status_code=400, detail="wargear does not belong to the selected model"
                )

        unit_models.append(UnitModel(model_id=entry.model_id, weapons=weapons, wargear=wargear))

    return unit_models


@router.get("", response_model=list[UnitOut])
async def list_units(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Unit)
        .options(
            selectinload(Unit.unit_models).selectinload(UnitModel.weapons),
            selectinload(Unit.unit_models).selectinload(UnitModel.wargear),
        )
        .order_by(Unit.id)
    )
    return [_to_out(unit) for unit in result.scalars().all()]


@router.post("", response_model=UnitOut, status_code=201)
async def create_unit(payload: UnitIn, session: AsyncSession = Depends(get_session)):
    if payload.list_id is not None:
        army_list = (
            await session.execute(select(ArmyList).where(ArmyList.id == payload.list_id))
        ).scalar_one_or_none()
        if army_list is None:
            raise HTTPException(status_code=400, detail="invalid list_id")

    unit_models = await _build_unit_models(session, payload.unit_models)
    unit = Unit(
        name=payload.name,
        points=payload.points,
        list_id=payload.list_id,
        unit_models=unit_models,
    )
    session.add(unit)
    await session.commit()
    return _to_out(unit)


@router.delete("/{unit_id}", status_code=204)
async def delete_unit(unit_id: int, session: AsyncSession = Depends(get_session)):
    unit = (
        await session.execute(select(Unit).where(Unit.id == unit_id))
    ).scalar_one_or_none()
    if unit is None:
        raise HTTPException(status_code=404, detail="unit not found")

    await session.delete(unit)
    await session.commit()
