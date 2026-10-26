from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Faction, Model, Unit, UnitModel
from app.services.list_building import allies

# A list's WARLORD (see ArmyList.warlord): one of its CHARACTER units - and if
# the list has units with one of these abilities, one of them (e.g. Supreme
# Commander: "If this model is in your army, it must be your WARLORD" - with
# two, the player picks which).

MUST_BE_WARLORD = {"Supreme Commander"}


async def warlord_reason(
    session: AsyncSession, list_id: int, warlord_unit_id: int | None, chosen_only: bool = False
) -> str | None:
    # Why the list can't have that Warlord (or none), or None if it can. With
    # `chosen_only`, having none isn't a problem (yet) - only another unit.
    units = (
        await session.execute(
            select(Unit)
            .options(
                selectinload(Unit.faction_unit),
                selectinload(Unit.unit_models)
                .selectinload(UnitModel.model)
                .selectinload(Model.abilities),
            )
            .where(Unit.list_id == list_id)
        )
    ).scalars().all()
    required = [
        unit
        for unit in units
        if {a.name for m in unit.unit_models for a in m.model.abilities} & MUST_BE_WARLORD
    ]
    if not required or warlord_unit_id in {u.id for u in required}:
        return None
    if chosen_only and warlord_unit_id is None:
        return None
    names = " or ".join(u.faction_unit.name for u in required)
    return f"{names} must be the list's Warlord"


async def ally_warlord_reason(
    session: AsyncSession,
    warlord_unit_id: int | None,
    faction_id: int,
    subfaction: str | None,
    detachments: set[str],
) -> str | None:
    # Why that unit can't be the Warlord of a list of this faction, selection
    # (e.g. Chapter) and detachments (by name): not if it's only in the list
    # under one of its detachments' ally allowances (e.g. Deathwatch Allies:
    # "you cannot select a DEATHWATCH model to be your WARLORD"). None if it can.
    if warlord_unit_id is None:
        return None
    faction = await session.get(Faction, faction_id)
    unit = (
        await session.execute(
            select(Unit)
            .options(
                selectinload(Unit.faction_unit),
                selectinload(Unit.unit_models)
                .selectinload(UnitModel.model)
                .selectinload(Model.keywords),
            )
            .where(Unit.id == warlord_unit_id)
        )
    ).scalar_one_or_none()
    if faction is None or unit is None:
        return None
    for unit_model in unit.unit_models:
        ally = allies.subfaction_ally(unit_model.model, faction.name, subfaction, detachments)
        if ally is not None:
            return f"{ally['detachment']}: a {ally['keyword']} model can't be the list's Warlord"
    return None
