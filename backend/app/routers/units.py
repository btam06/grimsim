from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import (
    ArmyList,
    Enhancement,
    FactionUnit,
    ListWarlord,
    Model,
    Unit,
    UnitModel,
    UnitRuleSelection,
    Wargear,
    Weapon,
)
from app.routers.enhancements import used_in_list
from app.schemas import SelectableRuleOut, UnitIn, UnitModelIn, UnitModelOut, UnitOut
from app.services.list_building import allies as list_building
from app.services.list_building import enhancements as enhancement_rules

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
        selected_rule_ids=unit.selected_rule_ids,
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


def _rule_reaches(rule, keyword_sets: list[set[str]]) -> bool:
    # Whether a unit whose models have these keywords matches a rule's keyword
    # options (every model one of them, or it has none).
    options = [{k.name for k in option} for option in rule.keyword_options]
    return bool(keyword_sets) and all(
        not options or any(option <= keywords for option in options)
        for keywords in keyword_sets
    )


async def _selected_elsewhere(
    session: AsyncSession, list_id: int, rule_id: int, unit_id: int | None
) -> int:
    # How many other units in the list are selected for a rule.
    others = select(Unit.id).where(Unit.list_id == list_id)
    if unit_id is not None:
        others = others.where(Unit.id != unit_id)
    rows = await session.execute(
        select(UnitRuleSelection.unit_id).where(
            UnitRuleSelection.rule_id == rule_id, UnitRuleSelection.unit_id.in_(others)
        )
    )
    return len(rows.all())


async def _selectable_list_rules(session: AsyncSession, list_id: int) -> dict[int, object]:
    # The rules with a selection limit of the list's detachments, by id.
    army_list = (
        await session.execute(
            select(ArmyList)
            .options(selectinload(ArmyList.detachments))
            .where(ArmyList.id == list_id)
        )
    ).scalar_one_or_none()
    if army_list is None:
        raise HTTPException(status_code=400, detail="invalid list_id")
    return {
        rule.id: rule
        for rule in enhancement_rules.list_rules(army_list)
        if rule.selection_limit is not None
    }


async def _check_rule_selections(
    session: AsyncSession, payload: UnitIn, models: list[Model], unit_id: int | None
) -> list[int]:
    # The detachment rules the unit is selected for (see
    # DetachmentRule.selection_limit) - checking each is a rule with a
    # selection limit of one of its list's detachments, reaches units like this
    # one, and isn't already selected for by as many other units in the list as
    # it allows.
    ids = list(dict.fromkeys(payload.selected_rule_ids))
    if not ids:
        return []
    if payload.list_id is None:
        raise HTTPException(
            status_code=400, detail="a unit needs to be in a list to be selected for a rule"
        )
    rules = await _selectable_list_rules(session, payload.list_id)
    if any(i not in rules for i in ids):
        raise HTTPException(
            status_code=400,
            detail="selected_rule_ids must be rules of the list's detachments that units are "
            "selected for",
        )
    keyword_sets = [{k.name for k in model.keywords} for model in models]
    for rule_id in ids:
        rule = rules[rule_id]
        if not _rule_reaches(rule, keyword_sets):
            raise HTTPException(
                status_code=400, detail=f"'{rule.name}' can't be selected for this unit"
            )
        if await _selected_elsewhere(session, payload.list_id, rule_id, unit_id) >= (
            rule.selection_limit
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{rule.name}' can be selected for at most {rule.selection_limit} "
                    "units in a list"
                ),
            )
    return ids


