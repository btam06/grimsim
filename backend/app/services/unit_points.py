# A unit's points from its datasheet's costs - the Munitorum Field Manual's,
# imported by app/services/import/unit_points.py.
#
# Pricing (the manual's Muster Armies rules): a unit's cost is its starting
# strength's - the smallest listed size it fits in (a unit between two sizes
# pays the larger one's) - at its requisition threshold (its copy's place
# among the list's units of that datasheet, in the order they were added:
# e.g. the 3rd and on pay "Your 3rd+ Units Cost"), plus each wargear item
# with a cost, per item. Enhancements and upgrades are added on top
# elsewhere, as before.

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ArmyList, FactionUnit, Unit, UnitModel, UnitPointCost, UnitWargearCost


def norm(name: str) -> str:
    # A name to compare by: lowercase letters and digits only.
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _singular(name: str) -> str:
    # (Close enough for model and weapon names: "Hunting Wolves" and "Hunting
    # Wolf", "Initiates" and "Initiate".)
    key = norm(name)
    for plural, single in (("ves", "f"), ("ies", "y"), ("s", "")):
        if key.endswith(plural):
            return key[: -len(plural)] + single
    return key


def _fits(cost: UnitPointCost, counts: dict[str, int]) -> bool:
    # Whether a unit with these models (count by name) fits a named
    # composition: each of its models one the composition names, at most as
    # many as it names.
    if not cost.composition:
        return True
    limits = {_singular(name): n for n, name in cost.composition}
    return all(_singular(name) in limits and n <= limits[_singular(name)] for name, n in counts.items())


def unit_cost(costs: list[UnitPointCost], copy: int, model_names: list[str]) -> int | None:
    # The cost of a unit of these models (one name per model), as the
    # `copy`th of its datasheet in its list (None: no costs).
    if not costs:
        return None
    tiers = sorted({c.from_copy for c in costs})
    tier = max((t for t in tiers if t <= copy), default=tiers[0])
    rows = sorted((c for c in costs if c.from_copy == tier), key=lambda c: (c.models, c.points))
    counts: dict[str, int] = defaultdict(int)
    for name in model_names:
        counts[name] += 1
    size = len(model_names)
    # The smallest size it fits in (by its models' names too, for a named
    # composition); else the smallest at least its size; else the largest.
    fitting = [r for r in rows if r.models >= size and _fits(r, counts)]
    if fitting:
        return fitting[0].points
    bigger = [r for r in rows if r.models >= size]
    return bigger[0].points if bigger else rows[-1].points


def wargear_cost(wargear: list[UnitWargearCost], item_names: list[str]) -> int:
    # Each costed item among these (weapons, wargear and models, one name
    # each per model), per item.
    have: dict[str, int] = defaultdict(int)
    for name in item_names:
        have[_singular(name)] += 1
    return sum(gear.points * have.get(_singular(gear.name), 0) for gear in wargear)


def attached(models: list) -> list[int]:
    # The indexes of the models attached to a unit rather than of it: its
    # Leaders and Support models (see Model.is_leader / is_support) - unless
    # every model is one (a CHARACTER on its own: its own datasheet).
    found = [i for i, m in enumerate(models) if m.is_leader or m.is_support]
    return [] if len(found) == len(models) else found


def item_name(name: str) -> str:
    # A weapon's name without its profile ("Cyclone Missile Launcher - Krak",
    # "Plasma caliver – standard": "Cyclone Missile Launcher", "Plasma
    # caliver"), as the manual prices it and datasheets' options name it.
    return re.split(r"\s+[-–—]\s+", name, maxsplit=1)[0].strip()


def _items(unit_model: UnitModel, model) -> list[str]:
    # The costable things a model has, each once (a weapon's profiles are one
    # weapon).
    names = [model.name, *(w.name for w in unit_model.weapons), *(g.name for g in unit_model.wargear)]
    return list(dict.fromkeys(item_name(n) for n in names))


def price(
    costs: list[UnitPointCost],
    wargear: list[UnitWargearCost],
    copy: int,
    unit_models: list[UnitModel],
    models: list,
    leaders: dict[str, tuple[list[UnitPointCost], list[UnitWargearCost]]] | None = None,
) -> int | None:
    # A unit's points from its datasheet's costs - its own models' (at its
    # `copy`), plus each attached Leader's or Support model's from that
    # model's datasheet (`leaders`, by norm(name)) - or None: a cost is
    # missing, so it's priced by hand. `models`: each unit model's Model.
    joined = set(attached(models))
    own = [i for i in range(len(models)) if i not in joined]
    base = unit_cost(costs, copy, [models[i].name for i in own])
    if base is None:
        return None
    total = base + wargear_cost(
        wargear, [n for i in own for n in _items(unit_models[i], models[i])]
    )
    for i in sorted(joined):
        leader_costs, leader_wargear = (leaders or {}).get(norm(models[i].name), ([], []))
        cost = unit_cost(leader_costs, 1, [models[i].name])
        if cost is None:
            return None
        total += cost + wargear_cost(leader_wargear, _items(unit_models[i], models[i]))
    return total


