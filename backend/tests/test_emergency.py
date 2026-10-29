from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import DatasheetAbility, Model, UnitModel
from app.routers.games import _load_game
from app.services.in_game import casualties, deployment
from tests.test_reinforcements import _advance_to
from tests.test_scoring_rules import _transport_game

# Seat 1's P (2 models, 2 wounds each) starts embarked in its transport T (1
# model, 2 wounds) at (20, 38); seat 2's D is at (20, 4).


async def _give(session, unit, name):
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    model = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    model.abilities.append(DatasheetAbility(name=name, description=name))
    await session.commit()


async def _destroy_transport(session, game_id, t):
    game = await _load_game(session, game_id)
    casualties.mortal_wounds(game, deployment.find_unit(game, t["unit_id"]), 10)
    await session.commit()


async def _emergency(client, game_id):
    response = await client.get(f"/games/{game_id}/emergency")
    assert response.status_code == 200, response.text
    return response.json()


def _payload(unit, positions):
    return {
        "unit_id": unit["unit_id"],
        "positions": [
            {"unit_model_id": i, "x": x, "y": y, "rotation": 0} for i, (x, y) in positions.items()
        ],
    }


async def test_emergency_disembark_when_the_transport_is_destroyed(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _give(session, t, "Deadly Demise 1")
    await _advance_to(client, game_id, 1, 1, "movement")
    await _destroy_transport(session, game_id, t)

    [unit] = (await _emergency(client, game_id))["units"]
    assert (unit["unit_id"], unit["transport_name"]) == (p["unit_id"], "T")
    # Both models fit touching the wreck.
    assert len(unit["suggested"]) == 2
    # The game waits for it.
    response = await client.post(f"/games/{game_id}/advance")
    assert "emergency disembarking" in response.json()["detail"]

    first, second = (m["unit_model_id"] for m in p["models"])
    url = f"/games/{game_id}/emergency"
    # Further than 6" away, or not touching it with room to: not allowed.
    check = (
        await client.post(f"{url}/check", json=_payload(p, {first: (30, 38), second: (31.5, 38)}))
    ).json()
    assert 'P isn\'t wholly within 6" of its transport (x2)' in check["problems"]
    check = (
        await client.post(f"{url}/check", json=_payload(p, {first: (22.5, 38), second: (24, 38)}))
    ).json()
    assert any("could be touching its transport" in problem for problem in check["problems"])

    # One model set up where suggested; the other left out - destroyed.
    spot = next(s for s in unit["suggested"] if s["unit_model_id"] == first)
    payload = _payload(p, {first: (spot["x"], spot["y"])})
    assert (await client.post(f"{url}/check", json=payload)).json()["valid"]
    # Hazard roll 6 (no wounds); Deadly Demise 6 - it explodes: 1 mortal
    # wound to each unit within 6" (rolled for each).
    monkeypatch.setattr("app.services.in_game.emergency.random.randint", lambda a, b: 6)
    response = await client.post(url, json=payload)
    assert response.status_code == 200, response.text

    emergency = await _emergency(client, game_id)
    assert emergency["units"] == []
    kinds = [(r["kind"], r["roll"], r["wounds"]) for r in emergency["rolls"]]
    assert ("hazard", 6, 0) in kinds
    assert ("deadly_demise", 6, 0) in kinds
    assert ("deadly_demise_wounds", 1, 1) in kinds
    session.expire_all()
    game = await _load_game(session, game_id)
    unit_ = deployment.find_unit(game, p["unit_id"])
    # The left-out model destroyed; the other took the explosion's wound.
    assert casualties.wounds_remaining(game, unit_) == {first: 1}
    assert deployment.battle_formation(game, unit_) is None
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 200, response.text


async def test_a_failed_hazard_roll_after_emergency_disembarking(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    await _destroy_transport(session, game_id, t)
    [unit] = (await _emergency(client, game_id))["units"]
    positions = {s["unit_model_id"]: (s["x"], s["y"]) for s in unit["suggested"]}
    # Hazard rolls of 1 - but P has no INFANTRY or VEHICLE keyword: no wounds.
    monkeypatch.setattr("app.services.in_game.emergency.random.randint", lambda a, b: 1)
    response = await client.post(f"/games/{game_id}/emergency", json=_payload(p, positions))
    assert response.status_code == 200, response.text
    rolls = (await _emergency(client, game_id))["rolls"]
    assert [(r["kind"], r["roll"]) for r in rolls] == [("hazard", 1), ("hazard", 1)]
