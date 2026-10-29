from httpx import AsyncClient

from tests.test_deployment import R32, _deployment, _unit_named
from tests.test_movement import _battle, _shifted
from tests.test_shooting import _place

# Surge moves (21.02): seat 2's D (at (20, 4)) surges towards the closest
# enemy unit, A, 4" away (base to base, straight down the board) - B is
# further.


async def _surge_game(client, session, tmp_path):
    units = {1: [("A", 1, {}), ("B", 1, {})], 2: [("D", 1, {})]}
    spots = {"A": (20, 38), "B": (30, 38), "D": (20, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    a, b = _unit_named(deployment_, "A"), _unit_named(deployment_, "B")
    await _place(session, a, [(20, 4 + 2 * R32 + 4)])
    await _place(session, b, [(40, 30)])
    return game["id"], _unit_named(await _deployment(client, game["id"]), "D")


async def test_a_surge_move(client: AsyncClient, session, tmp_path):
    game_id, d = await _surge_game(client, session, tmp_path)
    url = f"/games/{game_id}/surge-moves"
    response = await client.post(f"{url}/start", json={"unit_id": d["unit_id"], "distance": "3"})
    assert response.status_code == 200, response.text
    [surge] = response.json()
    assert (surge["distance"], surge["target_name"]) == (3, "A")
    # Away from A: not allowed.
    check = (await client.post(
        f"{url}/check", json={"unit_id": d["unit_id"], "positions": _shifted(d, dx=2)}
    )).json()
    assert "D must end closer to A" in check["problems"]
    response = await client.post(
        url, json={"unit_id": d["unit_id"], "positions": _shifted(d, dy=2.5)}
    )
    assert response.status_code == 200, response.text
    # Once a phase.
    response = await client.post(f"{url}/start", json={"unit_id": d["unit_id"], "distance": "3"})
    assert "already surged" in response.json()["detail"]
