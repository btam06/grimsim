from httpx import AsyncClient
from sqlalchemy import select

from app.models import Stratagem, StratagemTiming
from tests.test_deployment import (
    R32,
    _declare,
    _deploy,
    _deployment,
    _game,
    _row,
    _set,
    _unit_named,
)

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Seat 1's unit
# R starts in Strategic Reserves (A and D are deployed: A at (20, 40), D at
# (20, 4)). Units have 100 points each, so R is within half of seat 1's army.


async def _rapid_ingress(session):
    # The core Rapid Ingress stratagem (1CP, in the opponent's movement phase).
    stratagem = Stratagem(name="Rapid Ingress", cp=1, is_core=True)
    stratagem.timings = [StratagemTiming(phase="movement", turn="opponent_turn")]
    session.add(stratagem)
    await session.commit()


async def _reserves_game(client, session, tmp_path, r_kwargs=None, rapid_ingress=True):
    if rapid_ingress:
        await _rapid_ingress(session)
    units = {
        1: [("A", 1, {}), ("R", 1, r_kwargs or {}), ("B", 1, {})],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, r, b, d = (_unit_named(deployment, n) for n in "ARBD")
    response = await _set(client, game_id, 1, r, "reserves")
    assert response.status_code == 200, response.text
    for seat in (1, 2):
        await _declare(client, game_id, seat)
    for unit, (x, y) in ((a, (20, 40)), (d, (20, 4)), (b, (30, 40))):
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    return game_id, r


async def _advance_to(client, game_id, battle_round, seat, phase, ended=False):
    # Advances until it's that battle round, seat's turn and phase (for the
    # movement phase, `ended`: the end of it, Rapid Ingress time).
    for _ in range(200):
        game = (await client.get(f"/games/{game_id}")).json()
        reserves = (await client.get(f"/games/{game_id}/reserves")).json()
        at_end = reserves["step"] == "rapid_ingress"
        if (game["battle_round"], game["turn_seat"], game["phase"]) == (
            battle_round, seat, phase
        ) and (phase != "movement" or at_end == ended):
            return game
        response = await client.post(f"/games/{game_id}/advance")
        assert response.status_code == 200, response.text
    raise AssertionError("never got there")


def _at(unit, x, y):
    return [{"unit_model_id": unit["models"][0]["unit_model_id"], "x": x, "y": y}]


async def _check(client, game_id, unit, positions):
    response = await client.post(
        f"/games/{game_id}/reserves/check",
        json={"unit_id": unit["unit_id"], "positions": positions},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _bring_in(client, game_id, unit, positions):
    return await client.post(
        f"/games/{game_id}/reserves", json={"unit_id": unit["unit_id"], "positions": positions}
    )


# On the bottom edge (within 6" of y 44), in seat 1's own zone, far from D.
EDGE = (40, 44 - R32 - 1)


async def test_no_arrivals_in_the_first_battle_round(client: AsyncClient, session, tmp_path):
    game_id, r = await _reserves_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    reserves = (await client.get(f"/games/{game_id}/reserves")).json()
    assert (reserves["step"], reserves["seat"], reserves["units"]) == ("movement", None, [])
    response = await _bring_in(client, game_id, r, _at(r, *EDGE))
    assert "first battle round" in response.json()["detail"]


async def test_bring_a_unit_in_in_battle_round_two(client: AsyncClient, session, tmp_path):
    game_id, r = await _reserves_game(client, session, tmp_path)
    await _advance_to(client, game_id, 2, 1, "movement")
    reserves = (await client.get(f"/games/{game_id}/reserves")).json()
    assert reserves["seat"] == 1
    assert [u["name"] for u in reserves["units"]] == ["R"]

    # Not in the middle of the battlefield...
    check = await _check(client, game_id, r, _at(r, 30, 22))
    assert 'R isn\'t wholly within 6" of a battlefield edge' in check["problems"]
    # ...nor (in the second round) in the enemy's deployment zone.
    check = await _check(client, game_id, r, _at(r, 45, R32 + 1))
    assert check["problems"] == ["R is in the enemy deployment zone"]

    response = await _bring_in(client, game_id, r, _at(r, *EDGE))
    assert response.status_code == 200, response.text
    deployment = await _deployment(client, game_id)
    unit = _unit_named(deployment, "R")
    assert (unit["formation"], unit["models"][0]["position"]["x"]) == (None, 40)
    # It counts as having moved: it can't move again.
    movement = (await client.get(f"/games/{game_id}/movement")).json()
    assert next(u for u in movement["units"] if u["name"] == "R")["arrived"]
    response = await client.post(
        f"/games/{game_id}/movement",
        json={"unit_id": r["unit_id"], "kind": "normal", "positions": _at(r, 40, 40)},
    )
    assert "arrived from Reserves" in response.json()["detail"]


async def test_in_battle_round_three_any_edge_will_do(client: AsyncClient, session, tmp_path):
    game_id, r = await _reserves_game(client, session, tmp_path, rapid_ingress=False)
    await _advance_to(client, game_id, 3, 1, "movement")
    # The top edge, in the enemy's zone - fine now...
    check = await _check(client, game_id, r, _at(r, 45, R32 + 1))
    assert check["valid"], check
    # ...but not within 8" of an enemy model (D, at (20, 4)).
    check = await _check(client, game_id, r, _at(r, 26.3, R32 + 1))
    assert check["problems"] == ['R is within 8" of an enemy model']


async def test_deep_strike_comes_down_anywhere(client: AsyncClient, session, tmp_path):
    game_id, r = await _reserves_game(
        client, session, tmp_path, r_kwargs={"deep_strike": True}, rapid_ingress=False
    )
    await _advance_to(client, game_id, 2, 1, "movement")
    reserves = (await client.get(f"/games/{game_id}/reserves")).json()
    assert reserves["units"][0]["deep_strike"]
    check = await _check(client, game_id, r, _at(r, 30, 22))
    assert check["valid"], check
    # Still 8" from enemy models.
    check = await _check(client, game_id, r, _at(r, 20, 4 + 2 * R32 + 6))
    assert 'R is within 8" of an enemy model' in check["problems"]


async def test_rapid_ingress_at_the_end_of_the_opponents_movement(
    client: AsyncClient, session, tmp_path
):
    game_id, r = await _reserves_game(client, session, tmp_path)
    # Seat 2's movement phase in round 2: it pauses at its end for seat 1.
    game = await _advance_to(client, game_id, 2, 2, "movement")
    response = await _bring_in(client, game_id, r, _at(r, *EDGE))
    assert "only the player whose turn it is" in response.json()["detail"]
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "movement"
    reserves = (await client.get(f"/games/{game_id}/reserves")).json()
    assert (reserves["step"], reserves["seat"]) == ("rapid_ingress", 1)
    # Seat 2 can't move any more.
    cp = next(p["cp"] for p in game["players"] if p["seat"] == 1)
    response = await _bring_in(client, game_id, r, _at(r, *EDGE))
    assert response.status_code == 200, response.text
    game = response.json()
    assert next(p["cp"] for p in game["players"] if p["seat"] == 1) == cp - 1
    assert _unit_named(await _deployment(client, game_id), "R")["models"][0]["position"]
    # On to the shooting phase.
    assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == "shooting"


async def test_no_pause_without_rapid_ingress(client: AsyncClient, session, tmp_path):
    # Without the stratagem (or reserves), the movement phase just ends.
    game_id, r = await _reserves_game(client, session, tmp_path, rapid_ingress=False)
    await _advance_to(client, game_id, 2, 2, "movement")
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "shooting"


async def test_reserves_still_off_the_battlefield_after_round_three_are_destroyed(
    client: AsyncClient, session, tmp_path
):
    game_id, r = await _reserves_game(client, session, tmp_path, rapid_ingress=False)
    await _advance_to(client, game_id, 3, 1, "fight")
    assert _unit_named(await _deployment(client, game_id), "R")["formation"] == "reserves"
    await _advance_to(client, game_id, 4, 2, "command")
    unit = _unit_named(await _deployment(client, game_id), "R")
    assert unit["formation"] == "destroyed"
    assert unit["destroyed"]
    reserves = (await client.get(f"/games/{game_id}/reserves")).json()
    assert reserves["units"] == []
