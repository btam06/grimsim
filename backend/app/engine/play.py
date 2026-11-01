from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import context, saves, state, store
from app.engine.context import Live
from app.schemas import GameIn

# Playing a game from Python, without HTTP or the database - e.g. for machine
# learning:
#
#     engine = await Engine.create(session, game_in)   # reads the database once
#     engine = Engine.load("saves/12/r2-s1-shooting.json")   # or not at all
#     decision = await engine.decision()   # whose turn, and every legal action
#     result = await engine.apply("advance", seat=1)
#     before = engine.snapshot(); ...; engine.restore(before)
#
# Actions are the agent interface's (see app/routers/agent.py): a type, the
# seat taking it and its params, as listed in decision()["actions"]. The game
# is the same one the HTTP API plays (it's in the store - see
# app/engine/store.py), so the two can be mixed.


class Engine:
    def __init__(self, live: Live) -> None:
        self.live = live
        store.put(live)

    @classmethod
    async def create(
        cls, session: AsyncSession, game_in: GameIn | dict, autosave: bool = True
    ) -> Engine:
        # A new game, set up as POST /games would.
        from app.services.in_game import game as game_service

        if isinstance(game_in, dict):
            game_in = GameIn(**game_in)
        live = await game_service.create_game(session, game_in)
        live.autosave = autosave
        engine = cls(live)
        with context.bound(live):
            game_service.enter_deployment(live.game)
        return engine

    @classmethod
    def load(cls, path: str | Path, autosave: bool = False) -> Engine:
        # The game as saved at `path` (see app/engine/saves.py) - played on as
        # a new game in memory (keeping its id: it replaces the game in memory
        # if that one's there).
        game, catalog = saves.restore(path)
        live = Live(game, catalog, autosave=autosave)
        return cls(live)

    @classmethod
    def of(cls, game_id: int) -> Engine:
        # A game already in memory (or saved), e.g. one made through the API.
        live = store.get(game_id)
        if live is None:
            raise KeyError(game_id)
        return cls(live)

    @property
    def game(self) -> state.Game:
        return self.live.game

    @property
    def id(self) -> int:
        return self.live.game.id

    async def decision(self) -> dict[str, Any]:
        # Whose decision the game is waiting on, and every legal action now
        # (see app/routers/agent.py).
        from app.routers import agent

        with context.bound(self.live):
            return await agent._decision(None, self.id)

    async def apply(
        self, type: str, seat: int, params: dict | None = None, listed: set[str] | None = None
    ) -> dict[str, Any]:
        # Takes an action: its log entry - ok, or the error (the game's left
        # as it was). `listed`: the keys of the actions listed as legal (see
        # app/routers/agent.py _key), to check it against.
        from app.routers import agent

        action = agent.AgentActionIn(type=type, seat=seat, params=params or {})
        with context.bound(self.live):
            return await agent._do(None, self.id, action, listed or set())

    def snapshot(self) -> state.Game:
        # A copy of the game as it is now (sharing its catalog), to go back to.
        return copy.deepcopy(self.live.game)

    def restore(self, snapshot: state.Game) -> None:
        # The game as it was at `snapshot` (which is kept: restore it again).
        self.live.game = copy.deepcopy(snapshot)

    def save(self) -> Path | None:
        # Saved now, if it's at the start of a phase (see app/engine/saves.py).
        return saves.autosave(self.live.game, self.live.catalog)

    def close(self) -> None:
        # Forgotten from memory (its saves stay).
        store.forget(self.id)
