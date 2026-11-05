"""Each army list's win rate, from a training run's games.

ml.ppo writes each finished game to ml/runs/<run>/games.jsonl - its save,
VP and the learner's seat. Each save's players say which lists played, so:

    python3 scripts/list_win_rates.py ml/runs/ppo-scripted/games.jsonl

Against an opponent (e.g. the scripted player), it's the learner's win rate
with each list (and against each list); in self-play, each list's. List
names come from the app's API if it's running (ids otherwise). Only the
standard library's used, so any Python 3 will do.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("games", nargs="+", help="games.jsonl files")
    parser.add_argument("--since", type=int, default=0, help="only games from this update on")
    parser.add_argument("--api", default="http://localhost:8080/api")
    args = parser.parse_args()

    try:
        with urllib.request.urlopen(args.api + "/lists", timeout=5) as response:
            names = {l["id"]: l["name"] for l in json.load(response)}
    except OSError:
        names = {}

    def name(list_id: int) -> str:
        return names.get(list_id, f"list {list_id}")

    lists_of: dict[str, dict[int, int]] = {}
    # (won, drawn, lost) by list, and by list against list.
    tally = collections.defaultdict(lambda: [0, 0, 0])
    pairs = collections.defaultdict(lambda: [0, 0, 0])
    unfinished = 0
    for path in args.games:
        for line in open(path):
            game = json.loads(line)
            if game["update"] < args.since:
                continue
            if game["end"] != "terminated":
                unfinished += 1
                continue
            save = game["save"]
            if save not in lists_of:
                players = json.load(open(ROOT / save))["game"]["players"]
                lists_of[save] = {p["seat"]: p["list_id"] for p in players}
            lists = lists_of[save]
            vp = {int(seat): v for seat, v in game["vp"].items()}
            seats = [game["learner"]] if game["learner"] else [1, 2]
            for seat in seats:
                lead = vp[seat] - vp[3 - seat]
                outcome = 0 if lead > 0 else 1 if lead == 0 else 2
                tally[lists[seat]][outcome] += 1
                pairs[(lists[seat], lists[3 - seat])][outcome] += 1

    if not tally:
        sys.exit("no finished games")

    def rate(counts) -> float:
        won, drawn, lost = counts
        return (won + drawn / 2) / (won + drawn + lost)

    width = max(len(name(i)) for i in tally) + 2
    print(f"{'list':{width}} won drawn lost  win%")
    for list_id, counts in sorted(tally.items(), key=lambda kv: -rate(kv[1])):
        won, drawn, lost = counts
        print(f"{name(list_id):{width}} {won:3} {drawn:5} {lost:4}  {rate(counts):4.0%}")
    if unfinished:
        print(f"({unfinished} unfinished, not counted)")

    ids = sorted({i for pair in pairs for i in pair})
    print("\nthe row list's win% against the column list (games):")
    print(" " * width + "".join(f"{name(i)[:10]:>12}" for i in ids))
    for a in ids:
        cells = []
        for b in ids:
            counts = pairs.get((a, b))
            cells.append(f"{rate(counts):.0%} ({sum(counts)})" if counts else "-")
        print(f"{name(a):{width}}" + "".join(f"{c:>12}" for c in cells))


if __name__ == "__main__":
    main()
