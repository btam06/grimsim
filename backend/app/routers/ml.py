from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import ArmyList

# The ML runs' diagnose files (ml/diagnose.py's --out, ml/data/diagnose*.jsonl:
# a line a side a finished game, with what it did), summed up for the app's
# ML page: averages a game for each list and side and over every list, the
# win rate with its 95% interval, and stratagem uses by name and by when.

router = APIRouter(prefix="/ml", tags=["ml"])

SIDES = ("policy", "opponent")
COLUMNS = (
    "vp", "vp_against", "primary", "secondary", "shot_damage", "melee_damage", "shot_kills",
    "melee_kills", "other_kills", "charges", "charges_made", "stratagems", "cp_spent",
    "idle_units", "units_in_reserves", "units_lost", "units", "left", "primary_left",
    "secondary_left", "capped", "discarded", "achieved", "held_unclaimed", "points_left",
    "points_lost",
)
ALL_LISTS = "All lists"


def _files() -> list[Path]:
    # The newest first.
    folder = Path(settings.ml_data_dir)
    return sorted(folder.glob("diagnose*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def wilson(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    # The 95% interval of a rate p over n games.
    if n == 0:
        return 0.0, 1.0
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, mid - half), min(1.0, mid + half)


def summarize(rows: list[dict], names: dict[int, str]) -> dict:
    finished = [r for r in rows if r.get("end") == "terminated"]
    by_game: dict[tuple, dict[int, dict]] = {}
    for r in finished:
        by_game.setdefault((r["seed"], r["save"]), {})[r["seat"]] = r
    sides = []
    for seats in by_game.values():
        for seat, r in seats.items():
            other = seats.get(3 - seat)
            if other is None:
                continue
            side = {c: r.get(c, 0) for c in COLUMNS}
            side.update(
                side=r["side"], list=names.get(r["list_id"], f"List {r['list_id']}"),
                won=(r["vp"] > other["vp"]) + 0.5 * (r["vp"] == other["vp"]),
                vp_against=other["vp"],
                capped=r.get("primary_capped", 0) + r.get("secondary_capped", 0),
                uses=r.get("stratagem_uses", []),
            )
            sides.append(side)

    by_list = []

    def add(list_name: str, side: str, group: list[dict]) -> None:
        n = len(group)
        win = sum(g["won"] for g in group) / n
        row = {"list": list_name, "side": side, "games": n, "win": win}
        row["win_lo"], row["win_hi"] = wilson(win, n)
        for c in COLUMNS:
            row[c] = sum(g[c] for g in group) / n
        row["margin"] = row["vp"] - row["vp_against"]
        row["charge_rate"] = row["charges_made"] / row["charges"] if row["charges"] else 0
        by_list.append(row)

    games = {}
    for side in SIDES:
        mine = [s for s in sides if s["side"] == side]
        games[side] = len(mine)
        if not mine:
            continue
        add(ALL_LISTS, side, mine)
        for list_name in sorted({s["list"] for s in mine}):
            add(list_name, side, [s for s in mine if s["list"] == list_name])

    def per_game(key) -> list[dict]:
        counts: dict[tuple[str, str], int] = {}
        for s in sides:
            for use in s["uses"]:
                k = (key(use), s["side"])
                counts[k] = counts.get(k, 0) + 1
        cats = {k for k, _ in counts}
        out = [
            {"name": cat, "values": [counts.get((cat, side), 0) / (games[side] or 1) for side in SIDES]}
            for cat in cats
        ]
        return sorted(out, key=lambda c: -sum(c["values"]))

    first = rows[0] if rows else {}
    return {
        "policy": first.get("policy"),
        "opponent": first.get("opponent"),
        "games": len(by_game),
        "unfinished": len({(r["seed"], r["save"]) for r in rows if r.get("end") != "terminated"}),
        "by_list": by_list,
        "stratagems": per_game(lambda u: u["name"]),
        "stratagem_times": per_game(
            lambda u: f"{u['phase'].capitalize()}, {'own' if u['own_turn'] else 'opponent’s'} turn"
        ),
    }


@router.get("/diagnoses")
async def list_diagnoses() -> list[dict]:
    out = []
    for path in _files():
        rows = _read(path)
        first = rows[0] if rows else {}
        out.append({
            "name": path.name,
            "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "policy": first.get("policy"),
            "opponent": first.get("opponent"),
            "games": len({(r["seed"], r["save"]) for r in rows}),
        })
    return out


@router.get("/diagnoses/{name}")
async def get_diagnosis(name: str, session: AsyncSession = Depends(get_session)) -> dict:
    path = next((p for p in _files() if p.name == name), None)
    if path is None:
        raise HTTPException(status_code=404, detail="no diagnose file by that name")
    rows = _read(path)
    ids = {r["list_id"] for r in rows if "list_id" in r}
    result = await session.execute(select(ArmyList.id, ArmyList.name).where(ArmyList.id.in_(ids)))
    names = {i: n for i, n in result.all()}
    return {"name": name, **summarize(rows, names)}
