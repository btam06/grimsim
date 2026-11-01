from __future__ import annotations

import os

# Played from saves, a game needs no database - but app.config insists on a
# URL (unused here).
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import copy  # noqa: E402
import functools  # noqa: E402
import random  # noqa: E402
from collections.abc import Callable  # noqa: E402
from pathlib import Path  # noqa: E402

from app.engine import context, features, saves  # noqa: E402
from app.engine.context import Live  # noqa: E402
from app.engine.play import Engine  # noqa: E402

# A game as a machine learning environment, in the style of Gymnasium's
# (reset, then step until it's over) - plain Python, nothing to install:
#
#     env = GameEnv("saves/1/r1-s2-start_of_round.json", seat=1)
#     obs, info = env.reset(seed=0)
#     while True:
#         index = policy(obs)            # one of obs["actions"]
#         obs, reward, terminated, truncated, info = env.step(index)
#         if terminated or truncated:
#             obs, info = env.reset()
#
# Each episode starts from a save (see app/engine/saves.py) - one of
# several, picked at random - with dice of its own (a new seed for the
# game's rolls - see app/services/dice.py). An observation is what the
# player whose decision it is sees (see app/engine/features.py): an action
# is the index of one of its legal actions. Only actions that can be taken
# as listed are offered (see app/routers/agent.py - "concrete").
#
# With `seat`, the env plays that seat: the other's decisions are taken by
# `opponent` (by default, at random) and rewards are that seat's. Without
# it, both seats are played through the env (self-play): each step's reward
# is for the player who took it, and info["rewards"] has both players'.
#
# Reward: the change in the player's VP lead (their VP minus their
# opponent's) over `vp_scale`, and at the end, `win_reward` for a win (minus
# that for a loss, nothing for a draw). An action the game refuses leaves it
# as it was (info["refused"] says why) and isn't offered again until
# something else happens.


@functools.cache
def _restored(path: str):
    # A save, restored once: each episode plays a copy of it.
    return saves.restore(path)


class Decision:
    # A decision for a policy to take: whose it is, the legal actions (the
    # agent interface's dicts), and what that player sees - worked out only
    # if asked for.
    def __init__(self, live: Live, seat: int, actions: list[dict]) -> None:
        self.live, self.seat, self.actions = live, seat, actions

    @functools.cached_property
    def obs(self) -> dict:
        with context.bound(self.live):
            return features.observe(self.live.game, self.seat, self.actions)


Policy = Callable[[Decision, random.Random], int]


def random_policy(decision: Decision, rng: random.Random) -> int:
    # A legal action at random - but less often moving the game on (advance)
    # while there's something else to do.
    actions = decision.actions
    others = [i for i, a in enumerate(actions) if a["type"] != "advance"]
    if others and rng.random() > 0.2:
        return rng.choice(others)
    return rng.randrange(len(actions))


