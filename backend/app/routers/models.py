from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import DatasheetAbility, Model, Wargear
from app.schemas import ModelIn, ModelOut

router = APIRouter(prefix="/models", tags=["models"])


def _to_out(model: Model, ability_ids: list[int], wargear_ids: list[int]) -> ModelOut:
    return ModelOut(
        id=model.id,
        name=model.name,
        faction_id=model.faction_id,
        save=model.save,
        toughness=model.toughness,
        oc=model.oc,
        movement=model.movement,
        wounds=model.wounds,
        leadership=model.leadership,
        invulnerable=model.invulnerable,
        feel_no_pain=model.feel_no_pain,
        is_support=model.is_support,
        is_leader=model.is_leader,
        ability_ids=ability_ids,
        wargear_ids=wargear_ids,
    )


@router.get("", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Model)
        .options(selectinload(Model.abilities), selectinload(Model.wargear))
        .order_by(Model.id)
    )
    return [
        _to_out(model, [a.id for a in model.abilities], [g.id for g in model.wargear])
        for model in result.scalars().all()
    ]


@router.post("", response_model=ModelOut, status_code=201)
async def create_model(payload: ModelIn, session: AsyncSession = Depends(get_session)):
    abilities: list[DatasheetAbility] = []
    if payload.ability_ids:
        result = await session.execute(
            select(DatasheetAbility).where(DatasheetAbility.id.in_(payload.ability_ids))
        )
        abilities = list(result.scalars().all())
        if len(abilities) != len(set(payload.ability_ids)):
            raise HTTPException(status_code=400, detail="one or more ability_ids not found")

    model = Model(
        **payload.model_dump(exclude={"ability_ids", "wargear_ids"}),
        abilities=abilities,
    )
    session.add(model)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc

    wargear: list[Wargear] = []
    if payload.wargear_ids:
        result = await session.execute(select(Wargear).where(Wargear.id.in_(payload.wargear_ids)))
        wargear = list(result.scalars().all())
        if len(wargear) != len(set(payload.wargear_ids)):
            await session.rollback()
            raise HTTPException(status_code=400, detail="one or more wargear_ids not found")
        for item in wargear:
            item.model_id = model.id

    await session.commit()
    return _to_out(model, [a.id for a in abilities], [g.id for g in wargear])


@router.put("/{model_id}", response_model=ModelOut)
async def update_model(
    model_id: int, payload: ModelIn, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Model).options(selectinload(Model.abilities)).where(Model.id == model_id)
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")

    abilities: list[DatasheetAbility] = []
    if payload.ability_ids:
        result = await session.execute(
            select(DatasheetAbility).where(DatasheetAbility.id.in_(payload.ability_ids))
        )
        abilities = list(result.scalars().all())
        if len(abilities) != len(set(payload.ability_ids)):
            raise HTTPException(status_code=400, detail="one or more ability_ids not found")

    model.name = payload.name
    model.faction_id = payload.faction_id
    model.save = payload.save
    model.toughness = payload.toughness
    model.oc = payload.oc
    model.movement = payload.movement
    model.wounds = payload.wounds
    model.leadership = payload.leadership
    model.invulnerable = payload.invulnerable
    model.feel_no_pain = payload.feel_no_pain
    model.is_support = payload.is_support
    model.is_leader = payload.is_leader
    model.abilities = abilities

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc

    if payload.wargear_ids:
        result = await session.execute(select(Wargear).where(Wargear.id.in_(payload.wargear_ids)))
        new_wargear = list(result.scalars().all())
        if len(new_wargear) != len(set(payload.wargear_ids)):
            await session.rollback()
            raise HTTPException(status_code=400, detail="one or more wargear_ids not found")
        for item in new_wargear:
            item.model_id = model.id

    await session.commit()

    result = await session.execute(
        select(Model)
        .options(selectinload(Model.abilities), selectinload(Model.wargear))
        .where(Model.id == model_id)
    )
    model = result.scalar_one()
    return _to_out(model, [a.id for a in model.abilities], [g.id for g in model.wargear])