async def leader_costs(
    session: AsyncSession, models: list, faction_id: int | None
) -> dict[str, tuple[list[UnitPointCost], list[UnitWargearCost]]]:
    # Each attached model's datasheet's costs (see attached), by norm(name):
    # the datasheet of its name - its unit's faction's first.
    names = {norm(models[i].name) for i in attached(models)}
    if not names:
        return {}
    rows = (await session.execute(select(FactionUnit.id, FactionUnit.name, FactionUnit.faction_id))).all()
    found = {}
    for unit_id, name, unit_faction in sorted(rows, key=lambda r: r[2] != faction_id):
        key = norm(name)
        if key in names and key not in found:
            costs = await costs_for(session, unit_id)
            if costs[0]:
                found[key] = costs
    return found


async def price_unit(
    session: AsyncSession,
    faction_unit_id: int,
    copy: int,
    unit_models: list[UnitModel],
    models: list,
) -> int | None:
    # price, its costs looked up.
    costs, wargear = await costs_for(session, faction_unit_id)
    if not costs:
        return None
    faction_id = await session.scalar(
        select(FactionUnit.faction_id).where(FactionUnit.id == faction_unit_id)
    )
    leaders = await leader_costs(session, models, faction_id)
    return price(costs, wargear, copy, unit_models, models, leaders)


async def costs_for(
    session: AsyncSession, faction_unit_id: int
) -> tuple[list[UnitPointCost], list[UnitWargearCost]]:
    costs = (
        await session.execute(
            select(UnitPointCost).where(UnitPointCost.faction_unit_id == faction_unit_id)
        )
    ).scalars().all()
    wargear = (
        await session.execute(
            select(UnitWargearCost).where(UnitWargearCost.faction_unit_id == faction_unit_id)
        )
    ).scalars().all()
    return list(costs), list(wargear)


async def copy_number(
    session: AsyncSession, list_id: int | None, faction_unit_id: int, unit_id: int | None
) -> int:
    # The unit's place among its list's units of its datasheet, in the order
    # they were added (a unit being added: after them all).
    if list_id is None:
        return 1
    ids = (
        await session.execute(
            select(Unit.id).where(Unit.list_id == list_id, Unit.faction_unit_id == faction_unit_id)
        )
    ).scalars().all()
    return 1 + sum(1 for i in ids if unit_id is None or i < unit_id)


async def reprice(
    session: AsyncSession, list_id: int | None, faction_unit_id: int | None = None
) -> list[tuple[Unit, int, int]]:
    # Prices the list's units (of one datasheet, or all of them; no list:
    # every unit) from their datasheets' costs; units with none are left as
    # they are. Returns (unit, old, new) for each that changed - not
    # committed.
    query = select(Unit).options(
        selectinload(Unit.unit_models).selectinload(UnitModel.weapons),
        selectinload(Unit.unit_models).selectinload(UnitModel.wargear),
        selectinload(Unit.unit_models).selectinload(UnitModel.model),
        selectinload(Unit.faction_unit),
        selectinload(Unit.army_list).selectinload(ArmyList.units).selectinload(Unit.faction_unit),
    )
    if list_id is not None:
        query = query.where(Unit.list_id == list_id)
    if faction_unit_id is not None:
        query = query.where(Unit.faction_unit_id == faction_unit_id)
    units = (await session.execute(query.order_by(Unit.id))).scalars().all()
    copies: dict[tuple[int | None, int], int] = defaultdict(int)
    changed = []
    for unit in units:
        if unit.list_id is None:
            copy = 1
        else:
            copies[(unit.list_id, unit.faction_unit_id)] += 1
            copy = copies[(unit.list_id, unit.faction_unit_id)]
        new = await price_unit(
            session, unit.faction_unit_id, copy, unit.unit_models,
            [um.model for um in unit.unit_models],
        )
        if new is not None and new != unit.points:
            changed.append((unit, unit.points, new))
            unit.points = new
    return changed
