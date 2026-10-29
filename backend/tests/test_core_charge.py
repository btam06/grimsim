from httpx import AsyncClient

from tests.test_charging import ROLL_URL, _charge
from tests.test_deployment import R32, _deployment, _unit_named
from tests.test_movement import _battle
from tests.test_shooting import _place

# The Core Rules' charges (11.02, 11.04): declared only within 12" of an
# enemy and unengaged; one or more charge targets; the unit ends engaged with
# all of them and no other enemy unit. Each charge die rolls a 4 (8").


async def _game(client, session, tmp_path, monkeypatch, places):
    monkeypatch.setattr("app.services.in_game.charging.random.randint", lambda a_, b: 4)
    units = {1: [("A", 1, {}), ("B", 1, {})], 2: [("D", 2, {})]}
    game, deployment_ = await _battle(
        client, session, tmp_path, units=units,
        spots={"A": (20, 38), "B": (40, 38), "D": (20, 4)},
    )
    u = {x["name"]: x for x in deployment_["units"]}
    for name, spots in places.items():
        await _place(session, u[name], spots)
    for phase in ("shooting", "charge"):
        await client.post(f"/games/{game['id']}/advance")
    deployment_ = await _deployment(client, game["id"])
    return game["id"], {x["name"]: x for x in deployment_["units"]}


def _positions(unit, spots):
    return [
        {"unit_model_id": m["unit_model_id"], "x": x, "y": y}
        for m, (x, y) in zip(unit["models"], spots)
    ]


async def test_no_charge_without_an_enemy_within_12(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, u = await _game(
        client, session, tmp_path, monkeypatch,
        {"D": [(20, 4), (21.5, 4)], "A": [(20, 30)], "B": [(40, 30)]},
    )
    [d] = [x for x in (await _charge(client, game_id))["units"] if x["name"] == "D"]
    assert d["reason"] == 'no enemy unit is within 12"'
    response = await client.post(ROLL_URL.format(game_id), json={"unit_id": u["D"]["unit_id"]})
    assert response.status_code == 400


async def test_two_charge_targets(client: AsyncClient, session, tmp_path, monkeypatch):
    # A and B side by side, 4" in front of D's two models.
    y = 4 + 2 * R32 + 4
    game_id, u = await _game(
        client, session, tmp_path, monkeypatch,
        {"D": [(20, 4), (23, 4)], "A": [(20, y)], "B": [(23.5, y)]},
    )
    await client.post(ROLL_URL.format(game_id), json={"unit_id": u["D"]["unit_id"]})
    up = _positions(u["D"], [(20, y - 2 * R32 - 1), (23, y - 2 * R32 - 1)])
    one = {"unit_id": u["D"]["unit_id"], "target_unit_ids": [u["A"]["unit_id"]], "positions": up}
    check = (await client.post(f"/games/{game_id}/charge/check", json=one)).json()
    # Engaged with B too, which isn't a charge target.
    assert any("isn't a charge target" in p for p in check["problems"])
    both = {**one, "target_unit_ids": [u["A"]["unit_id"], u["B"]["unit_id"]]}
    check = (await client.post(f"/games/{game_id}/charge/check", json=both)).json()
    assert check["valid"], check
    response = await client.post(f"/games/{game_id}/charge", json=both)
    assert response.status_code == 200, response.text
    [d] = [x for x in (await _charge(client, game_id))["units"] if x["name"] == "D"]
    assert sorted(d["target_names"]) == ["A", "B"]
