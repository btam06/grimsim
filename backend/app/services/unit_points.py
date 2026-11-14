# Datasheets' points from the Munitorum Field Manual (app/services/
# munitorum.py), and a unit's points from them.
#
# Importing: each of our datasheets is matched to a manual entry by name -
# on its own faction's page first, then on any page (e.g. Adeptus Mechanicus
# units in an Imperial Knights list, or Deathwatch Terminators on the
# Deathwatch page), then nearly (a typo in ours, on its own faction's page
# only) - and its costs replaced by that entry's. A datasheet with no match
# keeps whatever it had, and is reported.
#
# Pricing (the manual's Muster Armies rules): a unit's cost is its starting
# strength's - the smallest listed size it fits in (a unit between two sizes
# pays the larger one's) - at its requisition threshold (its copy's place
# among the list's units of that datasheet, in the order they were added:
# e.g. the 3rd and on pay "Your 3rd+ Units Cost"), plus each wargear item
# with a cost, per item. Enhancements and upgrades are added on top
# elsewhere, as before.
#
#     docker compose exec backend python -m app.services.unit_points --dry-run
#     docker compose exec backend python -m app.services.unit_points [--reprice]
#
# (--reprice: also re-price every unit already in a list; without it, only
# units added or edited from now on are priced from the manual.)

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ArmyList,
    Faction,
    FactionUnit,
    PointsSource,
    Unit,
    UnitModel,
    UnitPointCost,
    UnitWargearCost,
)
from app.services import munitorum
from app.services.munitorum import FactionPage, UnitEntry

# How close a name must be to count as a typo of a manual entry's.
NEAR = 0.9


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", munitorum.clean(name).lower())


def _singular(name: str) -> str:
    # (Close enough for model and weapon names: "Hunting Wolves" and "Hunting
    # Wolf", "Initiates" and "Initiate".)
    key = norm(name)
    for plural, single in (("ves", "f"), ("ies", "y"), ("s", "")):
        if key.endswith(plural):
            return key[: -len(plural)] + single
    return key


# --- importing ---------------------------------------------------------------


@dataclass
class Match:
    page: FactionPage
    entry: UnitEntry
    how: str  # "exact", "other page" or "near"


@dataclass
class ImportReport:
    updated: list[tuple[str, str, str]] = field(default_factory=list)  # faction, ours, how
    unmatched: list[tuple[str, str]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"{len(self.updated)} datasheets priced from the manual"]
        out += [f"  {f}: {ours} ({how})" for f, ours, how in self.updated if how != "exact"]
        if self.unmatched:
            out.append(f"{len(self.unmatched)} datasheets not in the manual (points left as they were):")
            out += [f"  {f}: {ours}" for f, ours in self.unmatched]
        if self.conflicts:
            out.append("Matched on more than one page with different costs (first page used):")
            out += [f"  {c}" for c in self.conflicts]
        if self.unparsed:
            out.append("Manual lines not understood:")
            out += [f"  {u}" for u in self.unparsed]
        return out


def _costs_key(entry: UnitEntry):
    return (
        sorted((c.from_copy, c.models, c.points) for c in entry.costs),
        sorted((w.name, w.points) for w in entry.wargear),
    )


def match_entries(
    pages: list[FactionPage], ours: list[tuple[str, str]]
) -> tuple[dict[tuple[str, str], Match], ImportReport]:
    # Each of our (faction name, datasheet name)s' manual entry.
    report = ImportReport(unparsed=[u for p in pages for u in p.unparsed])
    by_page = {norm(p.title): p for p in pages}
    everywhere: dict[str, list[tuple[FactionPage, UnitEntry]]] = defaultdict(list)
    for page in pages:
        for entry in page.units:
            if entry.costs:
                everywhere[norm(entry.name)].append((page, entry))

    found: dict[tuple[str, str], Match] = {}
    for faction, name in ours:
        key = norm(name)
        own = by_page.get(norm(faction))
        own_entries = {norm(e.name): e for e in own.units if e.costs} if own else {}
        if key in own_entries:
            found[(faction, name)] = Match(own, own_entries[key], "exact")
        elif everywhere.get(key):
            hits = everywhere[key]
            page, entry = hits[0]
            if len({json.dumps(_costs_key(e)) for _, e in hits}) > 1:
                report.conflicts.append(
                    f"{faction}: {name} - on " + ", ".join(p.slug for p, _ in hits)
                )
            found[(faction, name)] = Match(page, entry, f"from {page.slug}")
        else:
            near = difflib.get_close_matches(key, list(own_entries), n=1, cutoff=NEAR)
            if near:
                entry = own_entries[near[0]]
                found[(faction, name)] = Match(own, entry, f"near: {entry.name}")
            else:
                report.unmatched.append((faction, name))
    return found, report


