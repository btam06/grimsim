from __future__ import annotations

import argparse
import re
import subprocess
import time
from pathlib import Path

# Plays each kept checkpoint of a PPO run (model-<update>.pt) against an
# opponent as it appears, and for each:
#
# - writes ml/data/diagnose-<run>-<update>.jsonl (ml.diagnose's rows), which
#   the app's ML page shows;
# - appends "checkpoint <update> vs scripted: <summary>" to --log;
# - writes eval/scripted_* scalars to <run>/eval-scripted (TensorBoard).
#
# The games are played once: the diagnose rows also make the summary (the
# same seed plays the same games as app.engine.evaluate). Checkpoints
# already in --log are skipped. It stops once every checkpoint is done and
# the run's ml.ppo process is gone.
#
#     env PYTHONPATH=backend:. ml/.venv/bin/python -m ml.watch ml/runs/ppo-scripted-6 \
#         $(cat ml/data/spread.txt) --games 100 --seed 20000 --processes 2


def checkpoints(run: Path) -> list[tuple[int, Path]]:
    found = []
    for path in run.glob("model-*.pt"):
        if m := re.fullmatch(r"model-(\d+)\.pt", path.name):
            found.append((int(m.group(1)), path))
    return sorted(found)


def logged(log: Path) -> set[int]:
    if not log.exists():
        return set()
    return {int(m.group(1)) for line in open(log) if (m := re.match(r"checkpoint (\d+) vs", line))}


def ppo_running(run: Path) -> bool:
    # ("[.]" so pgrep doesn't find a shell whose command line names this.)
    found = subprocess.run(["pgrep", "-f", f"ml[.]ppo .*--run {run.name}"], capture_output=True)
    return found.returncode == 0


def main(argv: list[str] | None = None) -> None:
    from ml.diagnose import play, result

    parser = argparse.ArgumentParser(description="Evaluate a PPO run's checkpoints as they're kept.")
    parser.add_argument("run", help="the run's folder, e.g. ml/runs/ppo-scripted-6")
    parser.add_argument("saves", nargs="+", help="saves to start games from")
    parser.add_argument("--opponent", default="app.engine.scripted:scripted")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20000)
    parser.add_argument("--processes", type=int, default=2)
    parser.add_argument("--log", help="default: ml/data/<run>-eval.log")
    parser.add_argument("--data", default="ml/data", help="where the diagnose files go")
    args = parser.parse_args(argv)
    run = Path(args.run)
    log = Path(args.log or f"{args.data}/{run.name}-eval.log")
    done = logged(log)
    writer = None

    while True:
        todo = [(u, p) for u, p in checkpoints(run) if u not in done]
        if not todo:
            if not ppo_running(run):
                break
            time.sleep(60)
            continue
        update, path = todo[0]
        out = Path(args.data) / f"diagnose-{run.name}-{update}.jsonl"
        rows = play(str(path), args.opponent, args.saves, args.games, args.seed,
                    processes=args.processes, out=out)
        summary = result(rows)
        line = f"checkpoint {update} vs scripted: {summary.summary()}"
        with open(log, "a") as file:
            file.write(line + "\n")
        print(line, flush=True)
        done.add(update)
        if writer is None:
            from torch.utils.tensorboard import SummaryWriter

            writer = SummaryWriter(str(run / "eval-scripted"))
        writer.add_scalar("eval/scripted_win_rate", summary.win_rate, update)
        writer.add_scalar("eval/scripted_vp_difference", summary.vp_difference, update)
        writer.flush()
    if writer is not None:
        writer.close()


if __name__ == "__main__":
    main()
