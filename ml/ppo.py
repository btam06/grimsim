from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path

# Training a policy (see ml/model.py) with PPO, on games played in parallel
# (see backend/app/engine/vec.py) - against itself, or an opponent:
#
#     ml/.venv/bin/python -m ml.ppo saves/1/r1-s2-start_of_round.json --run first
#
# Each env's decisions are kept apart by player: a decision's reward is
# everything that happens to that player until their next decision (or the
# game ends) - the other player's turns included. Envs aren't stepped in
# lockstep: whichever are ready are decided for together (one batch through
# the model), so slow decisions don't hold the others up.
#
# Checkpoints and logs go to ml/runs/<run>/ (model.pt, and TensorBoard's -
# `tensorboard --logdir ml/runs`).
#
# (Imports of torch and the model are inside functions: the env processes
# import this module afresh, and don't need them.)

RUNS = Path(__file__).parent / "runs"


@dataclass
class Step:
    # One decision: what was seen (encoded), the action taken, its log
    # probability and the value then - and, once the player's next decision
    # (or the game's end) comes, its reward.
    obs: dict
    action: int
    logp: float
    value: float
    reward: float = 0.0
    done: bool = False


@dataclass
class Sequences:
    # Each player's decisions in each env, in order: finished ones (reward
    # known) to learn from, and the one still open.
    finished: dict[tuple[int, int], list[Step]] = field(default_factory=dict)
    open: dict[tuple[int, int], Step] = field(default_factory=dict)
    # What each player's had since their open decision.
    rewards: dict[tuple[int, int], float] = field(default_factory=dict)

    def reward(self, env: int, rewards: dict) -> None:
        for seat, reward in rewards.items():
            key = (env, int(seat))
            self.rewards[key] = self.rewards.get(key, 0.0) + reward

    def close(self, key: tuple[int, int], done: bool) -> None:
        step = self.open.pop(key, None)
        if step is not None:
            step.reward = self.rewards.get(key, 0.0)
            step.done = done
            self.finished.setdefault(key, []).append(step)
        self.rewards[key] = 0.0

    def decide(self, key: tuple[int, int], step: Step) -> None:
        self.close(key, done=False)
        self.open[key] = step

    def end(self, env: int) -> None:
        # The env's game is over: every player's open decision closes.
        for key in [k for k in list(self.open) + list(self.rewards) if k[0] == env]:
            self.close(key, done=True)

    def count(self) -> int:
        return sum(len(steps) for steps in self.finished.values())


def advantages(
    rewards: list[float],
    values: list[float],
    dones: list[bool],
    bootstrap: float,
    gamma: float,
    lam: float,
) -> list[float]:
    # Generalised advantage estimates for one player's decisions in order;
    # `bootstrap`: the value of the decision after the last (if it isn't
    # done).
    found = [0.0] * len(rewards)
    running = 0.0
    following = bootstrap
    for i in reversed(range(len(rewards))):
        alive = 0.0 if dones[i] else 1.0
        delta = rewards[i] + gamma * following * alive - values[i]
        running = delta + gamma * lam * alive * running
        found[i] = running
        following = values[i]
    return found


def main(argv: list[str] | None = None) -> None:
    args = _arguments(argv)
    train(args)


