from httpx import AsyncClient
from sqlalchemy import select

from app.models import GameOperationMarker, GamePlayer, PrimaryMission
from tests.test_casualties import _set_models
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named
from tests.test_reinforcements import _advance_to
from tests.test_scoring import _end_turn
from tests.test_shooting import _place, _shoot, _to_shooting

# Games on the test layout ("Strips": seat 1, the attacker, deploys along y
# 32-44; seat 2 along y 0-12, and goes first). Its terrain areas: the Medium
# ruin (x 7-13, y 8-12 - in seat 2's deployment zone), which is the one
# objective (central), and a triangle near the middle. Seat 1 has A (1 model
# of 2 wounds, no save), seat 2 has D (2 models, each with a 24" gun); every
# die rolls a 6, so D's shooting destroys A.

ON_THE_RUIN = [(9, 10), (11, 10)]


async def _mission_game(client, session, tmp_path, monkeypatch, primaries, d_spot=(9, 10)):
    # `primaries`: {seat: primary mission card} - in place before the battle
    # starts.
    monkeypatch.setattr("app.services.combat.random.randint", lambda a, b: 6)
    units = {1: [("A", 1, {})], 2: [("D", 2, {"weapon_range": 24})]}
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    for seat, name in primaries.items():
        player = (
            await session.execute(
                select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.seat == seat)
            )
        ).scalar_one()
        mission = await session.get(PrimaryMission, player.primary_mission_id)
        mission.name = name
    await session.commit()
    deployment = await _deployment(client, game_id)
    a, d = _unit_named(deployment, "A"), _unit_named(deployment, "D")
    await _set_models(session, a, save=7)
    for unit, spot in ((a, (20, 38)), (d, d_spot)):
        response = await _deploy(client, game_id, unit, _row(unit, *spot))
        assert response.status_code == 200, response.text
    # On to seat 2's movement phase - unless a mission's choice is waiting.
    if not (await _mission(client, game_id))["prompts"]:
        response = await client.post(f"/games/{game_id}/advance")
        assert response.json()["phase"] == "movement", response.text
    return game_id, a, d


async def _mission(client, game_id):
    response = await client.get(f"/games/{game_id}/mission")
    assert response.status_code == 200, response.text
    return response.json()


async def _answer(client, game_id, prompt, ids=(), consecrations=None):
    return await client.post(
        f"/games/{game_id}/mission/prompts/{prompt['id']}",
        json={"ids": list(ids), "consecrations": consecrations or {}},
    )


