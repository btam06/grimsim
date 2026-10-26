from httpx import AsyncClient

from app.models import DatasheetAbility
from app.services.in_game import first_turn
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named
from tests.test_space_marine_units import _model_of

# A game on the test layout where who goes first isn't decided: seat 1 (the
# attacker, deploying along y 32-44) has A and S (with Scouts 6"), seat 2 has
# D (along y 0-12).


async def _rolled_off_game(client, session, tmp_path, rolls):
    units = {1: [("A", 1, {}), ("S", 1, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units, first=None)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    a, s, d = (_unit_named(deployment_, n) for n in "ASD")
    model = await _model_of(session, s)
    model.abilities.append(DatasheetAbility(name='Scouts 6"', description="Scouts"))
    await session.commit()
    for unit, spot in ((a, (20, 40)), (d, (20, 4)), (s, (40, 40))):
        response = await _deploy(client, game_id, unit, _row(unit, *spot))
        assert response.status_code == 200, response.text
    return game_id, s


async def test_roll_off_then_scouts_moves_at_the_start_of_the_first_round(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    rolls = iter([3, 3, 2, 5])
    monkeypatch.setattr(first_turn.random, "randint", lambda a, b: next(rolls))
    game_id, s = await _rolled_off_game(client, session, tmp_path, rolls)
    game = (await client.get(f"/games/{game_id}")).json()
    # Everything's set up: the roll-off is next.
    assert (game["status"], game["deployment_step"], game["first_seat"]) == (
        "deployment", "first_turn", None
    )
    response = await client.post(f"/games/{game_id}/first-turn/roll")
    assert response.status_code == 200, response.text
    game = response.json()
    # A tie, re-rolled: seat 2's 5 beats seat 1's 2.
    assert [(r["attempt"], r["seat"], r["roll"]) for r in game["first_turn_rolls"]] == [
        (1, 1, 3), (1, 2, 3), (2, 1, 2), (2, 2, 5),
    ]
    assert game["first_seat"] == 2
    response = await client.post(f"/games/{game_id}/first-turn/roll")
    assert response.status_code == 400

    # The battle: its first round starts with Scouts moves - seat 2 has no
    # Scouts units, so seat 1 makes its.
    assert (game["status"], game["battle_round"], game["phase"]) == (
        "in_progress", 1, "start_of_round"
    )
    assert game["scouting_seat"] == 1
    response = await client.post(f"/games/{game_id}/advance")
    assert "Scouts moves first" in response.json()["detail"]
    scouts = (await client.get(f"/games/{game_id}/scouts")).json()
    assert [(u["unit_id"], u["distance"]) for u in scouts["units"]] == [(s["unit_id"], 6)]
    model = s["models"][0]["unit_model_id"]
    too_far = [{"unit_model_id": model, "x": 40, "y": 33}]
    response = await client.post(
        f"/games/{game_id}/scouts", json={"unit_id": s["unit_id"], "positions": too_far}
    )
    assert response.status_code == 400
    near = [{"unit_model_id": model, "x": 40, "y": 35}]
    response = await client.post(
        f"/games/{game_id}/scouts", json={"unit_id": s["unit_id"], "positions": near}
    )
    assert response.status_code == 200, response.text
    assert response.json()["units"][0]["moved"]

    response = await client.post(f"/games/{game_id}/scouts/done", json={"seat": 1})
    assert response.status_code == 200, response.text
    assert response.json()["scouting_seat"] is None
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert (game["phase"], game["turn_seat"]) == ("command", 2)


async def test_a_unit_without_scouts_on_every_model_cant_scout(
    client: AsyncClient, session, tmp_path
):
    from app.routers.games import _load_game
    from app.services.in_game import deployment, scouts

    game_id, s = await _rolled_off_game(client, session, tmp_path, None)
    game = await _load_game(session, game_id)
    assert scouts.distance(deployment.find_unit(game, s["unit_id"])) == 6
    a = next(u for u in deployment.deployable_units(game.players[0]) if u.id != s["unit_id"])
    assert scouts.distance(a) == 0


async def test_scouts_from_wargear_after_the_roll_off(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # A unit whose wargear gives it Scouts (e.g. an Orbital Comms Array) - its
    # abilities have to be loaded with the game.
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import UnitModel, Wargear, WargearAbility

    rolls = iter([2, 5])
    monkeypatch.setattr(first_turn.random, "randint", lambda a, b: next(rolls))
    units = {1: [("A", 1, {}), ("O", 1, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units, first=None)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    a, o, d = (_unit_named(deployment_, n) for n in "AOD")
    unit_model = (
        await session.execute(
            select(UnitModel)
            .options(selectinload(UnitModel.wargear))
            .where(UnitModel.id == o["models"][0]["unit_model_id"])
        )
    ).scalar_one()
    gear = Wargear(name="Orbital Comms Array", model_id=unit_model.model_id)
    gear.abilities = [WargearAbility(name='Scouts 6"', description="Scouts")]
    unit_model.wargear.append(gear)
    await session.commit()
    for unit, spot in ((a, (20, 40)), (d, (20, 4)), (o, (40, 40))):
        response = await _deploy(client, game_id, unit, _row(unit, *spot))
        assert response.status_code == 200, response.text
    session.expire_all()
    response = await client.post(f"/games/{game_id}/first-turn/roll")
    assert response.status_code == 200, response.text
    # Seat 2 rolled higher and goes first, but only seat 1 has Scouts.
    assert response.json()["scouting_seat"] == 1
    scouts = (await client.get(f"/games/{game_id}/scouts")).json()
    assert [(u["unit_id"], u["distance"]) for u in scouts["units"]] == [(o["unit_id"], 6)]
