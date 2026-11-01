from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.engine import saves, state
from app.engine.context import Live

# The games being played, in memory, by id. A game not here (e.g. after the
# server restarts) comes back from its latest autosave - the start of the
# phase it was in (see app/engine/saves.py).

_games: dict[int, Live] = {}


def put(live: Live) -> None:
    _games[live.game.id] = live


def get(game_id: int) -> Live | None:
    live = _games.get(game_id)
    if live is None:
        found = saves.saves(game_id)
        if found:
            game, catalog = saves.restore(found[-1])
            live = _games[game_id] = Live(game, catalog)
    return live


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
