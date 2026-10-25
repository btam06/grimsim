from httpx import AsyncClient
from sqlalchemy import select

from app.models import GamePlayer, GameSecondary, PrimaryMission, SecondaryMission
from tests.test_casualties import _game as _casualty_game
from tests.test_casualties import _gun
from tests.test_deployment import _unit_named
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place, _shoot, _to_shooting

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Every die
# rolls a 6: seat 2's D (a 24" gun per model) destroys what it shoots. The
# one objective is the Medium ruin's area (x 7-13, y 8-12), a central one.


async def _player(session, game_id, seat) -> GamePlayer:
    return (
        await session.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id, GamePlayer.seat == seat)
        )
    ).scalar_one()


async def _primary(session, game_id, seat, name):
    # The player's primary mission becomes the card `name`.
    player = await _player(session, game_id, seat)
    mission = await session.get(PrimaryMission, player.primary_mission_id)
    mission.name = name
    await session.commit()


async def _secondary(session, game_id, seat, name, fixed=False, points=2) -> int:
    # Gives the player the secondary `name` (fixed or tactical).
    mission = (
        await session.execute(select(SecondaryMission).where(SecondaryMission.name == name))
    ).scalar_one_or_none()
    if mission is None:
        mission = SecondaryMission(
            name=name,
            completes_on="either",
            fixed_points=points if fixed else None,
            tactical_points=points,
        )
        session.add(mission)
        await session.flush()
    player = await _player(session, game_id, seat)
    card = GameSecondary(
        game_player_id=player.id,
        secondary_mission_id=mission.id,
        status="active",
        fixed=fixed,
        drawn_round=1,
    )
    session.add(card)
    await session.commit()
    return card.id


async def _game(client, session, tmp_path, monkeypatch, a_keywords=()):
    units = {1: [("A", 1, {"keywords": a_keywords})], 2: [("D", *_gun(2))]}
    game, deployment = await _casualty_game(client, session, tmp_path, monkeypatch, units)
    return game["id"], _unit_named(deployment, "A"), _unit_named(deployment, "D")


async def _scores(client, game_id, seat):
    game = (await client.get(f"/games/{game_id}")).json()
    return next(p for p in game["players"] if p["seat"] == seat)["scores"]


async def _end_turn(client, game_id):
    # On to the end of the current turn (the fight phase), then past it.
    for _ in range(6):
        game = (await client.get(f"/games/{game_id}")).json()
        response = await client.post(f"/games/{game_id}/advance")
        if game["phase"] == "fight":
            return response
    raise AssertionError("never got to the fight phase")


async def test_primary_scores_at_the_end_of_the_turn(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _primary(session, game_id, 2, "Destroyer's Wrath")
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    response = await _end_turn(client, game_id)
    assert response.status_code == 200, response.text

    [score] = await _scores(client, game_id, 2)
    assert (score["kind"], score["points"], score["battle_round"], score["turn_seat"]) == (
        "primary", 3, 1, 2
    )
    assert score["reasons"] == [
        {"text": "One or more enemy units were destroyed this turn", "points": 3}
    ]


async def test_primary_control_line_at_the_end_of_the_command_phase(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _primary(session, game_id, 2, "Destroyer's Wrath")
    await _place(session, d, [(9, 10), (11, 10)])
    # Not in the first battle round.
    await _advance_to(client, game_id, 2, 2, "command")
    assert all(s["battle_round"] == 1 for s in await _scores(client, game_id, 2))
    await client.post(f"/games/{game_id}/advance")
    [score] = [s for s in await _scores(client, game_id, 2) if s["battle_round"] == 2]
    # D on the central objective; A on none: 4 + 6.
    assert score["points"] == 10
    assert {r["text"] for r in score["reasons"]} == {
        "You control one or more objectives (excluding your home objective)",
        "You control more objectives than your opponent",
    }


async def test_tactical_secondaries_are_claimed_or_held(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    card_id = await _secondary(session, game_id, 2, "No Prisoners")
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    await _end_turn(client, game_id)

    # Completed: offered to claim, and the game waits.
    [offer] = (await client.get(f"/games/{game_id}/scoring")).json()["offers"]
    assert (offer["name"], offer["seat"], offer["points"]) == ("No Prisoners", 2, 2)
    response = await client.post(f"/games/{game_id}/advance")
    assert "claim or hold" in response.json()["detail"]

    # Held: not scored, and the card's still in hand.
    game = (await client.post(f"/games/{game_id}/scoring/offers/{offer['id']}/hold")).json()
    player = next(p for p in game["players"] if p["seat"] == 2)
    assert next(c for c in player["secondaries"] if c["id"] == card_id)["status"] == "active"
    assert [s for s in player["scores"] if s["kind"] == "secondary"] == []
    # Checked again at the next turn's end: nothing destroyed then.
    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["turn_seat"] == 1
    await _end_turn(client, game_id)
    assert (await client.get(f"/games/{game_id}/scoring")).json()["offers"] == []


async def test_claiming_scores_it_and_finishes_the_card(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    card_id = await _secondary(session, game_id, 2, "No Prisoners")
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    await _end_turn(client, game_id)
    [offer] = (await client.get(f"/games/{game_id}/scoring")).json()["offers"]
    game = (await client.post(f"/games/{game_id}/scoring/offers/{offer['id']}/claim")).json()
    player = next(p for p in game["players"] if p["seat"] == 2)
    assert next(c for c in player["secondaries"] if c["id"] == card_id)["status"] == "achieved"
    [score] = [s for s in player["scores"] if s["kind"] == "secondary"]
    assert (score["points"], score["game_secondary_id"]) == (2, card_id)
    # And it can't be scored by hand.
    response = await client.post(f"/games/{game_id}/secondaries/{card_id}/achieve")
    assert response.status_code == 400


async def test_fixed_secondaries_score_by_themselves(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # A is a CHARACTER: Assassination (fixed) scores 3 when it's destroyed.
    game_id, a, d = await _game(
        client, session, tmp_path, monkeypatch, a_keywords=("CHARACTER",)
    )
    card_id = await _secondary(session, game_id, 2, "Assassination", fixed=True, points=3)
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    await _end_turn(client, game_id)
    assert (await client.get(f"/games/{game_id}/scoring")).json()["offers"] == []
    [score] = [s for s in await _scores(client, game_id, 2) if s["kind"] == "secondary"]
    assert (score["points"], score["game_secondary_id"]) == (3, card_id)
    response = await client.post(f"/games/{game_id}/secondaries/{card_id}/achieve")
    assert "scored automatically" in response.json()["detail"]


async def test_a_game_with_scored_secondaries_can_be_deleted(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 2, "No Prisoners")
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    await _end_turn(client, game_id)
    [offer] = (await client.get(f"/games/{game_id}/scoring")).json()["offers"]
    await client.post(f"/games/{game_id}/scoring/offers/{offer['id']}/claim")
    assert (await client.delete(f"/games/{game_id}")).status_code == 204
    assert (await client.get(f"/games/{game_id}")).status_code == 404