async def _action(client, game_id, unit, name):
    # Starts the unit's action `name` on its first target.
    options = (await client.get(f"/games/{game_id}/actions")).json()["options"]
    option = next(o for o in options[str(unit["unit_id"])] if o["action"] == name)
    assert option["reason"] is None, option
    response = await client.post(
        f"/games/{game_id}/actions",
        json={"unit_id": unit["unit_id"], "action": name, "target_id": option["targets"][0]["id"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _primary_scores(client, game_id, seat):
    game = (await client.get(f"/games/{game_id}")).json()
    player = next(p for p in game["players"] if p["seat"] == seat)
    return [r for s in player["scores"] if s["kind"] == "primary" for r in s["reasons"]]


async def _triangle(client, game_id) -> int:
    # The triangle terrain area's id.
    game = (await client.get(f"/games/{game_id}")).json()
    layout = (await client.get(f"/terrain-layouts/{game['terrain_layout_id']}")).json()
    return next(a["id"] for a in layout["areas"] if a["shape_name"] == "Triangle")


async def _markers(session, game_id, seat, count, objective_id=None, area_id=None):
    for _ in range(count):
        session.add(
            GameOperationMarker(
                game_id=game_id, seat=seat, source="test", objective_id=objective_id,
                area_id=area_id, placed_round=1,
            )
        )
    await session.commit()


async def test_locate_and_deny_places_markers_at_the_start(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Locate and Deny"}
    )
    [prompt] = (await _mission(client, game_id))["prompts"]
    # Only the triangle isn't within seat 2's deployment zone: one marker.
    assert (prompt["kind"], prompt["seat"], prompt["pick_min"]) == ("place_markers", 2, 1)
    [area] = prompt["options"]
    response = await client.post(f"/games/{game_id}/advance")
    assert "missions' choices" in response.json()["detail"]
    state = (await _answer(client, game_id, prompt, [area["id"]])).json()
    assert state["prompts"] == []
    [marker] = state["markers"]
    assert (marker["seat"], marker["source"], marker["area_id"]) == (
        2, "Locate and Deny", area["id"]
    )
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 200


async def test_decoy_places_a_marker_and_scores(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Smoke and Mirrors"}
    )
    await _to_shooting(client, game_id)
    await _action(client, game_id, d, "Decoy")
    await _end_turn(client, game_id)
    [marker] = (await _mission(client, game_id))["markers"]
    assert (marker["seat"], marker["source"]) == (2, "Decoy")
    assert {"text": "For each objective that is decoyed (1)", "points": 2} in (
        await _primary_scores(client, game_id, 2)
    )


async def test_a_sensor_sweep_removes_a_marker(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Extract Relic"}
    )
    await _markers(session, game_id, 1, 2, area_id=await _triangle(client, game_id))
    await _to_shooting(client, game_id)
    await _action(client, game_id, d, "Sensor Sweep")
    # The end of the turn: it completes, and seat 2 picks a marker to remove.
    response = await _end_turn(client, game_id)
    assert response.json()["turn_seat"] == 2
    [prompt] = (await _mission(client, game_id))["prompts"]
    assert (prompt["kind"], len(prompt["options"])) == ("remove_marker", 2)
    state = (await _answer(client, game_id, prompt, [prompt["options"][0]["id"]])).json()
    assert len(state["markers"]) == 1
    await client.post(f"/games/{game_id}/advance")
    assert {"text": "A friendly unit performed a sensor sweep this turn", "points": 4} in (
        await _primary_scores(client, game_id, 2)
    )


async def test_no_sensor_sweep_with_one_marker(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Extract Relic"}
    )
    await _markers(session, game_id, 1, 1, area_id=await _triangle(client, game_id))
    await _to_shooting(client, game_id)
    options = (await client.get(f"/games/{game_id}/actions")).json()["options"]
    [option] = options[str(d["unit_id"])]
    assert "only one operation marker" in option["reason"]


async def test_surveil_the_foe(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Surveil the Foe"}, d_spot=(20, 4)
    )
    # A within 18" of D (and not on an objective).
    await _place(session, a, [(20, 18)])
    await _to_shooting(client, game_id)
    state = await _action(client, game_id, d, "Surveil the Foe")
    [started] = state["started"]
    assert (started["target"], started["status"]) == ("A", "completed")
    assert [m["kind"] for m in (await _mission(client, game_id))["marked"]] == ["surveilled"]
    await _end_turn(client, game_id)
    reasons = await _primary_scores(client, game_id, 2)
    assert {"text": "One or more enemy units were surveilled this turn", "points": 4} in reasons


async def test_surveil_the_foe_removes_markers_when_a_unit_ends_a_move_there(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Surveil the Foe"}, d_spot=(17, 6)
    )
    objective_id = (await _deployment(client, game_id))["objectives"][0]["objective_id"]
    await _markers(session, game_id, 1, 1, objective_id=objective_id)
    assert len((await _mission(client, game_id))["markers"]) == 1
    moved = _unit_named(await _deployment(client, game_id), "D")
    response = await client.post(
        f"/games/{game_id}/movement",
        json={
            "unit_id": d["unit_id"],
            "kind": "normal",
            "positions": [
                {"unit_model_id": m["unit_model_id"], "x": x, "y": y}
                for m, (x, y) in zip(moved["models"], [(13.4, 8.4), (14.9, 8.4)])
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert (await _mission(client, game_id))["markers"] == []


async def test_punishment_condemns_and_scores(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Punishment"}
    )
    # The start of seat 2's turn: A isn't on an objective and didn't destroy
    # anything, so any one enemy unit.
    [prompt] = (await _mission(client, game_id))["prompts"]
    assert (prompt["kind"], prompt["pick_max"]) == ("condemn", 1)
    await _answer(client, game_id, prompt, [a["unit_id"]])
    await client.post(f"/games/{game_id}/advance")
    marked = (await _mission(client, game_id))["marked"]
    assert [(m["unit_name"], m["kind"]) for m in marked] == [("A", "condemned")]
    await _place(session, a, [(20, 24)])
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    await _end_turn(client, game_id)
    reasons = await _primary_scores(client, game_id, 2)
    assert {
        "text": "One or more condemned enemy units left the battlefield this turn", "points": 5
    } in reasons


async def test_consecrate(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _mission_game(client, session, tmp_path, monkeypatch, {2: "Consecrate"})
    await _place(session, a, [(20, 24)])
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    # D destroyed a unit: it's a consecration unit.
    assert [m["kind"] for m in (await _mission(client, game_id))["marked"]] == ["consecration"]
    await _end_turn(client, game_id)
    [prompt] = (await _mission(client, game_id))["prompts"]
    [option] = prompt["options"]
    assert (prompt["kind"], option["unit_id"]) == ("consecrate", d["unit_id"])
    state = (
        await _answer(client, game_id, prompt, consecrations={d["unit_id"]: option["id"]})
    ).json()
    assert [m["source"] for m in state["markers"]] == ["Consecrate"]
    assert state["marked"] == []
    await client.post(f"/games/{game_id}/advance")
    assert {"text": "One or two objectives are consecrated", "points": 3} in (
        await _primary_scores(client, game_id, 2)
    )


async def test_secure_asset(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Secure Asset"}
    )
    await _to_shooting(client, game_id)
    await _action(client, game_id, d, "Secure Asset")
    await _end_turn(client, game_id)
    assert {"text": "A friendly unit secured the asset this turn", "points": 4} in (
        await _primary_scores(client, game_id, 2)
    )


async def test_extract_intelligence_waits_for_the_second_round(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _mission_game(
        client, session, tmp_path, monkeypatch, {2: "Gather Intel"}
    )
    await _to_shooting(client, game_id)
    options = (await client.get(f"/games/{game_id}/actions")).json()["options"]
    [option] = options[str(d["unit_id"])]
    assert option["reason"] == "it can't be done before battle round 2"
    await _advance_to(client, game_id, 2, 2, "shooting")
    await _action(client, game_id, d, "Extract Intelligence")
    await _end_turn(client, game_id)
    reasons = await _primary_scores(client, game_id, 2)
    assert {
        "text": "For each friendly unit that completed Extract Intelligence this turn (1)",
        "points": 7,
    } in reasons
    assert [m["source"] for m in (await _mission(client, game_id))["markers"]] == [
        "Extract Intelligence"
    ]
