import random

from httpx import AsyncClient

from app.engine import saves, store
from app.engine.play import Engine
from app.routers.agent import _key
from tests.test_movement import _battle

# Playing from Python (see app/engine/play.py): no HTTP, no database - and
# from a save, the same actions give the same game.


async def _play(engine: Engine, steps: int, seed: int) -> list[dict]:
    # Legal actions picked at random (from `seed`), as the agent's
    # random_action does; the log entries.
    pick_from = random.Random(seed)
    log = []
    for _ in range(steps):
        decision = await engine.decision()
        if decision["state"].startswith("finished"):
            break
        who = decision["waiting_for"]["seat"]
        choices = [a for a in decision["actions"] if a["seat"] == who and a["concrete"]]
        if not choices:
            break
        others = [a for a in choices if a["type"] != "advance"]
        pick = pick_from.choice(others if others and pick_from.random() > 0.2 else choices)
        params = dict(pick["params"])
        if pick["placement"]:
            params["positions"] = pick["placement"]["default"]
        keys = {_key(a["type"], a["seat"], a["params"]) for a in decision["actions"]}
        log.append(await engine.apply(pick["type"], who, params, keys))
    return log


async def _armed_battle(client, session, tmp_path):
    armed = {"weapon_range": 24, "melee": True}
    units = {1: [("A", 5, armed)], 2: [("D", 5, armed)]}
    game, _ = await _battle(client, session, tmp_path, units=units)
    return game["id"]


async def test_a_game_is_played_without_the_database(client: AsyncClient, session, tmp_path):
    game_id = await _armed_battle(client, session, tmp_path)
    engine = Engine.of(game_id)
    log = await _play(engine, 40, seed=1)
    assert len(log) > 10
    assert [e for e in log if e["mismatch"]] == []
    assert any(e["ok"] for e in log)


async def test_a_save_replays_the_same(client: AsyncClient, session, tmp_path):
    game_id = await _armed_battle(client, session, tmp_path)
    path = saves.folder(game_id) / "r1-s2-movement.json"
    store.clear()
    # Twice from the same save, the same choices: the same game - dice
    # included (they're the game's own - see app/services/dice.py).
    first = Engine.load(path)
    await _play(first, 25, seed=7)
    after_first = first.game.to_dict()
    second = Engine.load(path)
    await _play(second, 25, seed=7)
    assert second.game.to_dict() == after_first
    assert second.game.rng_rolls > 0


async def test_snapshot_and_restore(client: AsyncClient, session, tmp_path):
    game_id = await _armed_battle(client, session, tmp_path)
    engine = Engine.of(game_id)
    before = engine.snapshot()
    await _play(engine, 10, seed=3)
    assert engine.game.to_dict() != before.to_dict()
    engine.restore(before)
    assert engine.game.to_dict() == before.to_dict()
    # Restoring again still works: the snapshot itself wasn't played on.
    await _play(engine, 5, seed=4)
    engine.restore(before)
    assert engine.game.to_dict() == before.to_dict()
