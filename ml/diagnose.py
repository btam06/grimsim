from __future__ import annotations

import argparse
import collections
import json
import multiprocessing as mp
import random
from pathlib import Path

# How each army list plays, to see why some win more: games played (as
# app.engine.evaluate does - seats in turn, the saves in turn), and from each
# finished game's state, for each side: where its VP came from, damage and
# kills by shooting and in melee, charges declared and made, stratagems used,
# units that never did anything (or never left Reserves), the VP it left on
# the table (see app.engine.env.left_on_table), and the points of its units
# left in the battle and lost (army_left).
#
#     env PYTHONPATH=backend ml/.venv/bin/python -m ml.diagnose $(cat ml/data/spread.txt) \
#         --policy ml/runs/ppo-scripted-2/model.pt --opponent app.engine.scripted:scripted \
#         --games 60 --processes 3 --out ml/data/diagnose.jsonl
#
# A policy is module:function, or a checkpoint (.pt). Each game's numbers
# are written to `--out` as it's played (a line a side), then summed up by
# list - for the policy's side and the opponent's apart. `--report` sums up
# an earlier `--out` without playing.

STATS = (
    "vp", "primary", "secondary", "shot_damage", "melee_damage", "shot_kills", "melee_kills",
    "other_kills", "charges", "charges_made", "stratagems", "cp_spent", "units", "idle_units",
    "units_in_reserves", "units_lost",
)
# (And the VP left on the table, from app.engine.env.left_on_table.)
LEFT = (
    "left", "primary_left", "secondary_left", "primary_capped", "secondary_capped",
    "discarded", "achieved", "held_unclaimed",
)
# (And the points of its units left in the battle, and lost - from
# app.engine.env.army_left.)
ARMY = ("points_left", "points_lost")


def _policy(spec: str):
    if spec.endswith(".pt"):
        from ml.policy import ModelPolicy

        return ModelPolicy(spec)
    from app.engine.evaluate import _load

    return _load(spec)


