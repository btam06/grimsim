from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import (
    ArmyList,
    DatasheetAbility,
    Detachment,
    Enhancement,
    EnhancementDatasheetAbility,
    EnhancementKeyword,
    EnhancementWeapon,
    EnhancementWeaponAbility,
    Keyword,
    Model,
    Unit,
    UnitModel,
    WeaponAbility,
    unit_model_enhancements,
    unit_upgrades,
)
from app.schemas import (
    EnhancementDatasheetAbilitySchema,
    EnhancementIn,
    EnhancementKeywordSchema,
    EnhancementOut,
    EnhancementWeaponAbilitySchema,
    EnhancementWeaponOut,
)
from app.services.list_building import allies as list_building
from app.services.list_building import enhancements as enhancement_rules

router = APIRouter(prefix="/enhancements", tags=["enhancements"])


def _to_out(enhancement: Enhancement) -> EnhancementOut:
    return EnhancementOut(
        id=enhancement.id,
        name=enhancement.name,
        description=enhancement.description,
        points=enhancement.points,
        kind=enhancement.kind,
        detachment_id=enhancement.detachment_id,
        keyword_ids=[k.id for k in enhancement.keywords],
        excluded_keyword_ids=[k.id for k in enhancement.excluded_keywords],
        weapon_abilities=[
            EnhancementWeaponAbilitySchema(
                weapon_ability_id=g.weapon_ability_id, weapon_type=g.weapon_type, scope=g.scope
            )
            for g in enhancement.weapon_ability_grants
        ],
        datasheet_abilities=[
            EnhancementDatasheetAbilitySchema(
                datasheet_ability_id=g.datasheet_ability_id, scope=g.scope
            )
            for g in enhancement.datasheet_ability_grants
        ],
        granted_keywords=[
            EnhancementKeywordSchema(keyword_id=g.keyword_id, scope=g.scope)
            for g in enhancement.keyword_grants
        ],
        weapons=[
            EnhancementWeaponOut(
                id=w.id,
                name=w.name,
                weapon_type=w.weapon_type,
                range=w.range,
                attacks=w.attacks,
                skill=w.skill,
                strength=w.strength,
                ap=w.ap,
                damage=w.damage,
                ability_ids=[a.id for a in w.abilities],
            )
            for w in enhancement.weapons
        ],
    )


async def _all(session: AsyncSession) -> list[Enhancement]:
    return list((await session.execute(select(Enhancement).order_by(Enhancement.id))).scalars())


async def _load_keywords(session: AsyncSession, ids: list[int], field: str) -> list[Keyword]:
    if not ids:
        return []
    keywords = list((await session.execute(select(Keyword).where(Keyword.id.in_(ids)))).scalars())
    if len(keywords) != len(set(ids)):
        raise HTTPException(status_code=400, detail=f"one or more {field} not found")
    return keywords


async def used_in_list(session: AsyncSession, list_id: int, except_unit_id: int | None) -> set[int]:
    # Enhancements and upgrades already taken by units in a list - each can
    # only be taken once per list. The unit being edited doesn't count.
    unit_ids = select(Unit.id).where(Unit.list_id == list_id)
    if except_unit_id is not None:
        unit_ids = unit_ids.where(Unit.id != except_unit_id)
    carried = select(unit_model_enhancements.c.enhancement_id).join(
        UnitModel, UnitModel.id == unit_model_enhancements.c.unit_model_id
    ).where(UnitModel.unit_id.in_(unit_ids))
    upgraded = select(unit_upgrades.c.enhancement_id).where(unit_upgrades.c.unit_id.in_(unit_ids))
    return set((await session.execute(carried)).scalars()) | set(
        (await session.execute(upgraded)).scalars()
    )


async def _list_detachments(
    session: AsyncSession, list_id: int
) -> tuple[set[int], list, dict[int, set[str]]]:
    # The list's detachment ids, their rules (e.g. for keywords they grant),
    # and those that limit some units to their own enhancements.
    army_list = (
        await session.execute(
            select(ArmyList)
            .options(selectinload(ArmyList.detachments))
            .where(ArmyList.id == list_id)
        )
    ).scalar_one_or_none()
    if army_list is None:
        raise HTTPException(status_code=400, detail="invalid list_id")
    return (
        {d.id for d in army_list.detachments},
        enhancement_rules.list_rules(army_list),
        enhancement_rules.exclusive_detachments(army_list.detachments),
    )


def _keyword_names(model: Model) -> set[str]:
    return {k.name for k in model.keywords}


async def _load_models(session: AsyncSession, ids: list[int]) -> dict[int, Model]:
    models = {
        m.id: m
        for m in (
            await session.execute(
                select(Model).options(selectinload(Model.keywords)).where(Model.id.in_(ids))
            )
        ).scalars()
    }
    if set(ids) - set(models):
        raise HTTPException(status_code=400, detail="one or more model_ids not found")
    return models


@router.get("", response_model=list[EnhancementOut])
async def list_enhancements(session: AsyncSession = Depends(get_session)):
    return [_to_out(e) for e in await _all(session)]