async def import_pages(
    session: AsyncSession, pages: list[FactionPage], commit: bool = True
) -> ImportReport:
    # Replaces each matched datasheet's costs with its manual entry's (all of
    # them, in one commit - or none, flushed only, to look before leaping).
    rows = (
        await session.execute(
            select(FactionUnit.id, Faction.name, FactionUnit.name).join(
                Faction, Faction.id == FactionUnit.faction_id
            )
        )
    ).all()
    ids = {(f, n): i for i, f, n in rows}
    found, report = match_entries(pages, list(ids))
    now = datetime.now(timezone.utc)
    for (faction, name), match in sorted(found.items()):
        unit_id = ids[(faction, name)]
        await session.execute(delete(UnitPointCost).where(UnitPointCost.faction_unit_id == unit_id))
        await session.execute(
            delete(UnitWargearCost).where(UnitWargearCost.faction_unit_id == unit_id)
        )
        seen = set()
        for cost in match.entry.costs:
            if (cost.from_copy, cost.models, cost.points) in seen:
                continue
            seen.add((cost.from_copy, cost.models, cost.points))
            session.add(
                UnitPointCost(
                    faction_unit_id=unit_id, from_copy=cost.from_copy, models=cost.models,
                    points=cost.points,
                    composition=[list(p) for p in cost.composition] if cost.composition else None,
                )
            )
        names = set()
        for gear in match.entry.wargear:
            if gear.name.lower() not in names:
                names.add(gear.name.lower())
                session.add(
                    UnitWargearCost(faction_unit_id=unit_id, name=gear.name, points=gear.points)
                )
        await session.merge(
            PointsSource(
                faction_unit_id=unit_id, page=match.page.slug, version=match.page.version,
                matched_name=match.entry.name, imported_at=now,
            )
        )
        report.updated.append((faction, name, match.how))
    if commit:
        await session.commit()
    else:
        await session.flush()
    return report


# --- pricing -----------------------------------------------------------------


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


def _items(unit_model: UnitModel, model) -> list[str]:
    return [model.name, *(w.name for w in unit_model.weapons), *(g.name for g in unit_model.wargear)]


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


# --- the script --------------------------------------------------------------


async def _main(args) -> None:
    from app.db import async_session, engine
    from app.models import Base

    if args.from_file:
        with open(args.from_file) as file:
            pages = [_page_from_json(p) for p in json.load(file)]
    else:
        pages = munitorum.fetch_all(only=args.only or None)
    if args.save:
        with open(args.save, "w") as file:
            json.dump([p.to_json() for p in pages], file, indent=1)
    print(f"{len(pages)} manual pages ({', '.join(sorted({p.version or '?' for p in pages}))})")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        # (A dry run does it all, and rolls it back.)
        report = await import_pages(session, pages, commit=not args.dry_run)
        print("\n".join(report.lines()))
        changed = await reprice(session, None)
        verb = "now cost" if args.reprice and not args.dry_run else "would cost"
        print(f"{len(changed)} units {verb} differently{'' if args.reprice else ' with --reprice'}:")
        for unit, old, new in changed:
            print(f"  {unit.army_list.name if unit.army_list else 'no list'}: {unit.label} {old} -> {new}")
        if args.reprice and not args.dry_run:
            await session.commit()
        else:
            await session.rollback()
    await engine.dispose()


def _page_from_json(data: dict) -> FactionPage:
    return FactionPage(
        slug=data["slug"], title=data["title"], version=data.get("version"),
        units=[
            UnitEntry(
                name=u["name"],
                costs=[
                    munitorum.UnitCost(
                        c["from_copy"], c["models"], c["points"],
                        [tuple(p) for p in c["composition"]] if c.get("composition") else None,
                    )
                    for c in u["costs"]
                ],
                wargear=[munitorum.WargearCost(w["name"], w["points"]) for w in u["wargear"]],
            )
            for u in data["units"]
        ],
        unparsed=data.get("unparsed", []),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Import points from the Munitorum Field Manual.")
    parser.add_argument("--only", nargs="*", help="just these pages (e.g. chaos-knights)")
    parser.add_argument("--dry-run", action="store_true", help="match and report; change nothing")
    parser.add_argument("--reprice", action="store_true", help="re-price units already in lists")
    parser.add_argument("--save", help="also write the parsed pages here, as JSON")
    parser.add_argument("--from-file", help="parsed pages (from --save) instead of fetching")
    asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
