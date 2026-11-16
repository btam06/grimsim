from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import (
    ArmyList,
    Enhancement,
    FactionUnit,
    LeaderBodyguard,
    ListWarlord,
    Model,
    Unit,
    UnitModel,
    UnitRuleSelection,
    Wargear,
    Weapon,
)
from app.routers.enhancements import used_in_list
from app.schemas import (
    SelectableRuleOut, UnitIn, UnitModelIn, UnitModelOut, UnitOut, UnitPriceOut,
)
from app.services.list_building import allies as list_building
from app.services import unit_points
from app.services.list_building import enhancements as enhancement_rules
from app.services.list_building import loadouts

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
        attached_to_id=unit.attached_to_id,
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


def _kind(models: list[Model]) -> str | None:
    # "leader" or "support" for a leader or support unit (every model a
    # Leader or Support model), else None.
    if not models or not all(m.is_leader or m.is_support for m in models):
        return None
    return "leader" if any(m.is_leader for m in models) else "support"


# Retinues (Cryptek Retinue: Cryptothralls; Canoptek Retinue: Tomb Crawlers):
# a unit with one can join one other unit in its list that's led by a
# CRYPTEK model - one retinue to a unit. In a game it's part of that unit
# (see app/engine/loader.py merge).
RETINUES = {"Cryptek Retinue": "CRYPTEK", "Canoptek Retinue": "CRYPTEK"}


async def _retinue(session: AsyncSession, models: list[Model]) -> bool:
    ids = [m.id for m in models if m.id is not None]
    if not ids:
        return False
    found = (
        await session.execute(
            select(Model).options(selectinload(Model.abilities)).where(Model.id.in_(ids))
        )
    ).scalars().all()
    return bool(found) and all(any(a.name in RETINUES for a in m.abilities) for m in found)


async def _check_retinue(session: AsyncSession, payload: UnitIn, unit_id: int | None) -> int:
    target = (
        await session.execute(
            select(Unit)
            .options(selectinload(Unit.unit_models).selectinload(UnitModel.model))
            .where(Unit.id == payload.attached_to_id)
        )
    ).scalar_one_or_none()
    if target is None or target.list_id != payload.list_id or target.id == unit_id:
        raise HTTPException(status_code=400, detail="attached_to_id must be another unit in its list")
    if target.attached_to_id is not None or _kind([um.model for um in target.unit_models]):
        raise HTTPException(status_code=400, detail="a retinue joins a Bodyguard unit")
    attached = (
        await session.execute(
            select(Unit)
            .options(
                selectinload(Unit.unit_models).selectinload(UnitModel.model).selectinload(Model.keywords),
                selectinload(Unit.unit_models).selectinload(UnitModel.model).selectinload(Model.abilities),
            )
            .where(Unit.attached_to_id == target.id, Unit.id != (unit_id or 0))
        )
    ).scalars().all()
    if not any(
        any(k.name == "CRYPTEK" for k in um.model.keywords) for other in attached for um in other.unit_models
    ):
        raise HTTPException(status_code=400, detail="a retinue joins a unit led by a CRYPTEK model")
    if any(
        any(a.name in RETINUES for a in um.model.abilities) for other in attached for um in other.unit_models
    ):
        raise HTTPException(status_code=400, detail="that unit already has a retinue")
    return target.id


async def _check_attachment(
    session: AsyncSession, payload: UnitIn, models: list[Model], unit_id: int | None
) -> int | None:
    # The bodyguard unit it's attached to, checked (Core Rules 19.01): one
    # in its list, of a datasheet it can lead, not itself a leader, support
    # or attached unit, with no other unit of its kind (leader or support)
    # attached to it.
    if payload.attached_to_id is None:
        return None
    if payload.list_id is None:
        raise HTTPException(status_code=400, detail="only a unit in a list can be attached")
    kind = _kind(models)
    if kind is None and await _retinue(session, models):
        return await _check_retinue(session, payload, unit_id)
    if kind is None:
        raise HTTPException(
            status_code=400, detail="only a leader or support unit can be attached to a unit"
        )
    if unit_id is not None and await session.scalar(
        select(Unit.id).where(Unit.attached_to_id == unit_id).limit(1)
    ):
        raise HTTPException(status_code=400, detail="a unit with units attached to it can't be attached")
    target = (
        await session.execute(
            select(Unit)
            .options(selectinload(Unit.unit_models).selectinload(UnitModel.model))
            .where(Unit.id == payload.attached_to_id)
        )
    ).scalar_one_or_none()
    if target is None or target.list_id != payload.list_id or target.id == unit_id:
        raise HTTPException(status_code=400, detail="attached_to_id must be another unit in its list")
    if target.attached_to_id is not None or _kind([um.model for um in target.unit_models]):
        raise HTTPException(
            status_code=400, detail="a leader or support unit can't be a bodyguard unit"
        )
    if not await session.get(LeaderBodyguard, (payload.faction_unit_id, target.faction_unit_id)):
        raise HTTPException(status_code=400, detail="this datasheet can't lead that unit")
    others = (
        await session.execute(
            select(Unit)
            .options(selectinload(Unit.unit_models).selectinload(UnitModel.model))
            .where(Unit.attached_to_id == target.id, Unit.id != (unit_id or 0))
        )
    ).scalars().all()
    if any(_kind([um.model for um in other.unit_models]) == kind for other in others):
        raise HTTPException(
            status_code=400, detail=f"that unit already has a {kind} unit attached"
        )
    return target.id


