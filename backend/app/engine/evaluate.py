from __future__ import annotations

import argparse
import importlib
import math
import multiprocessing as mp
import random
import time
from dataclasses import asdict, dataclass, field

from app.engine.env import Decision, GameEnv, Policy, random_policy

# How good a policy is: games against another (by default, random play),
# from saves, seats taken in turn - its wins, draws and losses, and VP.
#
#     result = evaluate(my_policy, saves=["saves/3/r1-s2-start_of_round.json"], games=40)
#     print(result.summary())
#
# A policy takes a Decision and a random.Random and returns the index of
# one of the decision's actions (see app/engine/env.py). Game i uses seed
# `seed + i`, so the same policies and seed play the same games. With
# `processes`, games are played in parallel (the policies must be
# picklable: functions defined at module level).
#
# From the command line (policies as module:function):
#
#     python -m app.engine.evaluate saves/3/r1-s2-start_of_round.json \
#         --policy app.engine.scripted:scripted --games 40 --processes 4


@dataclass
class GameResult:
    seed: int
    save: str
    seat: int  # the policy's
    vp: int  # the policy's
    opponent_vp: int
    steps: int
    # How it ended: "terminated" (finished) or "truncated" (step limit, or
    # stuck).
    end: str
    seconds: float

    @property
    def outcome(self) -> str:
        if self.end != "terminated":
            return "unfinished"
        return "win" if self.vp > self.opponent_vp else "loss" if self.vp < self.opponent_vp else "draw"


@dataclass
class Result:
    games: list[GameResult] = field(default_factory=list)

    def count(self, outcome: str) -> int:
        return sum(g.outcome == outcome for g in self.games)

    @property
    def win_rate(self) -> float:
        # Draws count half; unfinished games don't count.
        finished = [g for g in self.games if g.outcome != "unfinished"]
        if not finished:
            return 0.0
        return (self.count("win") + 0.5 * self.count("draw")) / len(finished)

    @property
    def interval(self) -> tuple[float, float]:
        # The win rate's 95% confidence interval (Wilson's).
        n = sum(g.outcome != "unfinished" for g in self.games)
        if not n:
            return 0.0, 1.0
        p, z = self.win_rate, 1.96
        middle = (p + z * z / (2 * n)) / (1 + z * z / n)
        spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return max(0.0, middle - spread), min(1.0, middle + spread)

    @property
    def vp_difference(self) -> float:
        # The policy's VP minus its opponent's, on average.
        if not self.games:
            return 0.0
        return sum(g.vp - g.opponent_vp for g in self.games) / len(self.games)

    def summary(self) -> str:
        low, high = self.interval
        n = len(self.games)
        steps = sum(g.steps for g in self.games) / n if n else 0
        seconds = sum(g.seconds for g in self.games) / n if n else 0
        return (
            f"{n} games: {self.count('win')} won, {self.count('draw')} drawn, "
            f"{self.count('loss')} lost, {self.count('unfinished')} unfinished - "
            f"win rate {self.win_rate:.0%} (95%: {low:.0%}-{high:.0%}), "
            f"VP difference {self.vp_difference:+.1f}; "
            f"{steps:.0f} steps and {seconds:.0f}s a game"
        )

    def to_dict(self) -> dict:
        return {
            "win_rate": self.win_rate,
            "interval": self.interval,
            "vp_difference": self.vp_difference,
            "games": [asdict(g) | {"outcome": g.outcome} for g in self.games],
        }


def evaluate(
    policy: Policy,
    saves: str | list[str],
    opponent: Policy = random_policy,
    games: int = 20,
    seed: int = 0,
    max_steps: int = 5000,
    processes: int = 1,
) -> Result:
    saves = [saves] if isinstance(saves, str) else list(saves)
    jobs = [(policy, opponent, saves, seed + i, max_steps) for i in range(games)]
    if processes > 1:
        with mp.get_context("spawn").Pool(processes) as pool:
            return Result(pool.map(_play, jobs))
    return Result([_play(job) for job in jobs])


def _play(job) -> GameResult:
    # One game: the policy takes seat 1 in even games and seat 2 in odd ones,
    # the saves in turn.
    policy, opponent, saves, game_seed, max_steps = job
    seat = 1 if game_seed % 2 == 0 else 2
    save = saves[(game_seed // 2) % len(saves)]
    env = GameEnv(save, seat=seat, opponent=opponent, max_steps=max_steps, seed=game_seed)
    rng = random.Random(game_seed)
    started = time.time()
    try:
        _, info = env.reset()
        done = info["done"]
        while done is None:
            decision = env.decision
            _, _, _, _, info = env.step(policy(decision, rng))
            done = info["done"]
        vp = info["vp"]
        return GameResult(
            seed=game_seed,
            save=save,
            seat=seat,
            vp=vp[seat],
            opponent_vp=vp[3 - seat],
            steps=info["steps"],
            end=done,
            seconds=time.time() - started,
        )
    finally:
        env.close()


def _load(spec: str) -> Policy:
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)


def first_action(decision: Decision, rng: random.Random) -> int:
    # Always the first listed action - a fixed baseline.
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Play a policy against another.")
    parser.add_argument("saves", nargs="+", help="saves to start games from")
    parser.add_argument("--policy", default="app.engine.env:random_policy")
    parser.add_argument("--opponent", default="app.engine.env:random_policy")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=5000)
    parser.add_argument("--processes", type=int, default=1)
    args = parser.parse_args(argv)
    result = evaluate(
        _load(args.policy),
        args.saves,
        opponent=_load(args.opponent),
        games=args.games,
        seed=args.seed,
        max_steps=args.max_steps,
        processes=args.processes,
    )
    for game in result.games:
        print(
            f"  seed {game.seed}, seat {game.seat}: {game.outcome} "
            f"{game.vp}-{game.opponent_vp} ({game.steps} steps, {game.seconds:.0f}s)"
        )
    print(result.summary())


if __name__ == "__main__":
    main()
