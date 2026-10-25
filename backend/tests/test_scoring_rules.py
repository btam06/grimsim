from httpx import AsyncClient
from sqlalchemy import update

from app.models import SecondaryMission
from app.routers.games import _load_game
from app.services.in_game import game as game_service
from app.services.in_game import mission_state
from tests.test_deployment import (
    _declare,
    _deploy,
    _deployment,
    _game as _formation_game,
    _row,
    _set,
    _unit_named,
)
from tests.test_reinforcements import _advance_to, _reserves_game
from tests.test_scoring import _end_turn, _game, _primary, _scores, _secondary
from tests.test_shooting import _place, _shoot, _to_shooting

# Games on the test layout ("Strips": seat 1 deploys along y 32-44, seat 2
# along y 0-12, and goes first). The one objective is the Medium ruin's area
# (x 7-13, y 8-12). In the scoring games, seat 1 has A (1 model), seat 2 has
# D (2 models with 24" guns); every die rolls a 6.


# --- VP caps ---


async def test_primary_vp_is_capped_at_15_a_battle_round(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    url = f"/games/{game_id}/primary-score"
    for points in (10, 10):
        assert (await client.post(url, json={"seat": 2, "points": points})).status_code == 200
    assert [s["points"] for s in await _scores(client, game_id, 2)] == [10, 5]
    response = await client.post(url, json={"seat": 2, "points": 1})
    assert "15VP" in response.json()["detail"]


# --- what counts as a kill ---


async def test_reserves_destroyed_off_the_table_arent_kills(
    client: AsyncClient, session, tmp_path
):
    game_id, r = await _reserves_game(client, session, tmp_path, rapid_ingress=False)
    await _advance_to(client, game_id, 4, 2, "command")
    deployment = await _deployment(client, game_id)
    assert _unit_named(deployment, "R")["formation"] == "destroyed"
    game = await _load_game(session, game_id)
    assert game.models_destroyed == []


async def test_purge_and_secure_looks_at_where_the_killer_was(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _primary(session, game_id, 2, "Purge and Secure")
    # D shoots A from the objective - then leaves it before the turn ends.
    await _place(session, d, [(9, 10), (11, 10)])
    await _place(session, a, [(20, 24)])
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    await _place(session, d, [(20, 4), (21.5, 4)])
    await _end_turn(client, game_id)
    reasons = [r["text"] for s in await _scores(client, game_id, 2) for r in s["reasons"]]
    assert (
        "One or more enemy units were destroyed this turn by a friendly unit within range of "
        "one or more objectives"
    ) in reasons


# --- redraws ---


async def _drawn(session, game_id, seat, card_id):
    # As if the player had just drawn that card.
    game = await _load_game(session, game_id)
    card = next(c for p in game.players for c in p.secondaries if c.id == card_id)
    mission_state.cards_drawn(game, seat, [card])
    await session.commit()


async def _card_status(client, game_id, seat, card_id):
    game = (await client.get(f"/games/{game_id}")).json()
    player = next(p for p in game["players"] if p["seat"] == seat)
    return next(c["status"] for c in player["secondaries"] if c["id"] == card_id)


async def test_a_grievous_blow_can_be_discarded_with_nothing_to_target(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    card_id = await _secondary(session, game_id, 2, "A Grievous Blow", points=5)
    await _drawn(session, game_id, 2, card_id)
    [prompt] = (await client.get(f"/games/{game_id}/mission")).json()["prompts"]
    [option] = prompt["options"]
    assert (prompt["kind"], option["id"]) == ("redraw", card_id)
    assert "discard it" in option["label"]
    game = (await client.get(f"/games/{game_id}")).json()
    held = len(next(p for p in game["players"] if p["seat"] == 2)["secondaries"])
    response = await client.post(
        f"/games/{game_id}/mission/prompts/{prompt['id']}", json={"ids": [card_id]}
    )
    assert response.status_code == 200, response.text
    assert await _card_status(client, game_id, 2, card_id) == "discarded"
    game = (await client.get(f"/games/{game_id}")).json()
    assert len(next(p for p in game["players"] if p["seat"] == 2)["secondaries"]) == held + 1


async def test_behind_enemy_lines_can_be_shuffled_back_in_the_first_round(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    card_id = await _secondary(session, game_id, 2, "Behind Enemy Lines", points=3)
    await _drawn(session, game_id, 2, card_id)
    [prompt] = (await client.get(f"/games/{game_id}/mission")).json()["prompts"]
    assert "shuffle it back" in prompt["options"][0]["label"]
    # Kept, this time.
    response = await client.post(f"/games/{game_id}/mission/prompts/{prompt['id']}", json={})
    assert response.status_code == 200, response.text
    assert await _card_status(client, game_id, 2, card_id) == "active"


async def test_defend_stronghold_is_replaced_in_the_first_round(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    # A deck of just Defend Stronghold, then Spare.
    await session.execute(update(SecondaryMission).values(tactical_points=None))
    for name in ("Defend Stronghold", "Spare"):
        session.add(SecondaryMission(name=name, completes_on="either", tactical_points=3))
    await session.commit()
    monkeypatch.setattr(game_service.random, "randrange", lambda n: 0)
    game = await _load_game(session, game_id)
    player = next(p for p in game.players if p.seat == 2)
    drawn = await game_service._draw_tactical(session, game, player, count=1)
    assert [c.mission.name for c in drawn] == ["Spare"]
    stronghold = next(c for c in player.secondaries if c.mission.name == "Defend Stronghold")
    assert stronghold.status == game_service.SHUFFLED


# --- embarked units ---


async def _transport_game(client, session, tmp_path):
    # Seat 1's P starts embarked in its transport T (at (20, 38)); seat 2's
    # D at (20, 4).
    units = {
        1: [("T", 1, {"keywords": ("TRANSPORT",)}), ("P", 2, {})],
        2: [("D", 1, {})],
    }
    game = await _formation_game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    t, p, d = (_unit_named(deployment, n) for n in "TPD")
    response = await _set(client, game_id, 1, p, "embarked", t)
    assert response.status_code == 200, response.text
    for seat in (1, 2):
        await _declare(client, game_id, seat)
    for unit, spot in ((t, (20, 38)), (d, (20, 4))):
        response = await _deploy(client, game_id, unit, _row(unit, *spot))
        assert response.status_code == 200, response.text
    return game_id, t, p


def _at(unit, spots):
    return [
        {"unit_model_id": m["unit_model_id"], "x": x, "y": y}
        for m, (x, y) in zip(unit["models"], spots)
    ]


async def test_disembarking(client: AsyncClient, session, tmp_path):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    [unit] = (await client.get(f"/games/{game_id}/embarked")).json()["units"]
    assert (unit["name"], unit["transport_name"]) == ("P", "T")

    url = f"/games/{game_id}/embarked"
    payload = {"unit_id": p["unit_id"], "positions": _at(p, [(30, 38), (31.5, 38)])}
    check = (await client.post(f"{url}/check", json=payload)).json()
    assert 'P isn\'t wholly within 3" of its transport (x2)' in check["problems"]
    payload = {"unit_id": p["unit_id"], "positions": _at(p, [(21.5, 38), (21.5, 39.5)])}
    assert (await client.post(f"{url}/check", json=payload)).json()["valid"]
    response = await client.post(url, json=payload)
    assert response.status_code == 200, response.text
    assert (await client.get(url)).json()["units"] == []
    # Its transport hadn't moved: it can still move.
    response = await client.post(
        f"/games/{game_id}/movement",
        json={
            "unit_id": p["unit_id"], "kind": "normal", "positions": _at(p, [(23, 37), (23, 35.5)])
        },
    )
    assert response.status_code == 200, response.text


async def test_disembarking_after_the_transport_moved(client: AsyncClient, session, tmp_path):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    response = await client.post(
        f"/games/{game_id}/movement",
        json={"unit_id": t["unit_id"], "kind": "normal", "positions": _at(t, [(25, 38)])},
    )
    assert response.status_code == 200, response.text
    payload = {"unit_id": p["unit_id"], "positions": _at(p, [(26.5, 38), (26.5, 39.5)])}
    response = await client.post(f"/games/{game_id}/embarked", json=payload)
    assert response.status_code == 200, response.text
    response = await client.post(
        f"/games/{game_id}/movement",
        json={
            "unit_id": p["unit_id"], "kind": "normal", "positions": _at(p, [(28, 38), (28, 39.5)])
        },
    )
    assert "disembarked" in response.json()["detail"]


async def test_an_embarked_unit_can_be_a_beacon(client: AsyncClient, session, tmp_path):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    assert p["unit_id"] in {u.id for u in mission_state.beacon_candidates(game, 1)}
