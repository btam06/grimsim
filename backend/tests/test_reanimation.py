from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.models import FactionAbility, GameModelDamage, GameModelPosition, Model, UnitModel
from app.services.in_game import reanimation
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
    monkeypatch.setattr(reanimation.random, "randint", lambda a, b: roll)
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
    session.add(
        GameModelDamage(
            game_id=game_id,
            unit_model_id=unit_model_id,
            wounds_lost=wounds_lost,
            destroyed=destroyed,
        )
    )
    if destroyed:
        await session.execute(
            delete(GameModelPosition).where(
                GameModelPosition.game_id == game_id,
                GameModelPosition.unit_model_id == unit_model_id,
            )
        )
    await session.commit()


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
    assert "set up the reanimated models first" in response.json()["detail"]

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
    assert "no reanimated models" in response.json()["detail"]


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
    await client.post(f"/games/{game_id}/advance")
    [unit] = (await client.get(f"/games/{game_id}/reanimation")).json()["units"]
    assert (unit["healed"], unit["returned"]) == (1, 2)
    payload = {"unit_id": n["unit_id"], "positions": unit["to_place"]}
    response = await client.post(f"/games/{game_id}/reanimation", json=payload)
    assert response.status_code == 200, response.text
    deployment = await _deployment(client, game_id)
    assert [_model(deployment, i)["wounds_remaining"] for i in (first, second)] == [2, 1]
