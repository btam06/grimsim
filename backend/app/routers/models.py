from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import BaseSize, DatasheetAbility, FactionAbility, Keyword, Model, Wargear
from app.schemas import ModelIn, ModelOut

router = APIRouter(prefix="/models", tags=["models"])


def _to_out(
    model: Model,
    ability_ids: list[int],
    wargear_ids: list[int],
    keyword_ids: list[int],
    faction_ability_ids: list[int],
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
        feel_no_pain_mortal=model.feel_no_pain_mortal,
        base_size_id=model.base_size.id if model.base_size else None,
        ability_ids=ability_ids,
        wargear_ids=wargear_ids,
        keyword_ids=keyword_ids,
        faction_ability_ids=faction_ability_ids,
    )


async def _base_size(session: AsyncSession, base_size_id: int | None) -> BaseSize | None:
    if base_size_id is None:
        return None
    base_size = await session.get(BaseSize, base_size_id)
    if base_size is None:
        raise HTTPException(status_code=400, detail="invalid base_size_id")
    return base_size


async def _build_keywords(session: AsyncSession, keyword_ids: list[int]) -> list[Keyword]:
    if not keyword_ids:
        return []
    result = await session.execute(select(Keyword).where(Keyword.id.in_(keyword_ids)))
    keywords = list(result.scalars().all())
    if len(keywords) != len(set(keyword_ids)):
        raise HTTPException(status_code=400, detail="one or more keyword_ids not found")
    return keywords


async def _build_faction_abilities(
    session: AsyncSession, faction_ability_ids: list[int]
) -> list[FactionAbility]:
    if not faction_ability_ids:
        return []
    result = await session.execute(
        select(FactionAbility).where(FactionAbility.id.in_(faction_ability_ids))
    )
    faction_abilities = list(result.scalars().all())
    if len(faction_abilities) != len(set(faction_ability_ids)):
        raise HTTPException(status_code=400, detail="one or more faction_ability_ids not found")
    return faction_abilities


@router.get("", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Model)
        .options(
            selectinload(Model.abilities),
            selectinload(Model.wargear),
            selectinload(Model.keywords),
            selectinload(Model.faction_abilities),
        )
        .order_by(Model.id)
    )
    return [
        _to_out(
            model,
            [a.id for a in model.abilities],
            [g.id for g in model.wargear],
            [k.id for k in model.keywords],
            [fa.id for fa in model.faction_abilities],
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
    faction_abilities = await _build_faction_abilities(session, payload.faction_ability_ids)

    model = Model(
        **payload.model_dump(
            exclude={
                "ability_ids",
                "wargear_ids",
                "keyword_ids",
                "faction_ability_ids",
                "base_size_id",
                "feel_no_pain_mortal",
            }
        ),
        feel_no_pain_mortal=payload.feel_no_pain_mortal,
        base_size=await _base_size(session, payload.base_size_id),
        abilities=abilities,
        keywords=keywords,
        faction_abilities=faction_abilities,
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
        model,
        [a.id for a in abilities],
        [g.id for g in wargear],
        [k.id for k in keywords],
        [fa.id for fa in faction_abilities],
    )


@router.put("/{model_id}", response_model=ModelOut)
async def update_model(
    model_id: int, payload: ModelIn, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Model)
        .options(
            selectinload(Model.abilities),
            selectinload(Model.keywords),
            selectinload(Model.faction_abilities),
        )
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
    faction_abilities = await _build_faction_abilities(session, payload.faction_ability_ids)

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
    model.base_size = await _base_size(session, payload.base_size_id)
    model.feel_no_pain_mortal = payload.feel_no_pain_mortal
    model.abilities = abilities
    model.keywords = keywords
    model.faction_abilities = faction_abilities

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
            selectinload(Model.faction_abilities),
        )
        .where(Model.id == model_id)
    )
    model = result.scalar_one()
    return _to_out(
        model,
        [a.id for a in model.abilities],
        [g.id for g in model.wargear],
        [k.id for k in model.keywords],
        [fa.id for fa in model.faction_abilities],
    )


async def _model_with_abilities(session: AsyncSession, model_id: int) -> Model:
    model = (
        await session.execute(
            select(Model).options(selectinload(Model.abilities)).where(Model.id == model_id)
        )
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    return model


@router.put("/{model_id}/abilities/{ability_id}", status_code=204)
async def attach_datasheet_ability(
    model_id: int, ability_id: int, session: AsyncSession = Depends(get_session)
):
    # Gives this model a (shared) datasheet ability; a no-op if it already has it.
    model = await _model_with_abilities(session, model_id)
    ability = (
        await session.execute(select(DatasheetAbility).where(DatasheetAbility.id == ability_id))
    ).scalar_one_or_none()
    if ability is None:
        raise HTTPException(status_code=404, detail="datasheet ability not found")
    if ability not in model.abilities:
        model.abilities.append(ability)
        await session.commit()


@router.delete("/{model_id}/abilities/{ability_id}", status_code=204)
async def detach_datasheet_ability(
    model_id: int, ability_id: int, session: AsyncSession = Depends(get_session)
):
    # Removes a datasheet ability from this model only - the ability itself,
    # and any other models that have it, are untouched.
    model = await _model_with_abilities(session, model_id)
    model.abilities = [a for a in model.abilities if a.id != ability_id]
    await session.commit()