@router.get("/available", response_model=list[EnhancementOut])
async def available_enhancements(
    list_id: int,
    model_id: int,
    unit_id: int | None = None,
    # Detachment rules the unit is selected for (e.g. one giving CHARACTER).
    selected_rule_ids: list[int] = Query(default=[]),
    session: AsyncSession = Depends(get_session),
):
    # The enhancements a model could carry in a unit of this list (`unit_id`:
    # the unit being edited, if any), leaving out ones other units in the list
    # have already taken.
    detachment_ids, rules, exclusive = await _list_detachments(session, list_id)
    model = (await _load_models(session, [model_id]))[model_id]
    # Keywords the list's detachment rules give it (judged on the model alone).
    granted = enhancement_rules.rule_granted_keywords(
        rules, [_keyword_names(model)], selected_rule_ids
    )[0]
    context = await list_building.load_list_context(session, list_id, unit_id)
    if not list_building.can_take_enhancements(context, model):
        return []  # e.g. a HARLEQUINS model in a Drukhari list
    used = await used_in_list(session, list_id, unit_id)
    return [
        _to_out(e)
        for e in await _all(session)
        if e.id not in used
        and enhancement_rules.model_unavailable_reason(
            e, model, detachment_ids, granted, exclusive
        )
        is None
    ]


@router.get("/available-upgrades", response_model=list[EnhancementOut])
async def available_upgrades(
    list_id: int,
    model_ids: list[int] = Query(default=[]),
    unit_id: int | None = None,
    selected_rule_ids: list[int] = Query(default=[]),
    session: AsyncSession = Depends(get_session),
):
    # The upgrades a unit made of these models (one id per model) could take
    # in this list, leaving out ones other units in the list have taken.
    detachment_ids, rules, exclusive = await _list_detachments(session, list_id)
    models = await _load_models(session, list(set(model_ids)))
    unit_models = [models[i] for i in model_ids]
    granted = enhancement_rules.rule_granted_keywords(
        rules, [_keyword_names(m) for m in unit_models], selected_rule_ids
    )
    used = await used_in_list(session, list_id, unit_id)
    return [
        _to_out(e)
        for e in await _all(session)
        if e.id not in used
        and enhancement_rules.unit_unavailable_reason(
            e, unit_models, detachment_ids, granted, exclusive
        )
        is None
    ]


@router.post("", response_model=EnhancementOut, status_code=201)
async def create_enhancement(payload: EnhancementIn, session: AsyncSession = Depends(get_session)):
    detachment = await session.get(Detachment, payload.detachment_id)
    if detachment is None:
        raise HTTPException(status_code=400, detail="invalid detachment_id")
    keywords = await _load_keywords(session, payload.keyword_ids, "keyword_ids")
    excluded = await _load_keywords(session, payload.excluded_keyword_ids, "excluded_keyword_ids")
    if set(payload.keyword_ids) & set(payload.excluded_keyword_ids):
        raise HTTPException(
            status_code=400, detail="a keyword can't be both required and excluded"
        )
    for grants, model, field in (
        (payload.weapon_abilities, WeaponAbility, "weapon_ability_id"),
        (payload.datasheet_abilities, DatasheetAbility, "datasheet_ability_id"),
    ):
        ids = [getattr(g, field) for g in grants]
        if len(ids) != len(set(ids)):
            raise HTTPException(status_code=400, detail=f"duplicate {field}")
        found = (await session.execute(select(model.id).where(model.id.in_(ids)))).scalars()
        if set(ids) - set(found):
            raise HTTPException(status_code=400, detail=f"one or more {field}s not found")
    granted = await _load_keywords(
        session, [g.keyword_id for g in payload.granted_keywords], "granted keyword_ids"
    )
    if len(granted) != len(payload.granted_keywords):
        raise HTTPException(status_code=400, detail="duplicate granted keyword_ids")
    weapon_abilities = {
        a.id: a
        for a in (
            await session.execute(
                select(WeaponAbility).where(
                    WeaponAbility.id.in_({i for w in payload.weapons for i in w.ability_ids})
                )
            )
        ).scalars()
    }
    if {i for w in payload.weapons for i in w.ability_ids} - set(weapon_abilities):
        raise HTTPException(status_code=400, detail="one or more weapon ability_ids not found")
    enhancement = Enhancement(
        name=payload.name,
        description=payload.description,
        points=payload.points,
        kind=payload.kind,
        detachment_id=payload.detachment_id,
        keywords=keywords,
        excluded_keywords=excluded,
        weapon_ability_grants=[
            EnhancementWeaponAbility(
                weapon_ability_id=g.weapon_ability_id, weapon_type=g.weapon_type, scope=g.scope
            )
            for g in payload.weapon_abilities
        ],
        datasheet_ability_grants=[
            EnhancementDatasheetAbility(datasheet_ability_id=g.datasheet_ability_id, scope=g.scope)
            for g in payload.datasheet_abilities
        ],
        keyword_grants=[
            EnhancementKeyword(keyword_id=g.keyword_id, scope=g.scope)
            for g in payload.granted_keywords
        ],
        weapons=[
            EnhancementWeapon(
                **w.model_dump(exclude={"ability_ids"}),
                abilities=[weapon_abilities[i] for i in dict.fromkeys(w.ability_ids)],
            )
            for w in payload.weapons
        ],
    )
    session.add(enhancement)
    await session.commit()
    return _to_out(enhancement)


@router.delete("/{enhancement_id}", status_code=204)
async def delete_enhancement(enhancement_id: int, session: AsyncSession = Depends(get_session)):
    # Also takes it off any models and units that have it.
    if await session.get(Enhancement, enhancement_id) is None:
        raise HTTPException(status_code=404, detail="enhancement not found")
    await enhancement_rules.delete_enhancements(session, [enhancement_id])
    await session.commit()
