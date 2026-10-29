from httpx import AsyncClient
from sqlalchemy import delete

from app.models import GameModelDamage, GameModelPosition
from app.routers.games import _load_game
from app.services.in_game import casualties, deployment
from tests.test_reinforcements import _advance_to
from tests.test_scoring_rules import _at, _transport_game

# Seat 1's P (2 models, 2 wounds each) starts embarked in its transport T at
# (20, 38); seat 2's D is at (20, 4). Seat 2 goes first.

NEXT_TO_T = [(21.5, 38), (21.5, 39.5)]


async def _move(client, game_id, unit, spots, kind="normal"):
    return await client.post(
        f"/games/{game_id}/movement",
        json={"unit_id": unit["unit_id"], "kind": kind, "positions": _at(unit, spots)},
    )


async def _embarked(client, game_id):
    return (await client.get(f"/games/{game_id}/embarked")).json()


async def _embark(client, game_id, unit, transport):
    return await client.post(
        f"/games/{game_id}/embarked/embark",
        json={"unit_id": unit["unit_id"], "transport_unit_id": transport["unit_id"]},
    )


async def _disembark(client, game_id, unit, spots):
    return await client.post(
        f"/games/{game_id}/embarked",
        json={"unit_id": unit["unit_id"], "positions": _at(unit, spots)},
    )


async def test_embarking_during_the_battle(client: AsyncClient, session, tmp_path):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    response = await _disembark(client, game_id, p, NEXT_TO_T)
    assert response.status_code == 200, response.text
    response = await _move(client, game_id, p, [(23, 38), (23, 39.5)])
    assert response.status_code == 200, response.text
    # Not in the same phase it disembarked.
    assert (await _embarked(client, game_id))["embarkable"] == []
    response = await _embark(client, game_id, p, t)
    assert "disembarked this phase" in response.json()["detail"]

    await _advance_to(client, game_id, 2, 1, "movement")
    # It has to move first.
    response = await _embark(client, game_id, p, t)
    assert "hasn't made a Normal, Advance or Fall Back move" in response.json()["detail"]
    # Ending further than 3" away, it can't.
    response = await _move(client, game_id, p, [(27, 38), (27, 39.5)])
    assert response.status_code == 200, response.text
    assert (await _embarked(client, game_id))["embarkable"] == []
    response = await _embark(client, game_id, p, t)
    assert 'within 3"' in response.json()["detail"]
    # Within 3" of it, it can.
    response = await _move(client, game_id, p, [(22, 38), (22, 39.5)])
    assert response.status_code == 200, response.text
    [unit] = (await _embarked(client, game_id))["embarkable"]
    assert (unit["unit_id"], unit["transports"]) == (
        p["unit_id"], [{"unit_id": t["unit_id"], "name": "T"}]
    )
    response = await _embark(client, game_id, p, t)
    assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, p["unit_id"])
    assert not deployment.is_deployed(unit, deployment.positions(game))
    assert deployment.battle_formation(game, unit).transport_unit_id == t["unit_id"]
    # Not out again in the same phase...
    assert (await _embarked(client, game_id))["units"] == []
    response = await _disembark(client, game_id, p, NEXT_TO_T)
    assert "embarked this phase" in response.json()["detail"]
    # ...but in a later one.
    await _advance_to(client, game_id, 3, 1, "movement")
    response = await _disembark(client, game_id, p, NEXT_TO_T)
    assert response.status_code == 200, response.text


