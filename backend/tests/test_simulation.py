from httpx import AsyncClient

from tests.test_casualties import _set_models
from tests.test_deployment import _unit_named
from tests.test_movement import _battle

# The calculator's Monte Carlo simulation (POST /combat/simulate): D's five
# models each fire a 1-attack gun (hits on 2+, S4 AP0 D1) at A (5 models, T4,
# 1 wound, no save). Every unit costs 100 points.


async def _units(client, session, tmp_path):
    units = {1: [("A", 5, {})], 2: [("D", 5, {"weapon_range": 24})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _set_models(session, a, wounds=1, save=7)
    from sqlalchemy import select

    from app.models import Weapon

    gun = (await session.execute(select(Weapon).where(Weapon.name == "D gun"))).scalars().first()
    return a, d, gun.id


async def test_simulation(client: AsyncClient, session, tmp_path):
    a, d, gun = await _units(client, session, tmp_path)
    response = await client.post(
        "/combat/simulate",
        json={"attacking_unit_id": d["unit_id"], "defending_unit_id": a["unit_id"],
              "selected_weapon_ids": [gun], "runs": 2000},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["runs"] == 2000
    # 5 attacks hitting on 2+: 4.17 hits; wounding on 4+: 2.08 wounds and
    # damage (no saves) - give or take.
    assert abs(body["hits"]["mean"] - 25 / 6) < 0.15
    assert abs(body["wounds"]["mean"] - 25 / 12) < 0.15
    assert body["damage"]["mean"] == body["wounds"]["mean"]
    assert body["hits"]["sd"] > 0
    # Each wound lost is 20 of A's 100 points: per D point, a fifth of that.
    assert (body["attacker_points"], body["defender_points"], body["defender_wounds"]) == (
        100, 100, 5
    )
    assert abs(body["points_removed"]["mean"] - 20 * body["damage"]["mean"]) < 1e-6
    assert abs(body["efficiency"] - body["points_removed"]["mean"] / 100) < 1e-9


async def test_simulation_runs_are_capped(client: AsyncClient, session, tmp_path):
    a, d, gun = await _units(client, session, tmp_path)
    response = await client.post(
        "/combat/simulate",
        json={"attacking_unit_id": d["unit_id"], "defending_unit_id": a["unit_id"],
              "selected_weapon_ids": [gun], "runs": 100000},
    )
    assert response.status_code == 422
