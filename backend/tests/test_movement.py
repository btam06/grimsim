from httpx import AsyncClient
from sqlalchemy import select

from app.models import GameModelPosition
from tests.test_deployment import R32, _deploy, _deployment, _game, _row, _unit_named

# Games on the test layout (see tests/test_deployment.py): the attacker (seat
# 1) deploys along y 32-44, the defender (seat 2) along y 0-12, and the
# defender goes first. Every model has M 6" and a 32mm base.


async def _battle(client, session, tmp_path, units=None, spots=None):
    # A game with everything deployed (each unit at its spot: {name: (x, y)},
    # in _row's formation), in the first player's (seat 2's) movement phase.
    units = units or {1: [("A", 5, {})], 2: [("D", 5, {})]}
    spots = spots or {"A": (20, 38), "D": (20, 4)}
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    while game["status"] == "deployment":
        seat = game["deploying_seat"]
        current = await _deployment(client, game_id)
        deployed = {u["unit_id"] for u in current["units"] if u["deployed"]}
        unit = next(
            u for u in deployment["units"] if u["seat"] == seat and u["unit_id"] not in deployed
        )
        response = await _deploy(client, game_id, unit, _row(unit, *spots[unit["name"]]))
        assert response.status_code == 200, response.text
        game = response.json()
    assert (game["phase"], game["turn_seat"]) == ("command", 2)
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "movement"
    return game, await _deployment(client, game_id)


async def _movement(client, game_id):
    return (await client.get(f"/games/{game_id}/movement")).json()


def _shifted(unit, dx=0.0, dy=0.0, only=None):
    # Each model's current position, moved by (dx, dy) - or just the models
    # at the indexes in `only`.
    return [
        {
            "unit_model_id": m["unit_model_id"],
            "x": m["position"]["x"] + (dx if only is None or i in only else 0),
            "y": m["position"]["y"] + (dy if only is None or i in only else 0),
        }
        for i, m in enumerate(unit["models"])
    ]


