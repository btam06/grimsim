from __future__ import annotations

import argparse
import gzip
import json
import multiprocessing as mp
import random
from pathlib import Path

# Learning from a teacher - any policy (see backend/app/engine/env.py
# Policy), e.g. a scripted player: record its games, then train the model
# (see ml/model.py) to choose as it did - and to guess each player's return
# from there (the value). The checkpoint can start PPO (ml.ppo --init).
#
#     ml/.venv/bin/python -m ml.imitate record saves/1/setup.json \
#         --teacher app.engine.scripted:scripted --games 200 --processes 4 --data ml/data/scripted
#     ml/.venv/bin/python -m ml.imitate train ml/data/scripted --run imitated
#
# A game is a file of its decisions (gzipped JSON lines: what the player
# saw, the action they took, their return from there). Training reads the
# files a few at a time, so the data needn't fit in memory.
#
# (torch is imported inside the functions that need it: recording doesn't.)

DATA = Path(__file__).parent / "data"
RUNS = Path(__file__).parent / "runs"


def record(
    saves: list[str],
    teacher: str,
    games: int,
    data: Path,
    seed: int = 0,
    max_steps: int = 5000,
    gamma: float = 0.995,
    processes: int = 1,
) -> list[Path]:
    data.mkdir(parents=True, exist_ok=True)
    jobs = [(saves, teacher, seed + i, data, max_steps, gamma) for i in range(games)]
    if processes > 1:
        with mp.get_context("spawn").Pool(processes) as pool:
            return pool.map(_record_game, jobs)
    return [_record_game(job) for job in jobs]


def _record_game(job) -> Path:
    # One game, the teacher playing both players.
    from app.engine.env import GameEnv
    from app.engine.evaluate import _load

    saves, teacher, game_seed, data, max_steps, gamma = job
    policy = _load(teacher)
    env = GameEnv(saves, max_steps=max_steps, seed=game_seed)
    rng = random.Random(game_seed)
    decisions: list[dict] = []
    # Each player's decisions (indexes into `decisions`), and the rewards
    # each decision got before that player's next one.
    by_seat: dict[int, list[int]] = {}
    rewards: list[float] = []
    try:
        obs, info = env.reset()
        while info["done"] is None:
            seat = info["seat"]
            index = policy(env.decision, rng)
            decisions.append({"obs": obs, "action": index, "seat": seat})
            rewards.append(0.0)
            by_seat.setdefault(seat, []).append(len(decisions) - 1)
            obs, _, _, _, info = env.step(index)
            for s, reward in info["rewards"].items():
                if by_seat.get(int(s)):
                    rewards[by_seat[int(s)][-1]] += reward
    finally:
        env.close()
    # Each decision's return: its player's rewards from there on, discounted
    # by their decisions.
    for indexes in by_seat.values():
        following = 0.0
        for i in reversed(indexes):
            following = rewards[i] + gamma * following
            decisions[i]["return"] = following
    path = data / f"game-{game_seed}.jsonl.gz"
    with gzip.open(path, "wt") as out:
        for decision in decisions:
            out.write(json.dumps(decision, separators=(",", ":")) + "\n")
    return path


