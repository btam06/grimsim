from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from app.config import settings
from app.engine import state
from app.engine.catalog import Catalog

# Autosaves: a game's state as it's made, and at the start of each phase, so
# it can be played again from there (restore). Each game has a folder under
# settings.saves_dir: catalog.json (what it's played with - see
# app/engine/catalog.py), setup.json (the game as it was made: into
# deployment, nothing deployed yet - e.g. to learn deployment from), and a
# file per phase
# it's reached, named for the battle round, whose turn and the phase - e.g.
# r2-s1-shooting.json. Deleting a game deletes its folder.
#
# A game put away while it's being played (see app/engine/store.py
# evict_idle) is saved just as it is, to current.json - and comes back from
# whichever is newer, that or its latest phase. summary.json is what the
# games list shows of it (see app/routers/games.py list_games), as of its
# newest save.

VERSION = 1
CATALOG = "catalog.json"
CURRENT = "current.json"
SETUP = "setup.json"
SUMMARY = "summary.json"


def folder(game_id: int) -> Path:
    return Path(settings.saves_dir) / str(game_id)


def name(game: state.Game) -> str | None:
    # Its save's name where it is now - None if it isn't in a phase.
    if game.status != "in_progress" or game.phase is None:
        return None
    return f"r{game.battle_round}-s{game.turn_seat}-{game.phase}.json"


def saved(game_id: int, save_name: str) -> bool:
    return (folder(game_id) / save_name).exists()


def autosave(game: state.Game, catalog: Catalog, summary: dict | None = None) -> Path | None:
    # Saves the game at the start of the phase it's in (the catalog too,
    # with anything it's added).
    save_name = name(game)
    if save_name is None:
        return None
    return _save(game, catalog, save_name, summary)


def save_setup(game: state.Game, catalog: Catalog, summary: dict | None = None) -> Path:
    # Saves the game as it's made (see SETUP).
    return _save(game, catalog, SETUP, summary)


def save_current(game: state.Game, catalog: Catalog, summary: dict | None = None) -> Path:
    # Saves the game as it is now (see CURRENT).
    return _save(game, catalog, CURRENT, summary)


def _save(game: state.Game, catalog: Catalog, save_name: str, summary: dict | None) -> Path:
    path = folder(game.id) / save_name
    _write(folder(game.id) / CATALOG, {"version": VERSION, "catalog": catalog.to_dict()})
    _write(path, {"version": VERSION, "game": game.to_dict()})
    if summary is not None:
        _write(folder(game.id) / SUMMARY, summary)
    return path


def latest(game_id: int) -> Path | None:
    # Where the game comes back from: its newest save - as it was put away,
    # or the start of its latest phase.
    found = saves(game_id) + [p for p in [folder(game_id) / CURRENT] if p.exists()]
    return max(found, key=lambda p: p.stat().st_mtime, default=None)


def summary(game_id: int) -> dict | None:
    path = folder(game_id) / SUMMARY
    return json.loads(path.read_text()) if path.exists() else None


def restore(path: str | Path) -> tuple[state.Game, Catalog]:
    # The game as saved at `path`, and its catalog - ready to play on.
    path = Path(path)
    data = json.loads(path.read_text())
    catalog = Catalog.from_dict(json.loads((path.parent / CATALOG).read_text())["catalog"])
    game = state.Game.from_dict(data["game"])
    highest = 0
    for record in game.records():
        for attr, (id_attr, class_name) in record._refs.items():
            ref_id = getattr(record, id_attr)
            if ref_id is not None:
                object.__setattr__(record, attr, catalog.get(class_name, ref_id))
        if record is not game:
            highest = max(highest, getattr(record, "id", None) or 0)
    # Its records' ids carry on from its own count (see app/engine/state.py).
    game.record_ids = max(game.record_ids, highest)
    return game, catalog


def saves(game_id: int) -> list[Path]:
    # A game's saves, oldest first.
    found = [p for p in folder(game_id).glob("r*.json")] + [
        p for p in [folder(game_id) / SETUP] if p.exists()
    ]
    return sorted(found, key=lambda p: p.stat().st_mtime)


def delete(game_id: int) -> None:
    shutil.rmtree(folder(game_id), ignore_errors=True)


def _write(path: Path, data: dict) -> None:
    # All at once: never a half-written save.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    os.replace(tmp, path)