async def _apply_enhancements(
    session: AsyncSession,
    payload: UnitIn,
    unit_models: list[UnitModel],
    models: list[Model],
    unit_id: int | None,
    context: list_building.ListContext | None,
    selected_rule_ids: list[int] = (),
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
    exclusive = enhancement_rules.exclusive_detachments(army_list.detachments)
    # Keywords the list's detachment rules give each model (e.g. BATTLELINE).
    granted = enhancement_rules.rule_granted_keywords(
        enhancement_rules.list_rules(army_list),
        [{k.name for k in model.keywords} for model in models],
        selected_rule_ids,
    )
    taken = set(ids) & await used_in_list(session, payload.list_id, unit_id)
    if taken:
        names = ", ".join(sorted(enhancements[i].name for i in taken))
        raise HTTPException(
            status_code=400, detail=f"already taken by another unit in this list: {names}"
        )

    for entry, unit_model, model, extra in zip(payload.unit_models, unit_models, models, granted):
        if entry.enhancement_id is None:
            continue
        enhancement = enhancements[entry.enhancement_id]
        reason = enhancement_rules.model_unavailable_reason(
            enhancement, model, detachment_ids, extra, exclusive
        )
        if reason is None and not list_building.can_take_enhancements(context, model):
            reason = "can't be given to a model included under an ally rule"
        if reason:
            raise HTTPException(
                status_code=400,
                detail=f"'{enhancement.name}' {reason} ({model.name} can't carry it)",
            )
        unit_model.enhancement = enhancement

    if payload.upgrade_id is None:
        return None
    upgrade = enhancements[payload.upgrade_id]
    reason = enhancement_rules.unit_unavailable_reason(
        upgrade, models, detachment_ids, granted, exclusive
    )
    if reason:
        raise HTTPException(status_code=400, detail=f"'{upgrade.name}' {reason}")
    return upgrade


async def _list_context(
    session: AsyncSession, list_id: int | None, unit_id: int | None
) -> list_building.ListContext | None:
    if list_id is None:
        return None
    context = await list_building.load_list_context(session, list_id, unit_id)
    if context is None:
        raise HTTPException(status_code=400, detail="invalid list_id")
    return context


def _check_list_building(
    context: list_building.ListContext | None,
    faction_unit: FactionUnit,
    points: int,
    models: list[Model],
) -> None:
    # A unit in a list must be from the list's faction, or included under an
    # ally rule (within any points cap).
    if context is None:
        return
    reason = list_building.unit_unavailable_reason(context, faction_unit, points, models)
    if reason:
        raise HTTPException(status_code=400, detail=reason)


@router.get("/selectable-rules", response_model=list[SelectableRuleOut])
async def selectable_rules(
    list_id: int,
    model_ids: list[int] = Query(default=[]),
    unit_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    # The detachment rules a unit made of these models (one id per model) in
    # this list can be selected for (`unit_id`: the unit being edited, if any),
    # with how many other units already are - one that's full is still listed.
    rules = await _selectable_list_rules(session, list_id)
    if not rules or not model_ids:
        return []
    models = {
        m.id: m
        for m in (
            await session.execute(
                select(Model).options(selectinload(Model.keywords)).where(Model.id.in_(model_ids))
            )
        ).scalars()
    }
    keyword_sets = [{k.name for k in models[i].keywords} for i in model_ids if i in models]
    return [
        SelectableRuleOut(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            selection_limit=rule.selection_limit,
            selected_elsewhere=await _selected_elsewhere(session, list_id, rule.id, unit_id),
        )
        for rule in rules.values()
        if _rule_reaches(rule, keyword_sets)
    ]


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

    context = await _list_context(session, payload.list_id, None)

    unit_models, models = await _build_unit_models(session, payload.unit_models)
    _check_list_building(context, faction_unit, payload.points, models)
    selected = await _check_rule_selections(session, payload, models, None)
    upgrade = await _apply_enhancements(
        session, payload, unit_models, models, None, context, selected
    )
    unit = Unit(
        faction_unit_id=payload.faction_unit_id,
        points=payload.points,
        list_id=payload.list_id,
        unit_models=unit_models,
        upgrade=upgrade,
    )
    unit.selected_rule_ids = selected
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

    context = await _list_context(session, payload.list_id, unit_id)

    new_unit_models, models = await _build_unit_models(session, payload.unit_models)
    _check_list_building(context, faction_unit, payload.points, models)
    selected = await _check_rule_selections(session, payload, models, unit_id)
    upgrade = await _apply_enhancements(
        session, payload, new_unit_models, models, unit_id, context, selected
    )

    unit.faction_unit_id = payload.faction_unit_id
    unit.points = payload.points
    unit.list_id = payload.list_id
    unit.unit_models = new_unit_models
    unit.upgrade = upgrade
    unit.selected_rule_ids = selected

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

    # No longer any list's Warlord.
    await session.execute(delete(ListWarlord).where(ListWarlord.unit_id == unit_id))
    await session.delete(unit)
    await session.commit()
