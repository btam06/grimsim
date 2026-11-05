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
#     env = GameEnv("saves/1/setup.json", seat=1)
#     obs, info = env.reset(seed=0)
#     while True:
#         index = policy(obs)            # one of obs["actions"]
#         obs, reward, terminated, truncated, info = env.step(index)
#         if terminated or truncated:
#             obs, info = env.reset()
#
# Each episode starts from a save (see app/engine/saves.py) - one of
# several, picked at random; setup.json, made with the game, plays its
# deployment too - with dice of its own (a new seed for the
# game's rolls - see app/services/dice.py). An observation is what the
# player whose decision it is sees (see app/engine/features.py): an action
# is the index of one of its legal actions. Only actions that can be taken
# as listed are offered (see app/routers/agent.py - "concrete").
#
# With `seat`, the env plays that seat: the other's decisions are taken by
# `opponent` (by default, at random) and rewards are that seat's ("random":
# either seat, picked each episode). Without
# it, both seats are played through the env (self-play): each step's reward
# is for the player who took it, and info["rewards"] has both players'.
#
# Reward: for VP as they're scored - `primary_reward` for each player's
# primary VP over VP_CAP (the most a battle gives), `secondary_reward` for
# their secondary VP (each counted up to VP_CAP), and `lead_reward` for
# their lead (their VP minus their opponent's) over VP_CAP - and at the end,
# `win_reward` for a win (minus that for a loss, nothing for a draw). A
# player maxing out both kinds gets less than a win; points for playing
# well (damage, kills) are left out, as a battle can be won by a player
# with no models left. An action the game refuses leaves it
# as it was (info["refused"] says why) and isn't offered again until
# something else happens.


# The most primary VP a battle gives (and secondary VP rewarded) - see
# app/services/in_game/scoring.py.
VP_CAP = 45


def standing(game) -> dict[int, tuple[int, int, int]]:
    # Each seat's primary VP and secondary VP (each up to VP_CAP), and all
    # its VP.
    found = {}
    for p in game.players:
        primary = sum(s.points for s in p.scores if s.kind == "primary")
        secondary = sum(s.points for s in p.scores if s.kind == "secondary")
        found[p.seat] = (min(primary, VP_CAP), min(secondary, VP_CAP), features.vp(game, p.seat))
    return found


def left_on_table(game) -> dict[int, dict[str, int]]:
    # The VP each seat didn't score, of the VP_CAP primary and VP_CAP
    # secondary a battle gives - and where some of it went: lost to the caps
    # (per battle round, and battle), and on tactical secondaries discarded,
    # or met but held and never claimed (what they were last held at).
    standings = standing(game)
    found = {}
    for p in game.players:
        primary, secondary, _ = standings[p.seat]
        capped = {"primary": 0, "secondary": 0}
        for score in p.scores:
            for reason in score.reasons:
                if score.kind in capped and reason.text.startswith("Capped at"):
                    capped[score.kind] -= reason.points
        cards = {c.id: c for c in p.secondaries}
        held = {}
        for offer in game.claim_offers:
            if offer.game_secondary_id in cards and offer.status == "held":
                held[offer.game_secondary_id] = offer.points
        tactical = [c for c in p.secondaries if not c.fixed]
        found[p.seat] = {
            "left": 2 * VP_CAP - primary - secondary,
            "primary_left": VP_CAP - primary,
            "secondary_left": VP_CAP - secondary,
            "primary_capped": capped["primary"],
            "secondary_capped": capped["secondary"],
            "discarded": sum(c.status == "discarded" for c in tactical),
            "achieved": sum(c.status == "achieved" for c in tactical),
            "held_unclaimed": sum(
                points for card_id, points in held.items()
                if cards[card_id].status != "achieved"
            ),
        }
    return found


def army_left(game) -> dict[int, dict[str, int]]:
    # The points of each seat's units still in the battle (a model left, on
    # the battlefield or in Reserves), and of those destroyed.
    destroyed = {d.unit_id for d in game.models_destroyed if d.unit_destroyed}
    found = {}
    for p in game.players:
        units = p.army_list.units
        lost = sum(u.points or 0 for u in units if u.id in destroyed)
        found[p.seat] = {
            "points_left": sum(u.points or 0 for u in units) - lost,
            "points_lost": lost,
        }
    return found


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
    # A legal action at random - but less often moving the game on (advance,
    # end_phase) while there's something else to do.
    actions = decision.actions
    others = [i for i, a in enumerate(actions) if a["type"] not in ("advance", "end_phase")]
    if others and rng.random() > 0.2:
        return rng.choice(others)
    return rng.randrange(len(actions))


class GameEnv:
    def __init__(
        self,
        saves: str | Path | list[str | Path],
        seat: int | str | None = None,
        opponent: Policy = random_policy,
        primary_reward: float = 0.25,
        secondary_reward: float = 0.25,
        lead_reward: float = 0.5,
        win_reward: float = 1.0,
        max_steps: int = 5000,
        seed: int | None = None,
    ) -> None:
        self.saves = [str(p) for p in ([saves] if isinstance(saves, (str, Path)) else saves)]
        self.seats = seat
        self.seat = seat if seat != "random" else None
        self.opponent = opponent
        self.primary_reward = primary_reward
        self.secondary_reward = secondary_reward
        self.lead_reward = lead_reward
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
        self.save = str(save) if save is not None else self.rng.choice(self.saves)
        game, catalog = _restored(self.save)
        game = copy.deepcopy(game)
        if self.seats == "random":
            self.seat = self.rng.choice([p.seat for p in game.players])
        game.rng_seed = self.rng.getrandbits(63)
        game.rng_rolls = 0
        self.engine = Engine(Live(game, catalog, autosave=False))
        self.steps = 0
        self._refused: set[str] = set()
        self._standing = standing(game)
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
        now = standing(self.game)
        for seat in rewards:
            rewards[seat] += self._earned(self._standing, now, seat)
        self._standing = now
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

    def _earned(self, before: dict, after: dict, seat: int) -> float:
        # The reward for VP scored between two standings (see standing).
        (other,) = (s for s in after if s != seat)
        primary = after[seat][0] - before[seat][0]
        secondary = after[seat][1] - before[seat][1]
        lead = (after[seat][2] - after[other][2]) - (before[seat][2] - before[other][2])
        return (
            self.primary_reward * primary
            + self.secondary_reward * secondary
            + self.lead_reward * lead
        ) / VP_CAP

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
            "save": self.save,
            "actions": self.decision.actions if self.decision else [],
            "rewards": rewards,
            "vp": {p.seat: features.vp(game, p.seat) for p in game.players},
            # (At the end: the VP each seat left on the table - see
            # left_on_table.)
            "left": (
                {seat: found["left"] for seat, found in left_on_table(game).items()}
                if done == "terminated" else None
            ),
            # (And the points of their units still in the battle.)
            "points_left": (
                {seat: found["points_left"] for seat, found in army_left(game).items()}
                if done == "terminated" else None
            ),
            "refused": refused,
            "steps": self.steps,
            "state": f"round {game.battle_round}, seat {game.turn_seat}, {game.phase or game.status}",
            "done": done,
        }
