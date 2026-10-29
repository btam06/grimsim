from httpx import AsyncClient

from tests.test_deployment import _deployment, _unit_named
from tests.test_reinforcements import _advance_to
from tests.test_scoring import _end_turn, _game, _secondary
from tests.test_shooting import _place, _to_shooting

# Games on the test layout ("Strips": seat 1, the attacker, deploys along y
# 32-44 and its territory is y 22-44; seat 2 along y 0-12, its territory y
# 0-22), seat 2 going first. The one objective is the Medium ruin's terrain
# area (x 7-13, y 8-12): central, and in seat 2's territory. Seat 1 has A (1
# model), seat 2 has D (2 models, each with a 24" gun).

ON_THE_RUIN = [(9, 10), (11, 10)]


async def _actions(client, game_id):
    response = await client.get(f"/games/{game_id}/actions")
    assert response.status_code == 200, response.text
    return response.json()


async def _start(client, game_id, unit, action, target_id):
    return await client.post(
        f"/games/{game_id}/actions",
        json={"unit_id": unit["unit_id"], "action": action, "target_id": target_id},
    )


async def test_cleanse_instead_of_shooting(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 2, "Cleanse")
    await _place(session, d, ON_THE_RUIN)
    await _to_shooting(client, game_id)

    [option] = (await _actions(client, game_id))["options"][str(d["unit_id"])]
    assert (option["action"], option["reason"]) == ("Cleanse", None)
    [target] = option["targets"]
    assert (target["kind"], target["label"]) == ("objective", "a central objective")
    response = await _start(client, game_id, d, "Cleanse", target["id"])
    assert response.status_code == 200, response.text
    [started] = response.json()["started"]
    assert (started["unit_name"], started["status"]) == ("D", "started")

    # It can't shoot now (nor start another action).
    shooting = (await client.get(f"/games/{game_id}/shooting")).json()["units"]
    assert next(u for u in shooting if u["unit_id"] == d["unit_id"])["reason"] == (
        "it started an action this turn (Cleanse)"
    )
    response = await _start(client, game_id, d, "Cleanse", target["id"])
    assert "already started an action" in response.json()["detail"]

    # The end of the turn: still controlling the objective - cleansed.
    await _end_turn(client, game_id)
    [offer] = (await client.get(f"/games/{game_id}/scoring")).json()["offers"]
    assert (offer["name"], offer["points"]) == ("Cleanse", 2)


async def test_cleanse_fails_if_it_isnt_controlling_the_objective(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 2, "Cleanse")
    await _place(session, d, ON_THE_RUIN)
    await _to_shooting(client, game_id)
    [option] = (await _actions(client, game_id))["options"][str(d["unit_id"])]
    await _start(client, game_id, d, "Cleanse", option["targets"][0]["id"])
    # Moved off it before the end of the turn.
    await _place(session, d, [(20, 4), (21.5, 4)])
    await _end_turn(client, game_id)
    assert (await client.get(f"/games/{game_id}/scoring")).json()["offers"] == []
    started = await _actions(client, game_id)
    # (Now seat 1's turn: last turn's actions are in the record of that turn.)
    assert started["started"] == []