class GameEnv:
    def __init__(
        self,
        saves: str | Path | list[str | Path],
        seat: int | None = None,
        opponent: Policy = random_policy,
        vp_scale: float = 100.0,
        win_reward: float = 1.0,
        max_steps: int = 5000,
        seed: int | None = None,
    ) -> None:
        self.saves = [str(p) for p in ([saves] if isinstance(saves, (str, Path)) else saves)]
        self.seat = seat
        self.opponent = opponent
        self.vp_scale = vp_scale
        self.win_reward = win_reward
        self.max_steps = max_steps
        self.rng = random.Random(seed)
        self.engine: Engine | None = None
        self.decision: Decision | None = None

    @property
    def game(self):
        return self.engine.game

    def reset(self, seed: int | None = None, save: str | Path | None = None) -> tuple[dict, dict]:
        # A new episode, from `save` (or one of the env's saves, at random).
        if seed is not None:
            self.rng.seed(seed)
        self.close_game()
        game, catalog = _restored(str(save) if save is not None else self.rng.choice(self.saves))
        game = copy.deepcopy(game)
        game.rng_seed = self.rng.getrandbits(63)
        game.rng_rolls = 0
        self.engine = Engine(Live(game, catalog, autosave=False))
        self.steps = 0
        self._refused: set[str] = set()
        self._lead = self._vp_lead()
        rewards = {p.seat: 0.0 for p in game.players}
        done = self._next(rewards)
        return self._observe(), self._info(rewards, done)

    def step(self, index: int) -> tuple[dict, float, bool, bool, dict]:
        decision = self.decision
        if decision is None:
            raise RuntimeError("the episode is over: reset first")
        rewards = {p.seat: 0.0 for p in self.game.players}
        refused = self._apply(decision, index, rewards)
        done = self._next(rewards)
        info = self._info(rewards, done, refused)
        return self._observe(), rewards[decision.seat], done == "terminated", done == "truncated", info

    def close_game(self) -> None:
        if self.engine is not None:
            self.engine.close()
            self.engine = None

    def close(self) -> None:
        self.close_game()

    # Playing on.

    def _run(self, coroutine):
        # The engine's coroutines never wait on anything (no database, no
        # I/O), so each runs to its end in one go - no event loop needed (and
        # so the env works inside one too).
        try:
            coroutine.send(None)
        except StopIteration as done:
            return done.value
        coroutine.close()
        raise RuntimeError("the engine waited on something: it can't be played synchronously")

    def _apply(self, decision: Decision, index: int, rewards: dict) -> str | None:
        # Takes one of the decision's actions; why it was refused, if it was.
        from app.routers.agent import _key

        action = decision.actions[index]
        params = dict(action["params"])
        if action.get("placement"):
            params["positions"] = action["placement"]["default"]
        result = self._run(self.engine.apply(action["type"], decision.seat, params))
        self.steps += 1
        if not result["ok"]:
            self._refused.add(_key(action["type"], decision.seat, action["params"]))
            return result["error"] or "refused"
        self._refused.clear()
        lead = self._vp_lead()
        for seat in rewards:
            change = lead - self._lead
            rewards[seat] += (change if seat == self._first_seat() else -change) / self.vp_scale
        self._lead = lead
        return None

    def _next(self, rewards: dict) -> str | None:
        # On to the next decision for the env's player (the other's taken by
        # the opponent, if the env plays one seat): None - or how it ended
        # ("terminated": the game's over; "truncated": too many steps, or no
        # action to take).
        from app.routers.agent import _key

        while True:
            self.decision = None
            if self.game.status == "finished":
                self._final(rewards)
                return "terminated"
            if self.steps >= self.max_steps:
                return "truncated"
            listed = self._run(self.engine.decision())
            if listed["state"].startswith("finished"):
                self._final(rewards)
                return "terminated"
            seat = listed["waiting_for"]["seat"]
            actions = [
                a
                for a in listed["actions"]
                if a["seat"] == seat
                and a["concrete"]
                and _key(a["type"], a["seat"], a["params"]) not in self._refused
            ]
            if seat is None or not actions:
                return "truncated"
            decision = Decision(self.engine.live, seat, actions)
            if self.seat is None or seat == self.seat:
                self.decision = decision
                return None
            self._apply(decision, self.opponent(decision, self.rng), rewards)

    def _final(self, rewards: dict) -> None:
        first = self._first_seat()
        lead = self._vp_lead()
        for seat in rewards:
            mine = lead if seat == first else -lead
            rewards[seat] += self.win_reward * ((mine > 0) - (mine < 0))

    def _first_seat(self) -> int:
        return min(p.seat for p in self.game.players)

    def _vp_lead(self) -> int:
        # The lower seat's VP minus the other's.
        first = self._first_seat()
        return sum(
            features.vp(self.game, p.seat) * (1 if p.seat == first else -1)
            for p in self.game.players
        )

    def _observe(self) -> dict:
        if self.decision is None:
            # Over: what the env's player (or the last to decide) sees.
            seat = self.seat or self._first_seat()
            with context.bound(self.engine.live):
                return features.observe(self.game, seat, [])
        return self.decision.obs

    def _info(self, rewards: dict, done: str | None, refused: str | None = None) -> dict:
        game = self.game
        return {
            "seat": self.decision.seat if self.decision else None,
            "actions": self.decision.actions if self.decision else [],
            "rewards": rewards,
            "vp": {p.seat: features.vp(game, p.seat) for p in game.players},
            "refused": refused,
            "steps": self.steps,
            "state": f"round {game.battle_round}, seat {game.turn_seat}, {game.phase or game.status}",
            "done": done,
        }