def _arguments(argv):
    parser = argparse.ArgumentParser(description="Train a policy with PPO.")
    parser.add_argument("saves", nargs="+", help="saves to start games from")
    parser.add_argument("--run", default="ppo", help="its folder under ml/runs")
    parser.add_argument("--envs", type=int, default=4, help="games played at once")
    parser.add_argument(
        "--opponent", default="self",
        help='"self" (self-play) or module:function (e.g. app.engine.env:random_policy)',
    )
    parser.add_argument("--updates", type=int, default=100)
    parser.add_argument("--rollout", type=int, default=512, help="decisions per update")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--minibatch", type=int, default=128)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--gamma", type=float, default=0.995)
    parser.add_argument("--lam", type=float, default=0.95)
    parser.add_argument("--clip", type=float, default=0.2)
    parser.add_argument("--entropy", type=float, default=0.01)
    parser.add_argument("--value-weight", type=float, default=0.5)
    parser.add_argument("--hidden", type=int, default=128)
    parser.add_argument("--init", help="a checkpoint to start from (e.g. from ml.imitate)")
    parser.add_argument("--max-steps", type=int, default=5000)
    parser.add_argument("--threads", type=int, default=2, help="torch's (the envs have theirs)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--eval-every", type=int, default=0,
        help="updates between evaluations against random play (0: none)",
    )
    parser.add_argument("--eval-games", type=int, default=4)
    return parser.parse_args(argv)


def train(args) -> Path:
    import torch

    from app.engine.evaluate import _load, evaluate
    from app.engine.vec import VecEnv
    from ml import batch, model
    from ml.policy import ModelPolicy

    torch.manual_seed(args.seed)
    torch.set_num_threads(args.threads)
    folder = RUNS / args.run
    folder.mkdir(parents=True, exist_ok=True)
    writer = _writer(folder)
    policy = model.load(args.init) if args.init else model.Policy(hidden=args.hidden)
    optimiser = torch.optim.Adam(policy.parameters(), lr=args.lr)
    if args.opponent == "self":
        envs = VecEnv(args.envs, saves=args.saves, seed=args.seed, max_steps=args.max_steps)
    else:
        envs = VecEnv(
            args.envs, saves=args.saves, seat="random", opponent=_load(args.opponent),
            seed=args.seed, max_steps=args.max_steps,
        )
    sequences = Sequences()
    episodes: list[dict] = []
    # The seat each env last decided for (against an opponent: the policy's).
    seats: dict[int, int] = {}
    obs, infos = envs.reset()
    ready = {i: (obs[i], infos[i]) for i in range(len(envs))}
    started = time.time()
    try:
        for update in range(1, args.updates + 1):
            decided = 0
            while sequences.count() < args.rollout:
                decided += _decide(policy, batch, ready, envs, sequences, seats)
                for i, (o, _, terminated, truncated, info) in envs.poll():
                    if terminated or truncated:
                        final = info["final_info"]
                        sequences.reward(i, final["rewards"])
                        sequences.end(i)
                        episodes.append(final | {
                            "end": "terminated" if terminated else "truncated",
                            "learner": seats.get(i),
                        })
                    sequences.reward(i, info["rewards"])
                    ready[i] = (o, info)
            stats = _learn(policy, optimiser, sequences, args, batch, torch)
            elapsed = time.time() - started
            stats |= _episode_stats(episodes, against=args.opponent != "self")
            episodes.clear()
            model.save(policy, folder / "model.pt", update=update, args=vars(args))
            line = ", ".join(f"{k} {v:.3g}" for k, v in stats.items())
            print(f"update {update}: {decided} decisions, {elapsed:.0f}s - {line}", flush=True)
            for name, value in stats.items():
                writer and writer.add_scalar(name, value, update)
            if args.eval_every and update % args.eval_every == 0:
                result = evaluate(
                    ModelPolicy(str(folder / "model.pt")), args.saves,
                    games=args.eval_games, seed=10_000 + update, max_steps=args.max_steps,
                )
                print(f"  against random play: {result.summary()}", flush=True)
                writer and writer.add_scalar("eval/win_rate", result.win_rate, update)
                writer and writer.add_scalar("eval/vp_difference", result.vp_difference, update)
    finally:
        envs.close()
        writer and writer.close()
    return folder / "model.pt"


