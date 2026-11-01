from __future__ import annotations

import time
from pathlib import Path

from app.config import settings
from app.engine import saves, state
from app.engine.context import Live

# The games being played, in memory, by id. A game not here (e.g. after the
# server restarts) comes back from its newest save - the start of the phase
# it was in, or as it was when it was put away (see app/engine/saves.py).
#
# Only games in use stay in memory: one no request has used for a while is
# saved as it is and put away (see idle and app/routers/games.py
# evict_idle) - unless it's played from Python (pinned - see
# app/engine/play.py), or isn't saved at all.

_games: dict[int, Live] = {}


def put(live: Live) -> None:
    _games[live.game.id] = live


def get(game_id: int) -> Live | None:
    live = _games.get(game_id)
    if live is None:
        found = saves.latest(game_id)
        if found is not None:
            game, catalog = saves.restore(found)
            live = _games[game_id] = Live(game, catalog)
    return live


def peek(game_id: int) -> Live | None:
    # The game if it's in memory (not brought back if it isn't).
    return _games.get(game_id)


def idle(max_idle: float) -> list[Live]:
    # The games in memory no request has used for `max_idle` seconds, that
    # can be put away: saved, not in use, not played from Python.
    now = time.monotonic()
    return [
        live
        for live in _games.values()
        if live.autosave and not live.pinned and not live.busy and now - live.touched >= max_idle
    ]


def ids() -> list[int]:
    # Every game's id - in memory, or saved - in order.
    saved = (
        int(p.name) for p in Path(settings.saves_dir).glob("*") if p.is_dir() and p.name.isdigit()
    )
    return sorted(set(_games) | set(saved))


def remove(game_id: int) -> None:
    _games.pop(game_id, None)
    saves.delete(game_id)


def forget(game_id: int) -> None:
    # Out of memory (its saves stay: it comes back from the latest).
    _games.pop(game_id, None)


def mark_stale() -> None:
    # Every game's catalog is out of date (see Live.stale).
    for live in _games.values():
        live.stale = True


def clear() -> None:
    # Forgets every game in memory (their saves stay) - for tests.
    _games.clear()


def start() -> None:
    # New games' ids come after every saved game's.
    state.game_ids_from(max(ids(), default=0) + 1)
