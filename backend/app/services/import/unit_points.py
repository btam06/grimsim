# Imports datasheets' points from the Munitorum Field Manual (munitorum.py)
# into unit_point_costs / unit_wargear_costs (app/models/unit_points.py), for
# app/services/unit_points.py to price units from.
#
# Each of our datasheets is matched to a manual entry by name - on its own
# faction's page first, then on any page (e.g. Adeptus Mechanicus units in an
# Imperial Knights list, or Deathwatch Terminators on the Deathwatch page),
# then nearly (a typo in ours, on its own faction's page only) - and its
# costs replaced by that entry's. A datasheet with no match keeps whatever it
# had, and is reported.
#
#     docker compose exec backend python -m app.services.import.unit_points [--dry-run]
#
# Every unit already in a list is re-priced from the new costs too (units'
# points are always the manual's - list building doesn't let them be
# changed). --dry-run: report what would change, change nothing.
#
# (This package is named `import`, a Python keyword: within it, modules import
# each other relatively; from elsewhere, importlib.import_module(
# "app.services.import.unit_points").)

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.models import (
    Faction, FactionUnit, Model, PointsSource, Unit, UnitModel, UnitPointCost, UnitWargearCost,
)
from app.services.unit_points import _singular, item_name
from app.services.unit_points import norm as _norm
from app.services.unit_points import reprice

from . import munitorum
from .munitorum import FactionPage, UnitEntry

# How close a name must be to count as a typo of a manual entry's.
NEAR = 0.9


def norm(name: str) -> str:
    return _norm(munitorum.clean(name))


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
    # Priced wargear no model of its datasheet has by that name (so it's never
    # charged): faction, datasheet, manual's name, our closest name or None.
    unfound_wargear: list[tuple[str, str, str, str | None]] = field(default_factory=list)

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
        if self.unfound_wargear:
            out.append("Priced wargear not found on the datasheet's models (never charged):")
            out += [
                f"  {f}: {ours} - {gear}" + (f" (closest: {near})" if near else "")
                for f, ours, gear, near in self.unfound_wargear
            ]
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
    report.unfound_wargear = await unfound_wargear(session)
    return report


async def _datasheet_models(session: AsyncSession) -> dict[int, list[Model]]:
    # The models each datasheet can be made of: those in its units in lists,
    # and its faction's models named like it or like a model its costs name.
    # (A datasheet with none of those: its faction's models, to be safe.)
    models = (
        await session.execute(
            select(Model).options(selectinload(Model.weapons), selectinload(Model.wargear))
        )
    ).scalars().all()
    by_faction: dict[int, list[Model]] = defaultdict(list)
    for model in models:
        by_faction[model.faction_id].append(model)
    by_id = {m.id: m for m in models}

    found: dict[int, dict[int, Model]] = defaultdict(dict)
    used = await session.execute(
        select(Unit.faction_unit_id, UnitModel.model_id).join(UnitModel, UnitModel.unit_id == Unit.id)
    )
    for datasheet_id, model_id in used:
        found[datasheet_id][model_id] = by_id[model_id]

    named: dict[int, set[str]] = defaultdict(set)
    for datasheet_id, composition in await session.execute(
        select(UnitPointCost.faction_unit_id, UnitPointCost.composition)
    ):
        named[datasheet_id] |= {_singular(name) for _, name in composition or []}

    out = {}
    for datasheet in (await session.execute(select(FactionUnit))).scalars():
        names = named[datasheet.id] | {_singular(datasheet.name)}
        mine = found[datasheet.id]
        for model in by_faction[datasheet.faction_id]:
            if _singular(model.name) in names:
                mine[model.id] = model
        out[datasheet.id] = list(mine.values()) or by_faction[datasheet.faction_id]
    return out


async def unfound_wargear(session: AsyncSession) -> list[tuple[str, str, str, str | None]]:
    # Each priced wargear name (unit_wargear_costs) no model of its datasheet
    # has as a weapon, wargear or model name - as wargear_cost compares them -
    # with our closest name, if one's close (a spelling to fix).
    models = await _datasheet_models(session)
    rows = (
        await session.execute(
            select(Faction.name, FactionUnit.name, FactionUnit.id, UnitWargearCost.name)
            .join(FactionUnit, FactionUnit.id == UnitWargearCost.faction_unit_id)
            .join(Faction, Faction.id == FactionUnit.faction_id)
        )
    ).all()
    out = []
    for faction, datasheet, datasheet_id, gear in sorted(rows):
        names = {
            _singular(item_name(n)): item_name(n)
            for m in models.get(datasheet_id, [])
            for n in [m.name, *(w.name for w in m.weapons), *(g.name for g in m.wargear)]
        }
        if _singular(gear) in names:
            continue
        near = difflib.get_close_matches(_singular(gear), list(names), n=1, cutoff=0.6)
        out.append((faction, datasheet, gear, names[near[0]] if near else None))
    return out


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
            json.dump([p.to_json() for p in pages], file, indent=1, ensure_ascii=False)
    print(f"{len(pages)} manual pages ({', '.join(sorted({p.version or '?' for p in pages}))})")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        # (A dry run does it all, and rolls it back.)
        report = await import_pages(session, pages, commit=not args.dry_run)
        print("\n".join(report.lines()))
        changed = await reprice(session, None)
        print(f"{len(changed)} units {'would cost' if args.dry_run else 'now cost'} differently:")
        for unit, old, new in changed:
            print(f"  {unit.army_list.name if unit.army_list else 'no list'}: {unit.label} {old} -> {new}")
        if args.dry_run:
            await session.rollback()
        else:
            await session.commit()
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
    parser.add_argument("--save", help="also write the parsed pages here, as JSON")
    parser.add_argument("--from-file", help="parsed pages (from --save) instead of fetching")
    asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
