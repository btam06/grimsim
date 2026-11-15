from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Faction, FactionUnit, LeaderBodyguard
from app.schemas import (
    FactionUnitIn, FactionUnitOut, LoadoutChoiceOut, LoadoutItemsOut, LoadoutOptionOut,
    LoadoutOut, LoadoutPartOut, LoadoutVariantOut,
)
from app.services.list_building import loadouts

router = APIRouter(prefix="/faction-units", tags=["faction-units"])


@router.get("", response_model=list[FactionUnitOut])
async def list_faction_units(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(FactionUnit).order_by(FactionUnit.id))
    return result.scalars().all()


@router.post("", response_model=FactionUnitOut, status_code=201)
async def create_faction_unit(
    payload: FactionUnitIn, session: AsyncSession = Depends(get_session)
):
    faction = (
        await session.execute(select(Faction).where(Faction.id == payload.faction_id))
    ).scalar_one_or_none()
    if faction is None:
        raise HTTPException(status_code=400, detail="invalid faction_id")

    faction_unit = FactionUnit(name=payload.name, faction_id=payload.faction_id)
    faction_unit.bodyguard_links = await _bodyguard_links(session, payload.bodyguard_ids)
    session.add(faction_unit)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400, detail="faction unit name must be unique within its faction"
        ) from exc
    return faction_unit


async def _bodyguard_links(session: AsyncSession, ids: list[int]) -> list[LeaderBodyguard]:
    found = set(
        (await session.execute(select(FactionUnit.id).where(FactionUnit.id.in_(ids)))).scalars()
    )
    if found != set(ids):
        raise HTTPException(status_code=400, detail="one or more bodyguard_ids not found")
    return [LeaderBodyguard(bodyguard_id=i) for i in sorted(found)]


@router.get("/{faction_unit_id}/loadout", response_model=LoadoutOut)
async def get_loadout(faction_unit_id: int, session: AsyncSession = Depends(get_session)):
    # What the datasheet's units can be made of (its datasheets.json
    # composition and wargear options).
    if await session.get(FactionUnit, faction_unit_id) is None:
        raise HTTPException(status_code=404, detail="faction unit not found")
    loadout = await loadouts.loadout_for(session, faction_unit_id)
    if loadout is None:
        return LoadoutOut(model_ids=[], composition=[], options=[], auto=False)

    def items(model, counter) -> dict:
        weapon_ids, wargear_ids = loadouts.ids_for(model, counter)
        return {"weapon_ids": weapon_ids, "wargear_ids": wargear_ids}

    return LoadoutOut(
        model_ids=[m.id for m in loadout.models],
        composition=[
            LoadoutPartOut(model_id=p.model.id, min=p.min, max=p.max, **items(p.model, p.equipped))
            for p in loadout.sergeant_first()
        ],
        options=[
            LoadoutOptionOut(
                index=o.index, model_id=o.model.id, label=o.label,
                replace=LoadoutItemsOut(**items(o.model, o.replace)),
                requires=LoadoutItemsOut(**items(o.model, o.requires)),
                choices=[
                    LoadoutChoiceOut(name=" and ".join(names), **items(o.model, choice))
                    for choice, names in zip(o.choices, o.choice_names)
                ],
                max=o.max, per=o.per,
            )
            for o in loadout.options
        ],
        variants=[
            LoadoutVariantOut(
                model_id=v.model.id, name=v.name, options=sorted(v.used), **items(v.model, v.items)
            )
            for part in loadout.sergeant_first()
            for v in loadout_variants(loadout, part)
        ],
        auto=loadout.auto,
    )


def loadout_variants(loadout, part):
    return loadouts.variants(part, [o for o in loadout.options if o.model.id == part.model.id])


@router.put("/{faction_unit_id}/bodyguards", response_model=FactionUnitOut)
async def set_bodyguards(
    faction_unit_id: int, bodyguard_ids: list[int], session: AsyncSession = Depends(get_session)
):
    # The bodyguard datasheets a leader or support datasheet can lead.
    faction_unit = await session.get(FactionUnit, faction_unit_id)
    if faction_unit is None:
        raise HTTPException(status_code=404, detail="faction unit not found")
    faction_unit.bodyguard_links = await _bodyguard_links(session, bodyguard_ids)
    await session.commit()
    await session.refresh(faction_unit, ["bodyguard_links"])
    return faction_unit


@router.delete("/{faction_unit_id}", status_code=204)
async def delete_faction_unit(
    faction_unit_id: int, session: AsyncSession = Depends(get_session)
):
    faction_unit = (
        await session.execute(select(FactionUnit).where(FactionUnit.id == faction_unit_id))
    ).scalar_one_or_none()
    if faction_unit is None:
        raise HTTPException(status_code=404, detail="faction unit not found")

    await session.delete(faction_unit)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="cannot delete faction unit: it is still referenced by one or more units",
        ) from exc
