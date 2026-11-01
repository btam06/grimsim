from __future__ import annotations

import contextvars
import copy
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.engine import state
from app.engine.catalog import Catalog
from app.services import dice

# The game being played - its state and its catalog - while it's played: the
# game code that reads the catalog (stratagems, units as the calculator sees
# them, mission cards, ...) doesn't always have the game to hand, so it finds
# it here (see catalog()). A request or engine call binds the game it's for
# (see bind); its dice are bound with it (see app/services/dice.py).


@dataclass(eq=False)
class Live:
    game: state.Game
    catalog: Catalog
    # The agent interface's log (see app/routers/agent.py), newest last.
    agent_log: list[dict[str, Any]] = field(default_factory=list)
    # Its catalog is out of date: read again from the database when the
    # game's next loaded with one (see app/routers/games.py _load_game).
    stale: bool = False

    def snapshot(self) -> state.Game:
        # A copy of its state (sharing the catalog) - to go back to.
        return copy.deepcopy(self.game)

    def restore(self, snapshot: state.Game) -> None:
        self.game = snapshot
        if _current.get() is self:
            dice.bind(snapshot)


_current: contextvars.ContextVar[Live | None] = contextvars.ContextVar("live", default=None)


def current() -> Live | None:
    return _current.get()


def catalog() -> Catalog:
    # The bound game's catalog (there must be one).
    live = _current.get()
    if live is None:
        raise RuntimeError("no game bound")
    return live.catalog


def bind(live: Live | None) -> None:
    # For the rest of the request (or engine call).
    _current.set(live)
    dice.bind(live.game if live is not None else None)


@contextmanager
def bound(live: Live) -> Iterator[Live]:
    token = _current.set(live)
    try:
        with dice.bound(live.game):
            yield live
    finally:
        _current.reset(token)


# A request that changes a game is all or nothing: the game as it was when
# the request loaded it is kept (see track), and put back if the request
# fails (see app/main.py).


@dataclass(eq=False)
class Request:
    changes: bool
    loaded: list[tuple[Live, state.Game]] = field(default_factory=list)


_request: contextvars.ContextVar[Request | None] = contextvars.ContextVar("request", default=None)


def begin_request(changes: bool) -> Request:
    request = Request(changes)
    _request.set(request)
    bind(None)
    return request


def track(live: Live) -> None:
    # A game the request has loaded (once): kept as it was, if the request
    # changes things.
    request = _request.get()
    if request is None or not request.changes:
        return
    if any(seen is live for seen, _ in request.loaded):
        return
    request.loaded.append((live, live.snapshot()))


def end_request(request: Request, failed: bool) -> None:
    for live, snapshot in request.loaded:
        if failed:
            live.restore(snapshot)
    request.loaded.clear()