def _decide(policy, batch, ready, envs, sequences, seats) -> int:
    # The envs ready for a decision: decided for together, and sent on.
    import torch

    if not ready:
        return 0
    order = list(ready)
    encoded = [batch.encode(ready[i][0]) for i in order]
    with torch.no_grad():
        logits, values = policy(batch.collate(encoded))
    for row, i in enumerate(order):
        obs, info = ready.pop(i)
        seats[i] = info["seat"]
        count = len(info["actions"])
        distribution = torch.distributions.Categorical(logits=logits[row, :count])
        action = int(distribution.sample())
        sequences.decide(
            (i, info["seat"]),
            Step(encoded[row], action, float(distribution.log_prob(torch.tensor(action))),
                 float(values[row])),
        )
        envs.send(i, action)
    return len(order)


def _learn(policy, optimiser, sequences, args, batch, torch) -> dict:
    # One PPO update on the finished decisions (then let go of them).
    steps, returns, advantage = [], [], []
    for key, finished in sequences.finished.items():
        following = sequences.open.get(key)
        bootstrap = following.value if following is not None and not finished[-1].done else 0.0
        found = advantages(
            [s.reward for s in finished], [s.value for s in finished],
            [s.done for s in finished], bootstrap, args.gamma, args.lam,
        )
        steps += finished
        advantage += found
        returns += [a + s.value for a, s in zip(found, finished)]
    sequences.finished.clear()
    advantage_t = torch.tensor(advantage)
    advantage_t = (advantage_t - advantage_t.mean()) / (advantage_t.std() + 1e-8)
    returns_t = torch.tensor(returns)
    actions_t = torch.tensor([s.action for s in steps])
    old_logp = torch.tensor([s.logp for s in steps])
    totals = {"loss/policy": 0.0, "loss/value": 0.0, "entropy": 0.0, "clipped": 0.0}
    batches = 0
    for _ in range(args.epochs):
        order = torch.randperm(len(steps))
        for start in range(0, len(steps), args.minibatch):
            index = order[start : start + args.minibatch]
            logits, values = policy(batch.collate([steps[i].obs for i in index]))
            distribution = torch.distributions.Categorical(logits=logits)
            logp = distribution.log_prob(actions_t[index])
            ratio = torch.exp(logp - old_logp[index])
            adv = advantage_t[index]
            policy_loss = -torch.min(
                ratio * adv, ratio.clamp(1 - args.clip, 1 + args.clip) * adv
            ).mean()
            value_loss = (values - returns_t[index]).pow(2).mean()
            entropy = distribution.entropy().mean()
            loss = policy_loss + args.value_weight * value_loss - args.entropy * entropy
            optimiser.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
            optimiser.step()
            totals["loss/policy"] += policy_loss.item()
            totals["loss/value"] += value_loss.item()
            totals["entropy"] += entropy.item()
            totals["clipped"] += float(((ratio - 1).abs() > args.clip).float().mean())
            batches += 1
    return {name: total / max(batches, 1) for name, total in totals.items()} | {
        "decisions": float(len(steps)),
        "return": float(returns_t.mean()) if len(steps) else 0.0,
    }


def _episode_stats(episodes: list[dict], against: bool) -> dict:
    # The games that ended since the last update: how many, how long, and -
    # against an opponent - how the policy did.
    if not episodes:
        return {"games": 0.0}
    stats = {
        "games": float(len(episodes)),
        "game_steps": sum(e["steps"] for e in episodes) / len(episodes),
        "unfinished": sum(e["end"] != "terminated" for e in episodes) / len(episodes),
    }
    scored = [e for e in episodes if e["learner"] is not None]
    if against and scored:
        leads = [e["vp"][e["learner"]] - e["vp"][3 - e["learner"]] for e in scored]
        stats["vp_difference"] = sum(leads) / len(leads)
        stats["win_rate"] = sum((lead > 0) + 0.5 * (lead == 0) for lead in leads) / len(leads)
    return stats


def _writer(folder: Path):
    try:
        from torch.utils.tensorboard import SummaryWriter
    except ImportError:
        return None
    return SummaryWriter(str(folder))


if __name__ == "__main__":
    main()
