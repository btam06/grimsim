from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import DatasheetAbility, Model, UnitModel
from tests.test_deployment import _declare, _deploy, _deployment, _game, _row, _set, _unit_named
from tests.test_reinforcements import _advance_to, _at, _rapid_ingress

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Seat 1's R
# (with a Teleport Homer) starts in Strategic Reserves; A is at (20, 40), B at
# (30, 40), and seat 2's D at (20, 4).

TOKEN = (45, 24)


async def _homer_game(client, session, tmp_path):
    await _rapid_ingress(session)
    units = {1: [("A", 1, {}), ("R", 1, {}), ("B", 1, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, r, b, d = (_unit_named(deployment, n) for n in "ARBD")
    unit_model = await session.get(UnitModel, r["models"][0]["unit_model_id"])
    model = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    model.abilities.append(DatasheetAbility(name="Teleport Homer", description="Teleport Homer"))
    await session.commit()
    response = await _set(client, game_id, 1, r, "reserves")
    assert response.status_code == 200, response.text
    for seat in (1, 2):
        await _declare(client, game_id, seat)
    for unit, (x, y) in ((a, (20, 40)), (d, (20, 4)), (b, (30, 40))):
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    return game_id, r, d


async def _homers(client, game_id):
    return (await client.get(f"/games/{game_id}/teleport-homers")).json()


async def _place(client, game_id, seat, unit, spot):
    return await client.post(
        f"/games/{game_id}/teleport-homers",
        json={"seat": seat, "unit_id": unit["unit_id"], "x": spot[0], "y": spot[1]},
    )


async def test_teleport_homer_tokens_at_the_start_of_the_battle(
    client: AsyncClient, session, tmp_path
):
    game_id, r, d = await _homer_game(client, session, tmp_path)
    homers = await _homers(client, game_id)
    assert homers["waiting_seats"] == [1]
    [unit] = homers["units"]
    assert (unit["unit_id"], unit["token"]) == (r["unit_id"], None)
    # The game waits until seat 1's done.
    response = await client.post(f"/games/{game_id}/advance")
    assert "Teleport Homer" in response.json()["detail"]
    response = await _place(client, game_id, 1, r, (70, 24))
    assert "on the battlefield" in response.json()["detail"]
    response = await _place(client, game_id, 1, r, TOKEN)
    assert response.status_code == 200, response.text
    assert response.json()["tokens"][0]["x"] == TOKEN[0]
    response = await client.post(f"/games/{game_id}/teleport-homers/done", json={"seat": 1})
    assert response.status_code == 200, response.text
    assert (await _homers(client, game_id))["waiting_seats"] == []
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 200, response.text


async def test_rapid_ingress_at_the_teleport_homer(client: AsyncClient, session, tmp_path):
    game_id, r, d = await _homer_game(client, session, tmp_path)
    await _place(client, game_id, 1, r, TOKEN)
    await client.post(f"/games/{game_id}/teleport-homers/done", json={"seat": 1})
    await _advance_to(client, game_id, 2, 2, "movement", ended=True)
    reserves = (await client.get(f"/games/{game_id}/reserves")).json()
    [unit] = reserves["units"]
    assert unit["teleport_homer"] == {"x": TOKEN[0], "y": TOKEN[1]}

    url = f"/games/{game_id}/reserves"
    far = {"unit_id": r["unit_id"], "positions": _at(r, 50, 24), "teleport_homer": True}
    check = (await client.post(f"{url}/check", json=far)).json()
    assert 'R isn\'t within 3" of its Teleport Homer token' in check["problems"]
    near = {"unit_id": r["unit_id"], "positions": _at(r, 46.5, 24), "teleport_homer": True}
    assert (await client.post(f"{url}/check", json=near)).json()["valid"]
    game = (await client.get(f"/games/{game_id}")).json()
    cp = next(p["cp"] for p in game["players"] if p["seat"] == 1)
    response = await client.post(url, json=near)
    assert response.status_code == 200, response.text
    # Rapid Ingress (1CP) for 1CP less; the token's used.
    game = response.json()
    assert next(p["cp"] for p in game["players"] if p["seat"] == 1) == cp
    assert (await _homers(client, game_id))["tokens"] == []


async def test_an_enemy_ending_a_move_near_the_token_removes_it(
    client: AsyncClient, session, tmp_path
):
    game_id, r, d = await _homer_game(client, session, tmp_path)
    await _place(client, game_id, 1, r, (20, 10))
    await client.post(f"/games/{game_id}/teleport-homers/done", json={"seat": 1})
    await _advance_to(client, game_id, 1, 2, "movement")
    d = _unit_named(await _deployment(client, game_id), "D")
    response = await client.post(
        f"/games/{game_id}/movement",
        json={"unit_id": d["unit_id"], "kind": "normal", "positions": _at(d, 20, 8.5)},
    )
    assert response.status_code == 200, response.text
    assert (await _homers(client, game_id))["tokens"] == []
