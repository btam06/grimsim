from httpx import AsyncClient

from app.models import Stratagem, StratagemTiming
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named
from tests.test_reinforcements import _advance_to

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Seat 2's D has
# a 36" gun, at (50, 8); seat 1's A (at (50, 33): within 24" of D) and B (at
# (20, 40): too far) have none - so only seat 2 can Fire Overwatch, at the
# end of seat 1's movement phase.


async def _fire_overwatch_stratagem(session):
    # The core Fire Overwatch stratagem (1CP, in the opponent's movement or
    # charge phase).
    stratagem = Stratagem(name="Fire Overwatch", cp=1, is_core=True)
    stratagem.timings = [
        StratagemTiming(phase="movement", turn="opponent_turn"),
        StratagemTiming(phase="charge", turn="opponent_turn"),
    ]
    session.add(stratagem)
    await session.commit()


async def _overwatch_game(client, session, tmp_path, stratagem=True):
    if stratagem:
        await _fire_overwatch_stratagem(session)
    units = {1: [("A", 1, {}), ("B", 1, {})], 2: [("D", 1, {"weapon_range": 36})]}
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, b, d = (_unit_named(deployment, n) for n in "ABD")
    for unit, (x, y) in ((a, (50, 33)), (d, (50, 8)), (b, (20, 40))):
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    return game_id, a, b, d


async def _overwatch(client, game_id):
    response = await client.get(f"/games/{game_id}/overwatch")
    assert response.status_code == 200, response.text
    return response.json()


async def _fire(client, game_id, unit, target, weapon_ids):
    return await client.post(
        f"/games/{game_id}/overwatch",
        json={
            "unit_id": unit["unit_id"],
            "target_unit_id": target["unit_id"],
            "weapon_ids": weapon_ids,
        },
    )


async def test_fire_overwatch_at_the_end_of_the_movement_phase(
    client: AsyncClient, session, tmp_path
):
    game_id, a, b, d = await _overwatch_game(client, session, tmp_path)
    # Seat 2's movement phase doesn't stop (seat 1 has no guns)...
    await _advance_to(client, game_id, 1, 2, "shooting")
    # ...but seat 1's does, for seat 2.
    await _advance_to(client, game_id, 1, 1, "movement", ended=True)
    overwatch = await _overwatch(client, game_id)
    assert (overwatch["seat"], overwatch["available"], overwatch["cp"]) == (2, True, 1)
    [unit] = overwatch["units"]
    assert (unit["name"], unit["can_shoot"]) == ("D", True)

    response = await client.get(
        f"/games/{game_id}/overwatch/targets", params={"unit_id": d["unit_id"]}
    )
    assert response.status_code == 200, response.text
    targets = {t["name"]: t for t in response.json()}
    # Only A is visible within 24".
    assert targets["A"]["visible"] and not targets["B"]["visible"]
    [gun] = targets["A"]["weapons"]

    response = await _fire(client, game_id, d, b, [gun["id"]])
    assert '24"' in response.json()["detail"]
    cp = next(p["cp"] for p in (await client.get(f"/games/{game_id}")).json()["players"]
              if p["seat"] == 2)
    response = await _fire(client, game_id, d, a, [gun["id"]])
    assert response.status_code == 200, response.text
    # One snap shot.
    assert len(response.json()["combat"]["attack_rolls"]) == 1
    game = (await client.get(f"/games/{game_id}")).json()
    assert next(p["cp"] for p in game["players"] if p["seat"] == 2) == cp - 1

    # Once per phase.
    overwatch = await _overwatch(client, game_id)
    assert not overwatch["available"]
    assert overwatch["units"][0]["shot"]["target_name"] == "A"
    response = await _fire(client, game_id, d, a, [gun["id"]])
    assert response.status_code == 400
    # On to seat 1's shooting phase.
    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["phase"] == "shooting"


async def test_no_overwatch_during_the_movement_phase(client: AsyncClient, session, tmp_path):
    game_id, a, _, d = await _overwatch_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 1, "movement")
    assert (await _overwatch(client, game_id))["seat"] is None
    response = await _fire(client, game_id, d, a, [])
    assert "end of the opponent's movement phase" in response.json()["detail"]


async def test_no_pause_without_the_stratagem(client: AsyncClient, session, tmp_path):
    game_id, *_ = await _overwatch_game(client, session, tmp_path, stratagem=False)
    await _advance_to(client, game_id, 1, 1, "movement")
    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["phase"] == "shooting"
