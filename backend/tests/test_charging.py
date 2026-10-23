from httpx import AsyncClient

from tests.test_deployment import R32, _deployment, _unit_named
from tests.test_movement import _battle, _shifted
from tests.test_shooting import _place

# Games on the test layout, the defender (seat 2) charging first. Every
# charge die rolls a 4 (a roll of 8) unless a test says otherwise; models
# are on 32mm bases; Engagement Range is 2".

ROLL_URL = "/games/{}/charge/roll"


async def _charge_game(client, session, tmp_path, monkeypatch, d=1, a=1, die=4, gap=6.0):
    # D (at x 20, y 4, in a row) charging A, whose models stand `gap` inches
    # from D's first model, base to base, straight down the board.
    monkeypatch.setattr("app.services.in_game.charging.random.randint", lambda a_, b: die)
    units = {1: [("A", a, {})], 2: [("D", d, {})]}
    game, deployment = await _battle(client, session, tmp_path, units=units)
    a_unit = _unit_named(deployment, "A")
    y = 4 + 2 * R32 + gap
    await _place(session, a_unit, [(20 + i * 1.5, y) for i in range(a)])
    game_id = game["id"]
    for phase in ("shooting", "charge"):
        game = (await client.post(f"/games/{game_id}/advance")).json()
        assert game["phase"] == phase
    deployment = await _deployment(client, game_id)
    return game_id, _unit_named(deployment, "D"), _unit_named(deployment, "A")


async def _charge(client, game_id):
    return (await client.get(f"/games/{game_id}/charge")).json()


async def _roll(client, game_id, unit):
    response = await client.post(ROLL_URL.format(game_id), json={"unit_id": unit["unit_id"]})
    assert response.status_code == 200, response.text
    return response.json()


async def _targets(client, game_id, unit):
    return (
        await client.get(f"/games/{game_id}/charge/targets?unit_id={unit['unit_id']}")
    ).json()


def _payload(unit, target, positions):
    return {"unit_id": unit["unit_id"], "target_unit_id": target["unit_id"], "positions": positions}


async def _check(client, game_id, unit, target, positions):
    response = await client.post(
        f"/games/{game_id}/charge/check", json=_payload(unit, target, positions)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _make(client, game_id, unit, target, positions):
    return await client.post(f"/games/{game_id}/charge", json=_payload(unit, target, positions))


async def test_roll_the_charge(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch)
    [unit] = (await _charge(client, game_id))["units"]
    assert (unit["name"], unit["roll"], unit["charged"]) == ("D", None, False)

    [unit] = (await _roll(client, game_id, d))["units"]
    assert (unit["dice"], unit["roll"], unit["failed"]) == ([4, 4], 8, False)
    # Rolling again keeps it.
    monkeypatch.setattr("app.services.in_game.charging.random.randint", lambda a_, b: 1)
    [unit] = (await _roll(client, game_id, d))["units"]
    assert unit["roll"] == 8


async def test_targets_in_reach(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch)
    [target] = await _targets(client, game_id, d)
    # Not rolled yet: nothing's in reach.
    assert (target["name"], target["distance"], target["in_reach"]) == ("A", 6.0, False)
    await _roll(client, game_id, d)
    [target] = await _targets(client, game_id, d)
    assert target["in_reach"]


async def test_charge_fails_with_nothing_in_reach(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch, gap=9)
    [unit] = (await _roll(client, game_id, d))["units"]
    assert (unit["roll"], unit["failed"]) == (8, True)
    [target] = await _targets(client, game_id, d)
    assert not target["in_reach"]
    response = await _make(client, game_id, d, a, _shifted(d, dy=8))
    assert response.status_code == 400
    assert "out of reach" in response.json()["detail"]


async def test_charge(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch)
    await _roll(client, game_id, d)
    # 5" of the 8: ends 1" from A, within Engagement Range.
    assert (await _check(client, game_id, d, a, _shifted(d, dy=5)))["valid"]
    response = await _make(client, game_id, d, a, _shifted(d, dy=5))
    assert response.status_code == 200, response.text

    [unit] = (await _charge(client, game_id))["units"]
    assert (unit["charged"], unit["target_name"]) == (True, "A")
    model = _unit_named(await _deployment(client, game_id), "D")["models"][0]
    assert model["position"]["y"] == d["models"][0]["position"]["y"] + 5
    # Once a phase.
    response = await _make(client, game_id, d, a, _shifted(d, dy=5))
    assert "already charged" in response.json()["detail"]


async def test_charge_has_to_reach_engagement_range(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch)
    await _roll(client, game_id, d)
    # 3" of the 8: still 3" away.
    check = await _check(client, game_id, d, a, _shifted(d, dy=3))
    assert check["problems"] == ['No model ends within Engagement Range (2") of A']
    # And no further than the roll.
    check = await _check(client, game_id, d, a, _shifted(d, dy=8.5))
    assert 'D would move 8.5" (it can move 8")' in check["problems"]


async def test_cant_end_on_top_of_the_target(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch)
    await _roll(client, game_id, d)
    check = await _check(client, game_id, d, a, _shifted(d, dy=7))
    assert "D overlaps A" in check["problems"]


async def test_models_that_cant_reach_must_get_closer(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Three models in a row (x 20, 21.5, 23); one reaches A, the others just
    # have to end closer than they started.
    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch, d=3)
    await _roll(client, game_id, d)
    positions = _shifted(d, dy=5, only={0})
    check = await _check(client, game_id, d, a, positions)
    # The two left where they were are no closer.
    assert "D must end closer to A (x2)" in check["problems"]
    # Closer (in coherency), though not in Engagement Range: fine.
    positions = _shifted(d, dy=5, only={0})
    for p in positions[1:]:
        p["y"] += 4
    check = await _check(client, game_id, d, a, positions)
    assert check["valid"], check


async def test_only_in_the_charge_phase(client: AsyncClient, session, tmp_path, monkeypatch):
    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment = await _battle(client, session, tmp_path, units=units)
    d = _unit_named(deployment, "D")
    assert (await _charge(client, game["id"]))["units"] == []
    response = await client.post(ROLL_URL.format(game["id"]), json={"unit_id": d["unit_id"]})
    assert response.status_code == 400
    assert "charge phase" in response.json()["detail"]
