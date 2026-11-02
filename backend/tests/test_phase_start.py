from httpx import AsyncClient

from app.engine import store
from app.routers.games import _load_game, _model_rules
from app.services.in_game import deployment, phase_start
from tests.test_command_phase import _give
from tests.test_deployment import _unit_named
from tests.test_shooting import _place, _shoot, _shooting_game, _to_shooting

# Abilities for the start of an opponent's phase (see
# app/services/in_game/phase_start.py) - Defend the Divine Work: at the start
# of the opponent's Shooting or Fight phase, once a battle, its unit has a
# 4+ invulnerable save until the end of the phase. Seat 2 (D) goes first;
# seat 1's A has the ability.


async def _phase_start(client, game_id):
    return (await client.get(f"/games/{game_id}/phase-start")).json()


async def _defend_game(client, session, tmp_path):
    game, deployment_ = await _shooting_game(client, session, tmp_path, d=1, a=1)
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _give(session, a, ["Defend the Divine Work"])
    await _place(session, a, [(20, 22)])
    return game_id, d, a


async def test_defend_the_divine_work_at_the_start_of_the_opponents_shooting(
    client: AsyncClient, session, tmp_path
):
    game_id, d, a = await _defend_game(client, session, tmp_path)
    assert (await _phase_start(client, game_id))["seat"] is None  # (their movement phase)
    await _to_shooting(client, game_id)
    # The game waits on seat 1: seat 2 can't shoot, nor move on.
    state = await _phase_start(client, game_id)
    assert (state["seat"], state["phase"]) == (1, "shooting")
    assert [(x["unit_name"], x["ability"]) for x in state["abilities"]] == [
        ("A", "Defend the Divine Work")
    ]
    response = await client.get(f"/games/{game_id}/shooting/targets?unit_id={d['unit_id']}")
    assert "waiting for player 1" in response.json()["detail"]
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 400
    # Seat 1 uses it: A's models have a 4+ invulnerable save this phase.
    response = await client.post(
        f"/games/{game_id}/phase-start",
        json={"seat": 1, "unit_id": a["unit_id"], "ability": "Defend the Divine Work"},
    )
    assert response.status_code == 200, response.text
    assert (await _phase_start(client, game_id))["seat"] is None
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, a["unit_id"])
    assert _model_rules(game, unit)
    response = await _shoot(client, game_id, d, a)
    assert response.status_code == 200, response.text
    # Gone at the end of the phase - and once a battle: not again at the
    # start of seat 2's Fight phase.
    assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == "charge"
    game = await _load_game(session, game_id)
    assert not _model_rules(game, deployment.find_unit(game, a["unit_id"]))
    assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == "fight"
    assert (await _phase_start(client, game_id))["seat"] is None


async def test_its_player_can_wait_for_the_fight_phase(client: AsyncClient, session, tmp_path):
    game_id, d, a = await _defend_game(client, session, tmp_path)
    await _to_shooting(client, game_id)
    response = await client.post(f"/games/{game_id}/phase-start/done", json={"seat": 1})
    assert response.status_code == 200, response.text
    assert (await _shoot(client, game_id, d, a)).status_code == 200
    for phase in ("charge", "fight"):
        assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == phase
    # Not used yet: offered again at the start of the Fight phase.
    assert (await _phase_start(client, game_id))["seat"] == 1
    decision = (await client.get(f"/games/{game_id}/agent")).json()
    assert decision["waiting_for"]["seat"] == 1
    assert {a["type"] for a in decision["actions"] if a["seat"] == 1} >= {
        "phase_start_ability", "finish_phase_start"
    }
    use = next(a for a in decision["actions"] if a["type"] == "phase_start_ability")
    response = await client.post(
        f"/games/{game_id}/agent/apply",
        json={"action": {"type": use["type"], "seat": 1, "params": use["params"]}},
    )
    assert response.json()["log"]["ok"], response.text
    live = store.get(game_id)
    assert not phase_start.waiting(live.game)