async def _check_loadout(
    session: AsyncSession, payload: UnitIn, unit_models: list[UnitModel], models: list[Model]
) -> None:
    # The unit must be one its datasheet allows (its composition and wargear
    # options, from the data), when the data says.
    loadout = await loadouts.loadout_for(session, payload.faction_unit_id)
    if loadout is None:
        return
    reason = loadouts.check(
        loadout, [(m, um.weapons, um.wargear) for um, m in zip(unit_models, models)]
    )
    if reason:
        raise HTTPException(status_code=400, detail=reason)


async def _auto_models(session: AsyncSession, payload: UnitIn) -> None:
    # A datasheet with nothing to decide (one model, as equipped) gets its
    # model when none are given.
    if payload.unit_models:
        return
    loadout = await loadouts.loadout_for(session, payload.faction_unit_id)
    if loadout is None or not loadout.auto:
        return
    part = loadout.parts[0]
    weapon_ids, wargear_ids = loadouts.ids_for(part.model, part.equipped)
    payload.unit_models = [
        UnitModelIn(model_id=part.model.id, weapon_ids=weapon_ids, wargear_ids=wargear_ids)
    ]


async def _price(
    session: AsyncSession,
    payload: UnitIn,
    unit_models: list[UnitModel],
    models: list[Model],
    unit_id: int | None,
) -> int:
    # The unit's points: from its datasheet's costs (the Munitorum Field
    # Manual's - see app/services/unit_points.py). A datasheet the manual
    # hasn't got: as given (by the API - list building doesn't ask), else
    # what the unit had, else 0.
    copy = await unit_points.copy_number(
        session, payload.list_id, payload.faction_unit_id, unit_id
    )
    points = await unit_points.price_unit(
        session, payload.faction_unit_id, copy, unit_models, models
    )
    if points is not None:
        return points
    if payload.points is not None:
        return payload.points
    if unit_id is not None:
        return await session.scalar(select(Unit.points).where(Unit.id == unit_id)) or 0
    return 0


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


@router.post("/price", response_model=UnitPriceOut)
async def price_unit(
    payload: UnitIn,
    unit_id: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    # What the unit would cost as given (for the unit form, as it's built):
    # priced as saving it would, without checking anything else. `unit_id`:
    # the unit being edited.
    if not payload.unit_models:
        return UnitPriceOut(points=0)
    if await session.get(FactionUnit, payload.faction_unit_id) is None:
        raise HTTPException(status_code=400, detail="invalid faction_unit_id")
    unit_models, models = await _build_unit_models(session, payload.unit_models)
    return UnitPriceOut(points=await _price(session, payload, unit_models, models, unit_id))


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

    await _auto_models(session, payload)
    unit_models, models = await _build_unit_models(session, payload.unit_models)
    await _check_loadout(session, payload, unit_models, models)
    points = await _price(session, payload, unit_models, models, None)
    attached_to_id = await _check_attachment(session, payload, models, None)
    _check_list_building(context, faction_unit, points, models)
    selected = await _check_rule_selections(session, payload, models, None)
    upgrade = await _apply_enhancements(
        session, payload, unit_models, models, None, context, selected
    )
    unit = Unit(
        faction_unit_id=payload.faction_unit_id,
        points=points,
        list_id=payload.list_id,
        attached_to_id=attached_to_id,
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

    await _auto_models(session, payload)
    new_unit_models, models = await _build_unit_models(session, payload.unit_models)
    await _check_loadout(session, payload, new_unit_models, models)
    points = await _price(session, payload, new_unit_models, models, unit_id)
    attached_to_id = await _check_attachment(session, payload, models, unit_id)
    _check_list_building(context, faction_unit, points, models)
    selected = await _check_rule_selections(session, payload, models, unit_id)
    upgrade = await _apply_enhancements(
        session, payload, new_unit_models, models, unit_id, context, selected
    )

    before = (unit.list_id, unit.faction_unit_id)
    unit.faction_unit_id = payload.faction_unit_id
    unit.points = points
    if unit.list_id != payload.list_id:
        # (Moved to another list: what was attached to it stays behind.)
        await session.execute(
            update(Unit).where(Unit.attached_to_id == unit_id).values(attached_to_id=None)
        )
    unit.list_id = payload.list_id
    unit.attached_to_id = attached_to_id
    unit.unit_models = new_unit_models
    unit.upgrade = upgrade
    unit.selected_rule_ids = selected

    await session.flush()
    # (Moved to another list or datasheet: the units of its old one there may
    # now be earlier copies, and of its new one later ones - at a different
    # requisition threshold.)
    after = (unit.list_id, unit.faction_unit_id)
    if before != after:
        for list_id, faction_unit_id in (before, after):
            if list_id is not None:
                await unit_points.reprice(session, list_id, faction_unit_id)
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
    group = (unit.list_id, unit.faction_unit_id)
    # What was attached to it is a unit on its own again.
    await session.execute(
        update(Unit).where(Unit.attached_to_id == unit_id).values(attached_to_id=None)
    )
    await session.delete(unit)
    await session.flush()
    # (Later units of its datasheet in its list move up a copy - maybe below
    # a requisition threshold.)
    if group[0] is not None:
        await unit_points.reprice(session, *group)
    await session.commit()
