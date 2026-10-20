from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import (
    ArmyList,
    Enhancement,
    FactionUnit,
    Model,
    Unit,
    UnitModel,
    Wargear,
    Weapon,
)
from app.routers.enhancements import used_in_list
from app.schemas import UnitIn, UnitModelIn, UnitModelOut, UnitOut
from app.services import enhancements as enhancement_rules

router = APIRouter(prefix="/units", tags=["units"])


def _unit_model_to_out(unit_model: UnitModel) -> UnitModelOut:
    return UnitModelOut(
        id=unit_model.id,
        model_id=unit_model.model_id,
        weapon_ids=[w.id for w in unit_model.weapons],
        wargear_ids=[g.id for g in unit_model.wargear],
        enhancement_id=unit_model.enhancement.id if unit_model.enhancement else None,
    )


def _to_out(unit: Unit) -> UnitOut:
    return UnitOut(
        id=unit.id,
        faction_unit_id=unit.faction_unit_id,
        points=unit.points,
        list_id=unit.list_id,
        unit_models=[_unit_model_to_out(um) for um in unit.unit_models],
        upgrade_id=unit.upgrade.id if unit.upgrade else None,
    )


async def _build_unit_models(
    session: AsyncSession, entries: list[UnitModelIn]
) -> tuple[list[UnitModel], list[Model]]:
    # The unit models, and the Model (with keywords) for each.
    unit_models: list[UnitModel] = []
    models: list[Model] = []
    for entry in entries:
        model = (
            await session.execute(
                select(Model)
                .options(selectinload(Model.keywords))
                .where(Model.id == entry.model_id)
            )
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

        models.append(model)
        unit_models.append(
            UnitModel(
                model_id=entry.model_id,
                weapons=weapons,
                wargear=wargear,
                enhancement=None,  # set by _apply_enhancements
            )
        )

    return unit_models, models


async def _apply_enhancements(
    session: AsyncSession,
    payload: UnitIn,
    unit_models: list[UnitModel],
    models: list[Model],
    unit_id: int | None,
) -> Enhancement | None:
    # Puts each model's enhancement on its unit model, and returns the unit's
    # upgrade - checking that the unit is in a list that has taken their
    # detachments, each goes on an applicable model/unit, and none is taken
    # twice in the list (or within this unit).
    ids = [e.enhancement_id for e in payload.unit_models if e.enhancement_id is not None]
    if payload.upgrade_id is not None:
        ids.append(payload.upgrade_id)
    if not ids:
        return None
    if payload.list_id is None:
        raise HTTPException(
            status_code=400, detail="enhancements and upgrades need the unit to be in a list"
        )
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="an enhancement can only be taken once")
    enhancements = {
        e.id: e
        for e in (
            await session.execute(select(Enhancement).where(Enhancement.id.in_(ids)))
        ).scalars()
    }
    if set(ids) - set(enhancements):
        raise HTTPException(status_code=400, detail="one or more enhancements not found")

    army_list = (
        await session.execute(
            select(ArmyList)
            .options(selectinload(ArmyList.detachments))
            .where(ArmyList.id == payload.list_id)
        )
    ).scalar_one()
    detachment_ids = {d.id for d in army_list.detachments}
    taken = set(ids) & await used_in_list(session, payload.list_id, unit_id)
    if taken:
        names = ", ".join(sorted(enhancements[i].name for i in taken))
        raise HTTPException(
            status_code=400, detail=f"already taken by another unit in this list: {names}"
        )

    for entry, unit_model, model in zip(payload.unit_models, unit_models, models):
        if entry.enhancement_id is None:
            continue
        enhancement = enhancements[entry.enhancement_id]
        reason = enhancement_rules.model_unavailable_reason(enhancement, model, detachment_ids)
        if reason:
            raise HTTPException(
                status_code=400,
                detail=f"'{enhancement.name}' {reason} ({model.name} can't carry it)",
            )
        unit_model.enhancement = enhancement

    if payload.upgrade_id is None:
        return None
    upgrade = enhancements[payload.upgrade_id]
    reason = enhancement_rules.unit_unavailable_reason(upgrade, models, detachment_ids)
    if reason:
        raise HTTPException(status_code=400, detail=f"'{upgrade.name}' {reason}")
    return upgrade


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
    faction_unit = (
        await session.execute(
            select(FactionUnit).where(FactionUnit.id == payload.faction_unit_id)
        )
    ).scalar_one_or_none()
    if faction_unit is None:
        raise HTTPException(status_code=400, detail="invalid faction_unit_id")

    if payload.list_id is not None:
        army_list = (
            await session.execute(select(ArmyList).where(ArmyList.id == payload.list_id))
        ).scalar_one_or_none()
        if army_list is None:
            raise HTTPException(status_code=400, detail="invalid list_id")

    unit_models, models = await _build_unit_models(session, payload.unit_models)
    upgrade = await _apply_enhancements(session, payload, unit_models, models, None)
    unit = Unit(
        faction_unit_id=payload.faction_unit_id,
        points=payload.points,
        list_id=payload.list_id,
        unit_models=unit_models,
        upgrade=upgrade,
    )
    session.add(unit)
    await session.commit()
    return _to_out(unit)


@router.put("/{unit_id}", response_model=UnitOut)
async def update_unit(
    unit_id: int, payload: UnitIn, session: AsyncSession = Depends(get_session)
):
    unit = (
        await session.execute(
            select(Unit).options(selectinload(Unit.unit_models)).where(Unit.id == unit_id)
        )
    ).scalar_one_or_none()
    if unit is None:
        raise HTTPException(status_code=404, detail="unit not found")

    faction_unit = (
        await session.execute(
            select(FactionUnit).where(FactionUnit.id == payload.faction_unit_id)
        )
    ).scalar_one_or_none()
    if faction_unit is None:
        raise HTTPException(status_code=400, detail="invalid faction_unit_id")

    if payload.list_id is not None:
        army_list = (
            await session.execute(select(ArmyList).where(ArmyList.id == payload.list_id))
        ).scalar_one_or_none()
        if army_list is None:
            raise HTTPException(status_code=400, detail="invalid list_id")

    new_unit_models, models = await _build_unit_models(session, payload.unit_models)
    upgrade = await _apply_enhancements(session, payload, new_unit_models, models, unit_id)

    unit.faction_unit_id = payload.faction_unit_id
    unit.points = payload.points
    unit.list_id = payload.list_id
    unit.unit_models = new_unit_models
    unit.upgrade = upgrade

    await session.commit()

    result = await session.execute(
        select(Unit)
        .options(
            selectinload(Unit.unit_models).selectinload(UnitModel.weapons),
            selectinload(Unit.unit_models).selectinload(UnitModel.wargear),
        )
        .where(Unit.id == unit_id)
    )
    unit = result.scalar_one()
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