async def test_embarking_keeps_wounds_and_losses(client: AsyncClient, session, tmp_path):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    await _disembark(client, game_id, p, NEXT_TO_T)
    await _advance_to(client, game_id, 2, 1, "movement")
    # One of P's models is destroyed, the other has lost a wound.
    first, second = (m["unit_model_id"] for m in p["models"])
    session.add(GameModelDamage(game_id=game_id, unit_model_id=first, wounds_lost=2, destroyed=True))
    session.add(GameModelDamage(game_id=game_id, unit_model_id=second, wounds_lost=1))
    await session.execute(
        delete(GameModelPosition).where(
            GameModelPosition.game_id == game_id, GameModelPosition.unit_model_id == first
        )
    )
    await session.commit()
    response = await client.post(
        f"/games/{game_id}/movement",
        json={
            "unit_id": p["unit_id"], "kind": "normal",
            "positions": [{"unit_model_id": second, "x": 22, "y": 38}],
        },
    )
    assert response.status_code == 200, response.text
    response = await _embark(client, game_id, p, t)
    assert response.status_code == 200, response.text

    await _advance_to(client, game_id, 3, 1, "movement")
    # Only the surviving model comes out - still wounded.
    response = await _disembark(client, game_id, p, NEXT_TO_T)
    assert "place every model" in response.json()["detail"]
    response = await client.post(
        f"/games/{game_id}/embarked",
        json={"unit_id": p["unit_id"], "positions": [{"unit_model_id": second, "x": 21.5, "y": 38}]},
    )
    assert response.status_code == 200, response.text
    session.expire_all()
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, p["unit_id"])
    assert casualties.wounds_remaining(game, unit) == {second: 1}


async def test_no_disembarking_after_the_transport_advanced(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    monkeypatch.setattr("app.services.in_game.movement.random.randint", lambda a, b: 3)
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    response = await client.post(
        f"/games/{game_id}/movement/advance", json={"unit_id": t["unit_id"]}
    )
    assert response.status_code == 200, response.text
    response = await _move(client, game_id, t, [(20, 32)], kind="advance")
    assert response.status_code == 200, response.text
    response = await _disembark(client, game_id, p, [(21.5, 32), (21.5, 33.5)])
    assert "its transport Advanced this turn" in response.json()["detail"]


async def test_a_rapid_disembark_after_the_transport_moved(
    client: AsyncClient, session, tmp_path
):
    # T makes a Normal move: P's disembark is rapid - it can't move or charge.
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    assert (await _embarked(client, game_id))["units"][0]["mode"] == "tactical"
    assert (await _move(client, game_id, t, [(20, 34)])).status_code == 200
    assert (await _embarked(client, game_id))["units"][0]["mode"] == "rapid"
    response = await _disembark(client, game_id, p, [(21.5, 34), (21.5, 35.5)])
    assert response.status_code == 200, response.text
    response = await _move(client, game_id, p, [(21.5, 33), (21.5, 34.5)])
    assert response.status_code == 400
    session.expire_all()
    game = await _load_game(session, game_id)
    from app.services.in_game import embarked

    unit = deployment.find_unit(game, p["unit_id"])
    assert embarked.no_charge(game, unit) == "it made a rapid disembark move this turn"


async def test_a_combat_disembark(client: AsyncClient, session, tmp_path, monkeypatch):
    # Within 6" (not 3"), with hazard rolls - then Battle-shocked.
    from app.services.in_game import battle_shock

    monkeypatch.setattr("random.randint", lambda a, b: 6)
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    spots = [(25, 38), (25, 39.5)]
    url = f"/games/{game_id}/embarked"
    payload = {"unit_id": p["unit_id"], "positions": _at(p, spots)}
    check = (await client.post(f"{url}/check", json=payload)).json()
    assert 'P isn\'t wholly within 3" of its transport (x2)' in check["problems"]
    payload["combat_disembark"] = True
    assert (await client.post(f"{url}/check", json=payload)).json()["valid"]
    response = await client.post(url, json=payload)
    assert response.status_code == 200, response.text
    session.expire_all()
    game = await _load_game(session, game_id)
    assert battle_shock.is_battle_shocked(game, deployment.find_unit(game, p["unit_id"]))


async def test_no_embarking_after_being_set_up_this_turn(
    client: AsyncClient, session, tmp_path
):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    assert (await _disembark(client, game_id, p, NEXT_TO_T)).status_code == 200
    from app.services.in_game import embarked

    session.expire_all()
    game = await _load_game(session, game_id)
    reason = embarked.embark_reason(game, deployment.find_unit(game, p["unit_id"]))
    assert reason is not None