async def _check(client, game_id, unit, kind, positions):
    response = await client.post(
        f"/games/{game_id}/movement/check",
        json={"unit_id": unit["unit_id"], "kind": kind, "positions": positions},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _move(client, game_id, unit, kind, positions):
    return await client.post(
        f"/games/{game_id}/movement",
        json={"unit_id": unit["unit_id"], "kind": kind, "positions": positions},
    )


async def test_movement_lists_the_turn_players_units(client: AsyncClient, session, tmp_path):
    game, _ = await _battle(client, session, tmp_path)
    [unit] = (await _movement(client, game["id"]))["units"]
    assert unit["name"] == "D"
    assert unit["allowed_kinds"] == ["normal", "advance"]
    assert (unit["moved"], unit["kind"], unit["in_engagement_range"]) == (False, None, False)
    assert {m["movement"] for m in unit["models"]} == {6}


async def test_no_movement_outside_the_movement_phase(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    game_id = game["id"]
    await client.post(f"/games/{game_id}/advance")  # to shooting
    assert (await _movement(client, game_id))["units"] == []
    d = _unit_named(deployment, "D")
    response = await _move(client, game_id, d, "normal", _shifted(d, dy=1))
    assert response.status_code == 400
    assert "movement phase" in response.json()["detail"]


async def test_only_the_turn_player_moves(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    a = _unit_named(deployment, "A")
    response = await _move(client, game["id"], a, "normal", _shifted(a, dy=-1))
    assert response.status_code == 400
    assert "whose turn" in response.json()["detail"]


async def test_normal_move(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    # Up to 6".
    assert (await _check(client, game_id, d, "normal", _shifted(d, dy=6)))["valid"]
    check = await _check(client, game_id, d, "normal", _shifted(d, dy=6.5))
    assert 'D would move 6.5" (it can move 6") (x5)' in check["problems"]
    response = await _move(client, game_id, d, "normal", _shifted(d, dy=6))
    assert response.status_code == 200, response.text

    moved = _unit_named(await _deployment(client, game_id), "D")
    assert [m["position"]["y"] for m in moved["models"]] == [
        m["position"]["y"] + 6 for m in d["models"]
    ]
    [unit] = (await _movement(client, game_id))["units"]
    assert (unit["moved"], unit["kind"], unit["allowed_kinds"]) == (True, "normal", [])
    # Once a phase.
    response = await _move(client, game_id, moved, "normal", _shifted(moved, dy=1))
    assert response.status_code == 400
    assert "already moved" in response.json()["detail"]


async def test_not_every_model_has_to_move(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    # One model steps 0.5" and the rest stay put.
    positions = _shifted(d, dx=0.5, only={4})
    assert (await _check(client, game_id, d, "normal", positions))["valid"]
    assert (await _move(client, game_id, d, "normal", positions)).status_code == 200
    moved = _unit_named(await _deployment(client, game_id), "D")
    assert moved["models"][0]["position"] == d["models"][0]["position"]
    assert moved["models"][4]["position"]["x"] == d["models"][4]["position"]["x"] + 0.5


async def test_moved_unit_must_stay_in_coherency(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    d = _unit_named(deployment, "D")
    # Its first model walks 5" away from the rest.
    check = await _check(client, game["id"], d, "normal", _shifted(d, dx=-5, only={0}))
    assert any('within 2" of another model' in p for p in check["problems"])


async def test_advance(client: AsyncClient, session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.in_game.movement.random.randint", lambda a, b: 3)
    game, deployment = await _battle(client, session, tmp_path)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    # It has to roll first.
    response = await _move(client, game_id, d, "advance", _shifted(d, dy=8))
    assert response.status_code == 400
    assert "roll for the Advance" in response.json()["detail"]

    url = f"/games/{game_id}/movement/advance"
    response = await client.post(url, json={"unit_id": d["unit_id"]})
    assert response.status_code == 200, response.text
    [unit] = response.json()["units"]
    assert (unit["kind"], unit["advance_roll"], unit["moved"]) == (None, 3, False)
    # It can still choose either.
    assert unit["allowed_kinds"] == ["normal", "advance"]

    # M 6" + 3.
    check = await _check(client, game_id, d, "advance", _shifted(d, dy=9.5))
    assert 'D would move 9.5" (it can move 9") (x5)' in check["problems"]
    assert (await _check(client, game_id, d, "advance", _shifted(d, dy=9)))["valid"]
    assert (await _move(client, game_id, d, "advance", _shifted(d, dy=9))).status_code == 200
    [unit] = (await _movement(client, game_id))["units"]
    assert (unit["kind"], unit["advance_roll"], unit["moved"]) == ("advance", 3, True)


async def test_advance_roll_stands(client: AsyncClient, session, tmp_path, monkeypatch):
    # Rolling again (e.g. unticking and ticking Advance) keeps the first roll.
    rolls = iter([2, 6])
    monkeypatch.setattr("app.services.in_game.movement.random.randint", lambda a, b: next(rolls))
    game, deployment = await _battle(client, session, tmp_path)
    d = _unit_named(deployment, "D")
    url = f"/games/{game['id']}/movement/advance"
    first = (await client.post(url, json={"unit_id": d["unit_id"]})).json()
    again = (await client.post(url, json={"unit_id": d["unit_id"]})).json()
    assert first["units"][0]["advance_roll"] == again["units"][0]["advance_roll"] == 2


async def test_rolled_unit_can_still_move_normally(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    await client.post(f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"]})
    # A Normal move: just M.
    check = await _check(client, game_id, d, "normal", _shifted(d, dy=6.5))
    assert 'D would move 6.5" (it can move 6") (x5)' in check["problems"]
    assert (await _move(client, game_id, d, "normal", _shifted(d, dy=6))).status_code == 200
    [unit] = (await _movement(client, game_id))["units"]
    assert (unit["kind"], unit["moved"]) == ("normal", True)


async def _engage(session, unit, x, y):
    # Puts the unit's first model at (x, y) directly (as if it had charged).
    position = (
        await session.execute(
            select(GameModelPosition).where(
                GameModelPosition.unit_model_id == unit["models"][0]["unit_model_id"]
            )
        )
    ).scalar_one()
    position.x, position.y = x, y
    await session.commit()


async def test_engaged_unit_can_only_fall_back(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment, "A"), _unit_named(deployment, "D")
    # The attacker's model 0.5" from the defender's.
    await _engage(session, a, d["models"][0]["position"]["x"] + 2 * R32 + 0.5, 4)
    [unit] = (await _movement(client, game_id))["units"]
    assert (unit["in_engagement_range"], unit["allowed_kinds"]) == (True, ["fall_back"])

    response = await _move(client, game_id, d, "normal", _shifted(d, dx=-3))
    assert "can only Fall Back" in response.json()["detail"]
    # It has to get out of Engagement Range.
    check = await _check(client, game_id, d, "fall_back", _shifted(d, dx=-0.3))
    assert check["problems"] == ["D would end within Engagement Range of an enemy model"]
    assert (await _move(client, game_id, d, "fall_back", _shifted(d, dx=-3))).status_code == 200
    [unit] = (await _movement(client, game_id))["units"]
    assert (unit["kind"], unit["moved"]) == ("fall_back", True)


async def test_unengaged_unit_cant_fall_back(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    d = _unit_named(deployment, "D")
    response = await _move(client, game["id"], d, "fall_back", _shifted(d, dy=1))
    assert response.status_code == 400
    assert "Engagement Range can Fall Back" in response.json()["detail"]


async def test_cant_move_into_engagement_range(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment, "A"), _unit_named(deployment, "D")
    # The attacker's model 5" from the defender's: Engagement Range is 2".
    await _engage(session, a, d["models"][0]["position"]["x"], 4 + 2 * R32 + 5)
    check = await _check(client, game_id, d, "normal", _shifted(d, dy=3.5))
    assert check["problems"] == ["D would end within Engagement Range of an enemy model"]
    assert (await _check(client, game_id, d, "normal", _shifted(d, dy=2.5)))["valid"]


async def test_cant_move_onto_terrain_or_other_models(client: AsyncClient, session, tmp_path):
    # The test layout's ruin wall runs x 7-11 along y 8-8.5.
    units = {1: [("A", 1, {})], 2: [("D", 1, {}), ("E", 1, {})]}
    spots = {"A": (20, 40), "D": (9, 4), "E": (14, 4)}
    game, deployment = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    check = await _check(client, game_id, d, "normal", _shifted(d, dy=4.25))
    assert check["problems"] == ["D overlaps a ruin wall"]
    check = await _check(client, game_id, d, "normal", _shifted(d, dx=4.5))
    assert check["problems"] == ["D overlaps E"]


async def test_move_needs_every_model(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    d = _unit_named(deployment, "D")
    response = await _move(client, game["id"], d, "normal", _shifted(d, dy=1)[:-1])
    assert response.status_code == 400
    assert "every model" in response.json()["detail"]
