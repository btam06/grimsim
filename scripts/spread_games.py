"""Make a spread of games from the army lists, to train from.

Every pairing of two lists, each way round (attacker and defender), a few
games each - each with its own dice seed, and its own terrain layout picked
at random. Each game's `saves/<game>/setup.json` is saved as it's made, before
anything's deployed (see backend/app/engine/saves.py). Their paths are
printed one a line (the progress goes to stderr), ready for ml.ppo,
ml.imitate or evaluate:

    python3 scripts/spread_games.py --games 3 > ml/data/spread.txt
    ml/.venv/bin/python -m ml.imitate record $(cat ml/data/spread.txt) \\
        --teacher app.engine.scripted:scripted --games 200 --processes 4

Games are made through the app's API (it has to be running: docker compose
up -d), each player being the list's owner. Pairings of dispositions with no
terrain layout are skipped, and said so. Only the standard library's used,
so any Python 3 will do.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Refused(Exception):
    pass


def call(api: str, method: str, path: str, body=None):
    request = urllib.request.Request(
        api + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        try:
            detail = json.loads(detail).get("detail", detail)
        except (ValueError, AttributeError):
            pass
        raise Refused(f"{e.code}: {detail}") from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--games", type=int, default=2, help="games per pairing, each way round")
    parser.add_argument("--lists", type=int, nargs="+", help="only these lists (ids)")
    parser.add_argument(
        "--secondaries", choices=("tactical", "fixed"), default="tactical",
        help="both players' secondary mode",
    )
    parser.add_argument("--seed", type=int, help="the first game's dice seed (the rest count up)")
    parser.add_argument("--api", default="http://localhost:8080/api")
    parser.add_argument("--dry-run", action="store_true", help="list the pairings, make nothing")
    args = parser.parse_args()

    def log(*parts) -> None:
        print(*parts, file=sys.stderr)

    try:
        lists = call(args.api, "GET", "/lists")
    except (Refused, urllib.error.URLError) as e:
        sys.exit(f"can't get the lists from {args.api} ({e}) - is the app running?")
    if args.lists:
        lists = [l for l in lists if l["id"] in args.lists]
        if missing := set(args.lists) - {l["id"] for l in lists}:
            sys.exit(f"no such lists: {sorted(missing)}")
    if len(lists) < 2:
        sys.exit("two lists or more are needed")

    layouts = call(args.api, "GET", "/terrain-layouts")
    covered = {
        frozenset((l["attacker_disposition_id"], l["defender_disposition_id"])) for l in layouts
    }
    names = {d["id"]: d["name"] for d in call(args.api, "GET", "/dispositions")}

    seeds = itertools.count(args.seed if args.seed is not None else random.randrange(2**32))
    made, skipped = [], []
    for attacker, defender in itertools.permutations(lists, 2):
        pairing = f"{attacker['name']} (attacking) vs {defender['name']}"
        dispositions = (attacker["disposition_id"], defender["disposition_id"])
        # (A layout fits its dispositions either way round.)
        if layouts and frozenset(dispositions) not in covered:
            skipped.append(
                f"{pairing}: no terrain layout for "
                + " vs ".join(names.get(d, str(d)) for d in dispositions)
            )
            continue
        if args.dry_run:
            log(pairing)
            continue
        for _ in range(args.games):
            seed = next(seeds)
            try:
                game = call(args.api, "POST", "/games", {
                    "players": [
                        {"user_id": l["user_id"], "list_id": l["id"],
                         "secondary_mode": args.secondaries}
                        for l in (attacker, defender)
                    ],
                    "attacker_seat": 1,
                    "seed": seed,
                })
            except Refused as e:
                # (Whatever it is, it'll be the same for every game.)
                skipped.append(f"{pairing}: {e}")
                break
            setup = Path("saves") / str(game["id"]) / "setup.json"
            if not (ROOT / setup).exists():
                sys.exit(f"game {game['id']} was made, but {setup} wasn't saved")
            log(f"game {game['id']}: {pairing}, {game.get('terrain_layout_name')}, seed {seed}")
            made.append(setup)
            print(setup, flush=True)

    for reason in skipped:
        log("skipped", reason)
    if not args.dry_run:
        log(f"{len(made)} games made")


if __name__ == "__main__":
    main()
