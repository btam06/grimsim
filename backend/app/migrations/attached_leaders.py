import logging
from collections import defaultdict

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FactionUnit, LeaderBodyguard, ListWarlord, Unit, UnitModel
from app.services import unit_points

# Leaders are now units of their own in a list, attached to a bodyguard unit
# (Unit.attached_to_id - Core Rules 19.01), rather than models in it. Here:
#
# - units gains its attached_to_id column (creating tables only adds new
#   tables, not columns);
# - each unit with Leader or Support models (Model.is_leader / is_support)
#   among others (see unit_points.attached) is split: those models move,
#   loadouts and enhancements with them, to a new unit of their own datasheet
#   (the one named after the model - its unit's faction's first; made if
#   there's none) in the same list, attached to what's left;
# - each such pair of datasheets is recorded as one the leader can lead
#   (LeaderBodyguard);
# - the list's Warlord, if it was the unit, becomes the leader's unit (a
#   Warlord is a CHARACTER: the leader, not its bodyguard);
# - points: the list's total is kept. The leader costs its datasheet's
#   points (as the Munitorum Field Manual has them - see
#   app/services/unit_points.py), its bodyguard what's left (or, if the
#   leader has no points values, the leader 0 and the bodyguard all of it).
#   Re-pricing from the manual is the import command's --reprice.
#
# A split unit's models are moved, not copied, so a game in progress (which
# plays the two as one again - see app/engine/loader.py) keeps its models.

log = logging.getLogger(__name__)


def _has_column(connection, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(connection).get_columns(table)}


async def _add_column(session: AsyncSession) -> None:
    connection = await session.connection()
    if await connection.run_sync(_has_column, "units", "attached_to_id"):
        return
    await connection.execute(
        text(
            "ALTER TABLE units ADD COLUMN attached_to_id INTEGER"
            " REFERENCES units(id) ON DELETE SET NULL"
        )
    )


async def _datasheet_for(session: AsyncSession, model, by_name: dict) -> FactionUnit:
    # The datasheet named after a Leader or Support model: its faction's
    # first, else any faction's, else a new one in its faction.
    key = unit_points.norm(model.name)
    found = sorted(by_name.get(key, []), key=lambda f: f.faction_id != model.faction_id)
    if found:
        return found[0]
    datasheet = FactionUnit(name=model.name, faction_id=model.faction_id)
    session.add(datasheet)
    await session.flush()
    by_name[key].append(datasheet)
    return datasheet


async def run(session: AsyncSession) -> None:
    await _add_column(session)

    units = (
        await session.execute(
            select(Unit)
            .options(
                selectinload(Unit.unit_models).selectinload(UnitModel.model),
                selectinload(Unit.unit_models).selectinload(UnitModel.weapons),
                selectinload(Unit.unit_models).selectinload(UnitModel.wargear),
                selectinload(Unit.faction_unit),
            )
            .order_by(Unit.id)
        )
    ).scalars().all()
    splitting = [u for u in units if unit_points.attached([um.model for um in u.unit_models])]
    if not splitting:
        return

    by_name: dict[str, list[FactionUnit]] = defaultdict(list)
    for datasheet in (await session.execute(select(FactionUnit))).scalars():
        by_name[unit_points.norm(datasheet.name)].append(datasheet)
    pairs = {
        (link.leader_id, link.bodyguard_id)
        for link in (await session.execute(select(LeaderBodyguard))).scalars()
    }
    warlords = {
        link.unit_id: link
        for link in (await session.execute(select(ListWarlord))).scalars()
    }

    for bodyguard in splitting:
        models = [um.model for um in bodyguard.unit_models]
        # The attached models, by model (a leader of more than one model, e.g.
        # with a retinue of its own, stays one unit).
        groups: dict[int, list[UnitModel]] = defaultdict(list)
        for i in unit_points.attached(models):
            groups[models[i].id].append(bodyguard.unit_models[i])
        leaders = []  # (unit, is a Leader rather than Support)
        for group in groups.values():
            datasheet = await _datasheet_for(session, group[0].model, by_name)
            copy = await unit_points.copy_number(session, bodyguard.list_id, datasheet.id, None)
            price = await unit_points.price_unit(
                session, datasheet.id, copy, group, [um.model for um in group]
            )
            leader = Unit(
                faction_unit_id=datasheet.id,
                points=price or 0,
                list_id=bodyguard.list_id,
                attached_to_id=bodyguard.id,
            )
            session.add(leader)
            await session.flush()
            for unit_model in group:
                # (Re-parented, not removed: a unit's models are deleted with
                # it, so one taken out of its list would be.)
                unit_model.unit = leader
            leaders.append((leader, any(um.model.is_leader for um in group)))
            if (datasheet.id, bodyguard.faction_unit_id) not in pairs:
                pairs.add((datasheet.id, bodyguard.faction_unit_id))
                session.add(
                    LeaderBodyguard(leader_id=datasheet.id, bodyguard_id=bodyguard.faction_unit_id)
                )
        old = bodyguard.points
        bodyguard.points = max(0, old - sum(leader.points for leader, _ in leaders))
        warlord = warlords.get(bodyguard.id)
        if warlord is not None:
            # (Its Leader's unit, else its Support unit's.)
            warlord.unit_id = sorted(leaders, key=lambda pair: not pair[1])[0][0].id
        log.info(
            "split %s (unit %s, %s pts): %s; it %s pts",
            bodyguard.faction_unit.name, bodyguard.id, old,
            ", ".join(f"unit {u.id} {u.points} pts" for u, _ in leaders), bodyguard.points,
        )
    await session.flush()
