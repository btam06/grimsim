from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import DatasheetAbility, Keyword, Model, Wargear
from app.schemas import ModelIn, ModelOut

router = APIRouter(prefix="/models", tags=["models"])


def _to_out(
    model: Model, ability_ids: list[int], wargear_ids: list[int], keyword_ids: list[int]
) -> ModelOut:
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
        keyword_ids=keyword_ids,
    )


async def _build_keywords(session: AsyncSession, keyword_ids: list[int]) -> list[Keyword]:
    if not keyword_ids:
        return []
    result = await session.execute(select(Keyword).where(Keyword.id.in_(keyword_ids)))
    keywords = list(result.scalars().all())
    if len(keywords) != len(set(keyword_ids)):
        raise HTTPException(status_code=400, detail="one or more keyword_ids not found")
    return keywords


@router.get("", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Model)
        .options(
            selectinload(Model.abilities),
            selectinload(Model.wargear),
            selectinload(Model.keywords),
        )
        .order_by(Model.id)
    )
    return [
        _to_out(
            model,
            [a.id for a in model.abilities],
            [g.id for g in model.wargear],
            [k.id for k in model.keywords],
        )
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

    keywords = await _build_keywords(session, payload.keyword_ids)

    model = Model(
        **payload.model_dump(exclude={"ability_ids", "wargear_ids", "keyword_ids"}),
        abilities=abilities,
        keywords=keywords,
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
    return _to_out(
        model, [a.id for a in abilities], [g.id for g in wargear], [k.id for k in keywords]
    )


@router.put("/{model_id}", response_model=ModelOut)
async def update_model(
    model_id: int, payload: ModelIn, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Model)
        .options(selectinload(Model.abilities), selectinload(Model.keywords))
        .where(Model.id == model_id)
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

    keywords = await _build_keywords(session, payload.keyword_ids)

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
    model.keywords = keywords

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
        .options(
            selectinload(Model.abilities),
            selectinload(Model.wargear),
            selectinload(Model.keywords),
        )
        .where(Model.id == model_id)
    )
    model = result.scalar_one()
    return _to_out(
        model,
        [a.id for a in model.abilities],
        [g.id for g in model.wargear],
        [k.id for k in model.keywords],
    )