def train(
    data: Path,
    run: str,
    epochs: int = 5,
    lr: float = 3e-4,
    minibatch: int = 128,
    hidden: int = 128,
    value_weight: float = 0.5,
    holdout: float = 0.1,
    games_at_once: int = 8,
    init: str | None = None,
    seed: int = 0,
    threads: int = 4,
) -> Path:
    import torch

    from ml import batch, model

    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    rng = random.Random(seed)
    files = sorted(Path(data).glob("game-*.jsonl.gz"))
    if not files:
        raise SystemExit(f"no recorded games in {data}")
    rng.shuffle(files)
    held = files[: max(1, int(len(files) * holdout))] if len(files) > 1 else []
    training = [f for f in files if f not in held]
    policy = model.load(init) if init else model.Policy(hidden=hidden)
    optimiser = torch.optim.Adam(policy.parameters(), lr=lr)
    folder = RUNS / run
    for epoch in range(1, epochs + 1):
        policy.train()
        rng.shuffle(training)
        totals = {"loss": 0.0, "accuracy": 0.0}
        batches = 0
        for steps in _chunks(training, games_at_once, rng):
            for start in range(0, len(steps), minibatch):
                part = steps[start : start + minibatch]
                logits, values = policy(batch.collate([s[0] for s in part]))
                actions = torch.tensor([s[1] for s in part])
                returns = torch.tensor([s[2] for s in part])
                policy_loss = torch.nn.functional.cross_entropy(logits, actions)
                value_loss = (values - returns).pow(2).mean()
                loss = policy_loss + value_weight * value_loss
                optimiser.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
                optimiser.step()
                totals["loss"] += policy_loss.item()
                totals["accuracy"] += float((logits.argmax(-1) == actions).float().mean())
                batches += 1
        line = f"epoch {epoch}: loss {totals['loss'] / max(batches, 1):.3f}, "
        line += f"accuracy {totals['accuracy'] / max(batches, 1):.1%}"
        if held:
            line += f"; held out: accuracy {_accuracy(policy, held, batch, torch):.1%}"
        print(line, flush=True)
        model.save(policy, folder / "model.pt", epoch=epoch, data=str(data))
    return folder / "model.pt"


def _chunks(files: list[Path], at_once: int, rng: random.Random):
    # The files' decisions, encoded, a few games at a time - shuffled.
    from ml import batch

    for start in range(0, len(files), at_once):
        steps = [
            (batch.encode(d["obs"]), d["action"], d["return"])
            for path in files[start : start + at_once]
            for d in _read(path)
        ]
        rng.shuffle(steps)
        yield steps


def _accuracy(policy, files: list[Path], batch, torch) -> float:
    # How often the policy's best action is the teacher's, on these games.
    policy.eval()
    right = total = 0
    with torch.no_grad():
        for path in files:
            decisions = _read(path)
            for start in range(0, len(decisions), 256):
                part = decisions[start : start + 256]
                logits, _ = policy(batch.collate([batch.encode(d["obs"]) for d in part]))
                actions = torch.tensor([d["action"] for d in part])
                right += int((logits.argmax(-1) == actions).sum())
                total += len(part)
    return right / max(total, 1)


def _read(path: Path) -> list[dict]:
    with gzip.open(path, "rt") as lines:
        return [json.loads(line) for line in lines]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Learn from a teacher's games.")
    commands = parser.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("record", help="record a teacher's games")
    rec.add_argument("saves", nargs="+")
    rec.add_argument("--teacher", default="app.engine.env:random_policy")
    rec.add_argument("--games", type=int, default=20)
    rec.add_argument("--data", default=str(DATA / "games"))
    rec.add_argument("--seed", type=int, default=0)
    rec.add_argument("--max-steps", type=int, default=5000)
    rec.add_argument("--processes", type=int, default=1)
    tr = commands.add_parser("train", help="train the model on recorded games")
    tr.add_argument("data")
    tr.add_argument("--run", default="imitated")
    tr.add_argument("--epochs", type=int, default=5)
    tr.add_argument("--lr", type=float, default=3e-4)
    tr.add_argument("--minibatch", type=int, default=128)
    tr.add_argument("--hidden", type=int, default=128)
    tr.add_argument("--init")
    tr.add_argument("--threads", type=int, default=4)
    tr.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    if args.command == "record":
        paths = record(
            args.saves, args.teacher, args.games, Path(args.data), seed=args.seed,
            max_steps=args.max_steps, processes=args.processes,
        )
        print(f"recorded {len(paths)} games in {args.data}")
    else:
        path = train(
            Path(args.data), args.run, epochs=args.epochs, lr=args.lr,
            minibatch=args.minibatch, hidden=args.hidden, init=args.init,
            seed=args.seed, threads=args.threads,
        )
        print(f"saved {path}")


if __name__ == "__main__":
    main()
