from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import FactionAbility, Model, UnitModel
from tests import live_games
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named
from tests.test_reinforcements import _advance_to

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Seat 1's N (3
# models of 2 wounds, from (20, 38)) has Reanimation Protocols; seat 2's D is
# at (20, 4).


async def _necrons(session, unit):
    # Gives the unit's models (they share one Model) Reanimation Protocols.
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    model = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.faction_abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    model.faction_abilities.append(
        FactionAbility(name="Reanimation Protocols", faction_id=model.faction_id)
    )
    await session.commit()


async def _reanimation_game(client, session, tmp_path, monkeypatch, roll):
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: roll)
    units = {1: [("N", 3, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    n, d = _unit_named(deployment, "N"), _unit_named(deployment, "D")
    await _necrons(session, n)
    for unit, (x, y) in ((n, (20, 38)), (d, (20, 4))):
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    return game_id, n


async def _hurt(session, game_id, unit_model_id, wounds_lost, destroyed=False):
    live_games.damage(game_id, unit_model_id, wounds_lost, destroyed)
    if destroyed:
        live_games.remove_position(unit_model_id, game_id)


def _model(deployment, unit_model_id):
    unit = _unit_named(deployment, "N")
    return next(m for m in unit["models"] if m["unit_model_id"] == unit_model_id)


async def test_reanimation_heals_then_returns_a_model_to_set_up(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, n = await _reanimation_game(client, session, tmp_path, monkeypatch, roll=2)
    first, second, _ = (m["unit_model_id"] for m in n["models"])
    await _hurt(session, game_id, first, 2, destroyed=True)
    await _hurt(session, game_id, second, 1)

    # Seat 2's command phase: nothing of theirs reanimates.
    await _advance_to(client, game_id, 1, 2, "movement")
    await _advance_to(client, game_id, 1, 1, "command")
    response = await client.post(f"/games/{game_id}/advance")
    # The end of seat 1's command phase: the wounded model heals its wound,
    # then the destroyed one returns - to be set up.
    assert response.json()["phase"] == "command"
    state = (await client.get(f"/games/{game_id}/reanimation")).json()
    assert state["placing"] and state["seat"] == 1
    [unit] = state["units"]
    assert (unit["name"], unit["roll"], unit["healed"], unit["returned"]) == ("N", 2, 1, 1)
    [start] = unit["to_place"]
    assert start["unit_model_id"] == first
    response = await client.post(f"/games/{game_id}/advance")
    assert "set up the returned models first" in response.json()["detail"]

    # Not in Engagement Range of D, and in coherency.
    payload = {"unit_id": n["unit_id"], "positions": [{**start, "x": 21, "y": 6.5}]}
    check = (await client.post(f"/games/{game_id}/reanimation/check", json=payload)).json()
    assert "N is within Engagement Range of an enemy model" in check["problems"]
    assert any("isn't within 2\"" in p for p in check["problems"])
    # Where it was suggested is fine.
    payload = {"unit_id": n["unit_id"], "positions": [start]}
    check = (await client.post(f"/games/{game_id}/reanimation/check", json=payload)).json()
    assert check["valid"], check
    response = await client.post(f"/games/{game_id}/reanimation", json=payload)
    assert response.status_code == 200, response.text

    deployment = await _deployment(client, game_id)
    assert _model(deployment, first)["position"] is not None
    assert _model(deployment, first)["wounds_remaining"] == 1
    assert _model(deployment, second)["wounds_remaining"] == 2
    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["phase"] == "movement"


async def test_reanimation_without_destroyed_models_moves_on(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, n = await _reanimation_game(client, session, tmp_path, monkeypatch, roll=3)
    second = n["models"][1]["unit_model_id"]
    await _hurt(session, game_id, second, 1)
    await _advance_to(client, game_id, 1, 1, "command")
    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["phase"] == "movement"
    deployment = await _deployment(client, game_id)
    assert _model(deployment, second)["wounds_remaining"] == 2


async def test_only_the_turn_player_sets_up_reanimated_models(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, n = await _reanimation_game(client, session, tmp_path, monkeypatch, roll=1)
    first = n["models"][0]["unit_model_id"]
    await _hurt(session, game_id, first, 2, destroyed=True)
    # Not in seat 2's turn (nor before the end of seat 1's command phase).
    await _advance_to(client, game_id, 1, 2, "movement")
    payload = {"unit_id": n["unit_id"], "positions": [{"unit_model_id": first, "x": 25, "y": 38}]}
    response = await client.post(f"/games/{game_id}/reanimation", json=payload)
    assert "no returned models" in response.json()["detail"]


async def test_left_over_wounds_spill_into_another_model(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Two destroyed 2-wound models and a roll of 3: both return (not one
    # returned and healed), and the last wound heals the first of them.
    game_id, n = await _reanimation_game(client, session, tmp_path, monkeypatch, roll=3)
    first, second, _ = (m["unit_model_id"] for m in n["models"])
    await _hurt(session, game_id, first, 2, destroyed=True)
    await _hurt(session, game_id, second, 2, destroyed=True)
    await _advance_to(client, game_id, 1, 1, "command")
    # At 1 of 3 models it takes a Battle-shock test first (the Battle-shock
    # step comes before the end of the Command phase).
    for test in (await client.get(f"/games/{game_id}/battle-shock")).json()["pending"]:
        await client.post(
            f"/games/{game_id}/battle-shock/{test['id']}/take", json={"insane_bravery": False}
        )
    await client.post(f"/games/{game_id}/advance")
    [unit] = (await client.get(f"/games/{game_id}/reanimation")).json()["units"]
    assert (unit["healed"], unit["returned"]) == (1, 2)
    payload = {"unit_id": n["unit_id"], "positions": unit["to_place"]}
    response = await client.post(f"/games/{game_id}/reanimation", json=payload)
    assert response.status_code == 200, response.text
    deployment = await _deployment(client, game_id)
    assert [_model(deployment, i)["wounds_remaining"] for i in (first, second)] == [2, 1]


async def test_resurrection_orb_at_the_end_of_a_phase(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Seat 1's N has a Resurrection Orb: in seat 2's Shooting phase, with a
    # model destroyed and one wounded, seat 1 declares it - and as the phase
    # ends, N heals D6 (a 2): the wound, then the destroyed model returns, for
    # seat 1 to set up before the Charge phase.
    from tests.test_admech_characters import _give

    game_id, n = await _reanimation_game(client, session, tmp_path, monkeypatch, roll=2)
    await _give(session, n, "Resurrection Orb")
    first, second, _ = (m["unit_model_id"] for m in n["models"])
    await _advance_to(client, game_id, 1, 2, "shooting")
    await _hurt(session, game_id, first, 2, destroyed=True)
    await _hurt(session, game_id, second, 1)
    state = (await client.get(f"/games/{game_id}/resurrection")).json()
    assert [(u["name"], u["seat"], u["declared"]) for u in state["units"]] == [("N", 1, False)]
    response = await client.post(
        f"/games/{game_id}/resurrection", json={"seat": 1, "unit_id": n["unit_id"]}
    )
    assert response.status_code == 200, response.text
    # Declared, not yet resolved.
    deployment = await _deployment(client, game_id)
    assert _model(deployment, second)["wounds_remaining"] == 1

    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["phase"] == "shooting"
    state = (await client.get(f"/games/{game_id}/reanimation")).json()
    assert state["placing"] and state["seat"] == 1
    [unit] = state["units"]
    assert (unit["roll"], unit["healed"], unit["returned"]) == (2, 1, 1)
    response = await client.post(f"/games/{game_id}/advance")
    assert "set up the returned models first" in response.json()["detail"]
    payload = {"unit_id": n["unit_id"], "positions": unit["to_place"]}
    response = await client.post(f"/games/{game_id}/reanimation", json=payload)
    assert response.status_code == 200, response.text
    assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == "charge"
    # Once a battle.
    response = await client.post(
        f"/games/{game_id}/resurrection", json={"seat": 1, "unit_id": n["unit_id"]}
    )
    assert "once a battle" in response.json()["detail"]
    assert (await client.get(f"/games/{game_id}/resurrection")).json()["units"] == []
