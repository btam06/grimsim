from httpx import AsyncClient
from sqlalchemy import select

from app.models import GameTerrainLayout, TerrainObjective
from tests.test_reinforcements import _advance_to
from tests.test_scoring import _end_turn, _game, _secondary
from tests.test_shooting import _place

# Games on the test layout ("Strips": seat 1 deploys along y 32-44, its
# territory y 22-44; seat 2 along y 0-12, and goes first). The one objective
# is the Medium ruin's area (x 7-13, y 8-12), central. Seat 1 has A (1
# model), seat 2 has D. Cards given to seat 1 prompt for their choices in
# its Command phase.


async def _mission(client, game_id):
    return (await client.get(f"/games/{game_id}/mission")).json()


async def _answer(client, game_id, prompt, ids=(), guards=None):
    response = await client.post(
        f"/games/{game_id}/mission/prompts/{prompt['id']}",
        json={"ids": list(ids), "guards": guards or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _offers(client, game_id):
    return (await client.get(f"/games/{game_id}/scoring")).json()["offers"]


async def _through_seat_2s_turn(client, game_id):
    # From seat 1's Command phase (round 1) to the end of seat 2's next turn
    # - answering any other choices on the way (seat 2 may draw these cards
    # too: they're in the deck).
    for _ in range(30):
        game = (await client.get(f"/games/{game_id}")).json()
        if (game["battle_round"], game["turn_seat"], game["phase"]) == (2, 2, "fight"):
            break
        for prompt in (await _mission(client, game_id))["prompts"]:
            first = [prompt["options"][0]["id"]] if prompt["kind"] != "guards" else []
            await _answer(client, game_id, prompt, first)
        await client.post(f"/games/{game_id}/advance")
    await _end_turn(client, game_id)


async def test_beacon(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 1, "Beacon", points=3)
    await _advance_to(client, game_id, 1, 1, "command")
    [prompt] = (await _mission(client, game_id))["prompts"]
    assert (prompt["kind"], prompt["seat"], [o["label"] for o in prompt["options"]]) == (
        "beacon", 1, ["A"]
    )
    response = await client.post(f"/games/{game_id}/advance")
    assert "missions' choices" in response.json()["detail"]
    await _answer(client, game_id, prompt, [a["unit_id"]])

    # A out of seat 1's territory at the end of seat 2's turn: 5VP.
    await _place(session, a, [(20, 20)])
    await _through_seat_2s_turn(client, game_id)
    [offer] = await _offers(client, game_id)
    assert (offer["name"], offer["seat"], offer["points"]) == ("Beacon", 1, 5)


async def test_tempting_target_is_chosen_by_the_opponent(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    # The objective's marker in No Man's Land.
    link = (
        await session.execute(select(GameTerrainLayout).where(GameTerrainLayout.game_id == game_id))
    ).scalar_one()
    objective = (
        await session.execute(
            select(TerrainObjective).where(TerrainObjective.layout_id == link.layout_id)
        )
    ).scalar_one()
    objective.y = 20
    await session.commit()
    await _secondary(session, game_id, 1, "A Tempting Target", points=5)
    await _advance_to(client, game_id, 1, 1, "command")
    [prompt] = (await _mission(client, game_id))["prompts"]
    assert (prompt["kind"], prompt["seat"]) == ("tempting_target", 2)
    [option] = prompt["options"]
    await _answer(client, game_id, prompt, [option["id"]])

    # Seat 1 controls it at the end of its turn: 5VP.
    await _place(session, a, [(10, 10)])
    await _end_turn(client, game_id)
    [offer] = await _offers(client, game_id)
    assert (offer["name"], offer["points"]) == ("A Tempting Target", 5)


async def test_burden_of_trust(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _game(client, session, tmp_path, monkeypatch)
    await _secondary(session, game_id, 1, "Burden of Trust", points=2)
    await _advance_to(client, game_id, 1, 1, "command")
    [prompt] = (await _mission(client, game_id))["prompts"]
    assert (prompt["kind"], [u["label"] for u in prompt["units"]]) == ("guards", ["A"])
    [objective] = prompt["options"]
    await _answer(client, game_id, prompt, guards={objective["id"]: a["unit_id"]})

    # A guards it (within range, and seat 1 controls it) at the end of seat
    # 2's turn: 2VP.
    await _place(session, a, [(10, 10)])
    await _through_seat_2s_turn(client, game_id)
    [offer] = await _offers(client, game_id)
    assert (offer["name"], offer["points"]) == ("Burden of Trust", 2)

    # Held: at the start of seat 1's next turn, it picks guards again.
    await client.post(f"/games/{game_id}/scoring/offers/{offer['id']}/hold")
    await client.post(f"/games/{game_id}/advance")
    [prompt] = (await _mission(client, game_id))["prompts"]
    assert (prompt["kind"], prompt["seat"]) == ("guards", 1)
