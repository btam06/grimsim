from httpx import AsyncClient

from app.routers.games import _load_game
from app.services.in_game import turn_record
from tests.test_casualties import _game as _casualty_game
from tests.test_casualties import _gun
from tests.test_deployment import _unit_named
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place, _shoot, _to_shooting

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. The one
# objective is the Medium ruin's terrain area (x 7-13, y 8-12).


async def _record(client, game_id, **params):
    response = await client.get(f"/games/{game_id}/turn-record", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_destroyed_models_are_recorded(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D's 3 attacks (every die a 6) destroy both of A's models.
    units = {1: [("A", 2, {})], 2: [("D", *_gun(3))]}
    game, deployment = await _casualty_game(client, session, tmp_path, monkeypatch, units)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)

    record = await _record(client, game_id)
    assert (record["battle_round"], record["turn_seat"]) == (1, 2)
    first, second = record["destroyed"]
    for destroyed in (first, second):
        assert (destroyed["unit_name"], destroyed["seat"], destroyed["phase"]) == (
            "A", 1, "shooting"
        )
        assert destroyed["destroyed_by"] == "D"
    # The second was the last of A: A was destroyed.
    assert (first["unit_destroyed"], second["unit_destroyed"]) == (False, True)

    loaded = await _load_game(session, game_id)
    [unit] = turn_record.units_destroyed(loaded, 1, 2)
    assert unit.unit_id == a["unit_id"]
    assert turn_record.models_destroyed(loaded, 1, 1) == []


async def test_how_things_stood_at_the_start_of_a_turn(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 2, {})], 2: [("D", 2, {})]}
    game, deployment = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    # Seat 2's turn started with no one on the objective.
    [objective] = (await _record(client, game_id))["start"]
    assert (objective["kind"], objective["controller"], objective["unit_ids"]) == (
        "centre", None, []
    )

    # D moves onto it: seat 1's turn starts with seat 2 controlling it, and D
    # within range of it (and within its terrain area).
    await _place(session, d, [(9, 10), (11, 10)])
    await _advance_to(client, game_id, 1, 1, "command")
    [objective] = (await _record(client, game_id, battle_round=1, turn_seat=1))["start"]
    assert (objective["controller"], objective["unit_ids"]) == (2, [d["unit_id"]])
    loaded = await _load_game(session, game_id)
    assert d["unit_id"] in turn_record.started_in_areas(loaded, 1, 1)
    # The earlier turn's record is kept.
    [objective] = (await _record(client, game_id, battle_round=1, turn_seat=2))["start"]
    assert objective["controller"] is None


async def test_previous_turn(client: AsyncClient, session, tmp_path):
    # Seat 2 goes first.
    game, _ = await _battle(client, session, tmp_path)
    loaded = await _load_game(session, game["id"])
    assert turn_record.previous_turn(loaded, 1, 2) is None
    assert turn_record.previous_turn(loaded, 1, 1) == (1, 2)
    assert turn_record.previous_turn(loaded, 2, 2) == (1, 1)