def _play(job) -> list[dict]:
    from app.engine.env import GameEnv

    policy_spec, opponent_spec, saves, game_seed, max_steps = job
    policy, opponent = _policy(policy_spec), _policy(opponent_spec)
    seat = 1 if game_seed % 2 == 0 else 2
    save = saves[(game_seed // 2) % len(saves)]
    env = GameEnv(save, seat=seat, opponent=opponent, max_steps=max_steps, seed=game_seed)
    rng = random.Random(game_seed)
    try:
        _, info = env.reset()
        while info["done"] is None:
            _, _, _, _, info = env.step(policy(env.decision, rng))
        played = {"policy": policy_spec, "opponent": opponent_spec}
        if info["done"] != "terminated":
            return [{"seed": game_seed, "save": save, "end": info["done"], **played}]
        return [
            {"seed": game_seed, "save": save, "end": "terminated", "seat": s, **played,
             "side": "policy" if s == seat else "opponent", **stats}
            for s, stats in _sides(env.game).items()
        ]
    finally:
        env.close()


def _sides(game) -> dict[int, dict]:
    from app.engine.env import army_left, left_on_table
    from app.services.in_game import reinforcements

    seat_of = {u.id: p.seat for p in game.players for u in p.army_list.units}
    left, army = left_on_table(game), army_left(game)
    sides = {
        p.seat: dict.fromkeys(STATS, 0) | left[p.seat] | army[p.seat]
        | {"list_id": p.army_list.id, "stratagem_uses": []}
        for p in game.players
    }
    for p in game.players:
        side = sides[p.seat]
        for score in p.scores:
            side["vp"] += score.points
            if score.kind in ("primary", "secondary"):
                side[score.kind] += score.points
        side["stratagems"] = len(p.stratagem_uses)
        for use in p.stratagem_uses:
            side["cp_spent"] += use.cp or 0
            side["stratagem_uses"].append({
                "name": use.stratagem.name if use.stratagem else str(use.stratagem_id),
                "phase": use.phase, "round": use.battle_round, "cp": use.cp,
                "own_turn": use.turn_seat == p.seat,
            })
        side["units"] = len(p.army_list.units)
        side["units_in_reserves"] = len(reinforcements.reserve_units(game, p.seat))

    acted = set()
    for shot in game.unit_shots:
        acted.add(shot.unit_id)
        if shot.unit_id in seat_of:
            sides[seat_of[shot.unit_id]]["shot_damage"] += shot.total_damage or 0
    for fight in game.unit_fights:
        acted.add(fight.unit_id)
        if fight.unit_id in seat_of:
            sides[seat_of[fight.unit_id]]["melee_damage"] += fight.total_damage or 0
    for charge in game.unit_charges:
        acted.add(charge.unit_id)
        # (Rolling is declaring: a failed charge has no target_unit_id, as
        # that's only set once the charge is made.)
        if charge.unit_id in seat_of:
            side = sides[seat_of[charge.unit_id]]
            side["charges"] += 1
            side["charges_made"] += charge.completed
    for move in game.unit_moves:
        acted.add(move.unit_id)
    for death in game.models_destroyed:
        if death.unit_destroyed and death.unit_id in seat_of:
            sides[seat_of[death.unit_id]]["units_lost"] += 1
        killer = seat_of.get(death.destroyed_by_unit_id)
        if killer is None:
            continue
        kind = {"shooting": "shot_kills", "fight": "melee_kills"}.get(death.phase, "other_kills")
        sides[killer][kind] += 1
    for unit_id, seat in seat_of.items():
        sides[seat]["idle_units"] += unit_id not in acted
    return sides


def report(rows: list[dict], names: dict[int, str]) -> str:
    unfinished = sum(r["end"] != "terminated" for r in rows)
    rows = [r for r in rows if r["end"] == "terminated"]
    by_game = collections.defaultdict(dict)
    for r in rows:
        by_game[(r["seed"], r["save"])][r["seat"]] = r
    groups = collections.defaultdict(list)
    for sides in by_game.values():
        for seat, r in sides.items():
            other = sides.get(3 - seat)
            if other is None:
                continue
            # (Earlier --out files have no VP-left numbers: the totals from
            # the VP scored, the rest 0.)
            if "left" not in r:
                r = dict.fromkeys(LEFT, 0) | r | {
                    "primary_left": 45 - min(r["primary"], 45),
                    "secondary_left": 45 - min(r["secondary"], 45),
                }
                r["left"] = r["primary_left"] + r["secondary_left"]
            r = dict.fromkeys(ARMY, 0) | {"cp_spent": 0} | r
            groups[(r["side"], r["list_id"])].append(
                r | {"won": (r["vp"] > other["vp"]) + 0.5 * (r["vp"] == other["vp"]),
                     "vp_against": other["vp"],
                     "capped": r["primary_capped"] + r["secondary_capped"]}
            )
    columns = (
        ("games", None), ("win%", "won"), ("vp", "vp"), ("vs", "vp_against"),
        ("prim", "primary"), ("sec", "secondary"), ("shotdmg", "shot_damage"),
        ("meleedmg", "melee_damage"), ("shotkill", "shot_kills"), ("meleekill", "melee_kills"),
        ("charges", "charges"), ("made", "charges_made"), ("strats", "stratagems"), ("cp", "cp_spent"),
        ("idle", "idle_units"), ("inres", "units_in_reserves"), ("lost", "units_lost"),
        ("units", "units"), ("left", "left"), ("primleft", "primary_left"),
        ("secleft", "secondary_left"), ("capped", "capped"), ("discard", "discarded"),
        ("claimed", "achieved"), ("heldvp", "held_unclaimed"), ("ptsleft", "points_left"),
        ("ptslost", "points_lost"),
    )
    width = max([len(names.get(k[1], str(k[1]))) for k in groups] + [4]) + 2
    lines = ["(averages a game; win% counts draws half)"]
    for side in ("policy", "opponent"):
        keys = sorted(k for k in groups if k[0] == side)
        if not keys:
            continue
        lines.append(f"\nas the {side}:")
        lines.append(f"{'list':{width}}" + "".join(f"{c:>10}" for c, _ in columns))
        for key in keys:
            games = groups[key]
            cells = []
            for title, stat in columns:
                if stat is None:
                    cells.append(f"{len(games):>10}")
                elif stat == "won":
                    cells.append(f"{sum(g['won'] for g in games) / len(games):>10.0%}")
                else:
                    cells.append(f"{sum(g[stat] for g in games) / len(games):>10.1f}")
            lines.append(f"{names.get(key[1], str(key[1])):{width}}" + "".join(cells))
    if unfinished:
        lines.append(f"\n({unfinished} unfinished games, not counted)")
    return "\n".join(lines)


def _names() -> dict[int, str]:
    # The lists' names, from the app's API if it's running.
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:8080/api/lists", timeout=5) as response:
            return {l["id"]: l["name"] for l in json.load(response)}
    except OSError:
        return {}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="How each army list plays.")
    parser.add_argument("saves", nargs="*", help="saves to start games from")
    parser.add_argument("--policy", default="app.engine.scripted:scripted")
    parser.add_argument("--opponent", default="app.engine.scripted:scripted")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=5000)
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument("--out", default="ml/data/diagnose.jsonl")
    parser.add_argument("--report", action="store_true", help="sum up --out, play nothing")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if not args.report:
        if not args.saves:
            parser.error("saves are needed to play")
        jobs = [
            (args.policy, args.opponent, args.saves, args.seed + i, args.max_steps)
            for i in range(args.games)
        ]
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as file:
            if args.processes > 1:
                with mp.get_context("spawn").Pool(args.processes) as pool:
                    results = pool.imap_unordered(_play, jobs)
                    for rows in results:
                        _write(file, rows)
            else:
                for job in jobs:
                    _write(file, _play(job))
    rows = [json.loads(line) for line in open(out)]
    print(report(rows, _names()))


def _write(file, rows: list[dict]) -> None:
    for row in rows:
        file.write(json.dumps(row) + "\n")
    file.flush()
    print(f"game {rows[0]['seed']}: {rows[0]['save']} {rows[0]['end']}", flush=True)


if __name__ == "__main__":
    main()