async def test_only_with_a_card_and_somewhere_to_do_it(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _to_shooting(client, game_id)
    # No mission card with an action: none.
    assert (await _actions(client, game_id))["options"][str(d["unit_id"])] == []

    # Plunder: D is on the ruin, but that's in its own territory.
    await _secondary(session, game_id, 2, "Plunder")
    await _place(session, d, ON_THE_RUIN)
    [option] = (await _actions(client, game_id))["options"][str(d["unit_id"])]
    assert option["action"] == "Plunder"
    assert option["reason"] == "it isn't within a terrain area it can do it in"


async def test_no_action_after_advancing(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 2, "Cleanse")
    await client.post(f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"]})
    moved = _unit_named(await _deployment(client, game_id), "D")
    response = await client.post(
        f"/games/{game_id}/movement",
        json={
            "unit_id": d["unit_id"],
            "kind": "advance",
            "positions": [
                {
                    "unit_model_id": m["unit_model_id"],
                    "x": m["position"]["x"],
                    "y": m["position"]["y"] + 2,
                }
                for m in moved["models"]
            ],
        },
    )
    assert response.status_code == 200, response.text
    await _to_shooting(client, game_id)
    [option] = (await _actions(client, game_id))["options"][str(d["unit_id"])]
    assert option["reason"] == "it Advanced this turn"


async def test_plunder_completes_at_once_and_stops_charging(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Seat 1's A on the ruin: in seat 2's territory, so it can plunder it.
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 1, "Plunder")
    await _advance_to(client, game_id, 1, 1, "movement")
    await _place(session, a, [(10, 10)])
    await _to_shooting(client, game_id)
    [option] = (await _actions(client, game_id))["options"][str(a["unit_id"])]
    [target] = option["targets"]
    assert (target["kind"], target["label"]) == ("area", "Medium ruin (a central objective)")
    [started] = (await _start(client, game_id, a, "Plunder", target["id"])).json()["started"]
    assert started["status"] == "completed"

    await client.post(f"/games/{game_id}/advance")
    charge = (await client.get(f"/games/{game_id}/charge")).json()["units"]
    assert next(u for u in charge if u["unit_id"] == a["unit_id"])["reason"] == (
        "it started an action this turn (Plunder)"
    )
    await _end_turn(client, game_id)
    [offer] = (await client.get(f"/games/{game_id}/scoring")).json()["offers"]
    assert (offer["name"], offer["points"]) == ("Plunder", 5)


def _battle_shock_dice(monkeypatch, *rolls):
    values = iter(rolls)
    monkeypatch.setattr(
        "app.services.in_game.battle_shock.random.randint", lambda a, b: next(values)
    )


async def _shock(client, game_id, unit, monkeypatch):
    # A rule makes the unit take a Battle-shock test, and it fails (1 + 1).
    _battle_shock_dice(monkeypatch, 1, 1)
    state = (
        await client.post(
            f"/games/{game_id}/battle-shock/test",
            json={"unit_id": unit["unit_id"], "reason": "A rule"},
        )
    ).json()
    [test] = state["pending"]
    response = await client.post(
        f"/games/{game_id}/battle-shock/{test['id']}/take", json={"insane_bravery": False}
    )
    assert response.json()["battle_shocked"], response.text


async def test_battle_shocked_units_cant_do_actions(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 2, "Cleanse")
    await _place(session, d, ON_THE_RUIN)
    await _shock(client, game_id, d, monkeypatch)
    await _to_shooting(client, game_id)
    [option] = (await _actions(client, game_id))["options"][str(d["unit_id"])]
    assert option["reason"] == "it's Battle-shocked"


async def test_an_action_fails_if_its_unit_becomes_battle_shocked(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 2, "Cleanse")
    await _place(session, d, ON_THE_RUIN)
    await _to_shooting(client, game_id)
    [option] = (await _actions(client, game_id))["options"][str(d["unit_id"])]
    await _start(client, game_id, d, "Cleanse", option["targets"][0]["id"])
    await _shock(client, game_id, d, monkeypatch)
    [started] = (await _actions(client, game_id))["started"]
    assert started["status"] == "failed"
    await _end_turn(client, game_id)
    assert (await client.get(f"/games/{game_id}/scoring")).json()["offers"] == []


async def test_an_action_survives_an_enemy_engaging_its_unit(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # 16: becoming engaged doesn't stop an action completing - making a move
    # does (see the next test).
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 2, "Cleanse")
    await _place(session, d, ON_THE_RUIN)
    await _to_shooting(client, game_id)
    [option] = (await _actions(client, game_id))["options"][str(d["unit_id"])]
    await _start(client, game_id, d, "Cleanse", option["targets"][0]["id"])
    # An enemy unit next to it by the end of the turn.
    await _place(session, a, [(12.5, 11.5)])
    await _end_turn(client, game_id)
    assert (await client.get(f"/games/{game_id}/scoring")).json()["offers"] != []


async def test_an_action_fails_if_its_unit_moves(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    from app.routers.games import _load_game
    from app.services.in_game import deployment, mission_state

    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 2, "Cleanse")
    await _place(session, d, ON_THE_RUIN)
    await _to_shooting(client, game_id)
    [option] = (await _actions(client, game_id))["options"][str(d["unit_id"])]
    await _start(client, game_id, d, "Cleanse", option["targets"][0]["id"])
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    # A pile-in or consolidation move doesn't fail it; any other move does.
    mission_state.after_move(game, unit, "consolidate")
    assert [r.status for r in game.actions] == ["started"]
    mission_state.after_move(game, unit)
    assert [r.status for r in game.actions] == ["failed"]
