from httpx import AsyncClient

from app.engine import saves
from app.engine import store as game_store
from app.models.model import TransportCapacity
from app.routers.games import _load_game
from app.services.in_game import deployment, unit_splits
from tests import live_games
from tests.test_deployment import _deployment, _game, _set, _unit_named
from tests.test_space_marine_units import _model_of

# Splitting a unit in two at Declare Battle Formations (see
# app/services/in_game/unit_splits.py): seat 2's Immolator "I" (carrying 6
# ADEPTA SORORITAS INFANTRY) and Battle Sisters Squad "S" (10 models).

SISTERS = ("ADEPTA SORORITAS", "INFANTRY", "BATTLE SISTERS SQUAD")


async def _split_game(client, session, tmp_path):
    units = {
        1: [("A", 1, {})],
        2: [
            ("I", 1, {"keywords": ("TRANSPORT", "VEHICLE", "IMMOLATOR")}),
            ("S", 10, {"keywords": SISTERS}),
        ],
    }
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    i, s = _unit_named(deployment_, "I"), _unit_named(deployment_, "S")
    (await _model_of(session, i)).transport = TransportCapacity(
        capacity=6, keywords=("ADEPTA SORORITAS", "INFANTRY")
    )
    await session.commit()
    return game_id, i, s


async def _formations(client, game_id, seat=2):
    out = (await client.get(f"/games/{game_id}/formations")).json()
    return next(p for p in out["players"] if p["seat"] == seat)


async def _split(client, game_id, i, s, **extra):
    return await client.post(
        f"/games/{game_id}/formations/split",
        json={"seat": 2, "transport_unit_id": i["unit_id"], "unit_id": s["unit_id"], **extra},
    )


async def test_an_immolator_splits_a_squad_one_half_embarked(
    client: AsyncClient, session, tmp_path
):
    game_id, i, s = await _split_game(client, session, tmp_path)
    player = await _formations(client, game_id)
    [split] = player["splits"]
    assert split["transport_unit_id"] == i["unit_id"]
    assert [c["unit_id"] for c in split["candidates"]] == [s["unit_id"]]
    response = await _split(client, game_id, i, s)
    assert response.status_code == 200, response.text
    player = next(p for p in response.json()["players"] if p["seat"] == 2)
    [split] = player["splits"]
    new_id = split["new_unit_id"]
    assert split["unit_id"] == s["unit_id"] and new_id == unit_splits.SPLIT_ID_OFFSET + s["unit_id"]
    assert split["candidates"] == []
    deployment_ = await _deployment(client, game_id)
    halves = {u["unit_id"]: u for u in deployment_["units"] if u["unit_id"] in (s["unit_id"], new_id)}
    assert sorted(len(u["models"]) for u in halves.values()) == [5, 5]
    # Points shared by models.
    points = {u["unit_id"]: u["points"] for u in player["units"]}
    assert points[s["unit_id"]] == points[new_id]
    # Once per Immolator.
    assert (await _split(client, game_id, i, s)).status_code == 400

    # One half must start embarked in it.
    response = await client.post(f"/games/{game_id}/formations/done", json={"seat": 2})
    assert response.status_code == 400
    assert "must start embarked" in response.json()["detail"]
    response = await _set(client, game_id, 2, halves[new_id], "embarked", i)
    assert response.status_code == 200, response.text
    response = await client.post(f"/games/{game_id}/formations/done", json={"seat": 2})
    assert response.status_code == 200, response.text


async def test_a_split_can_be_undone(client: AsyncClient, session, tmp_path):
    game_id, i, s = await _split_game(client, session, tmp_path)
    await _split(client, game_id, i, s)
    response = await client.post(
        f"/games/{game_id}/formations/unsplit", json={"seat": 2, "unit_id": s["unit_id"]}
    )
    assert response.status_code == 200, response.text
    deployment_ = await _deployment(client, game_id)
    assert len(_unit_named(deployment_, "S")["models"]) == 10
    assert len([u for u in deployment_["units"] if u["seat"] == 2]) == 2
    player = await _formations(client, game_id)
    assert player["splits"][0]["candidates"]


async def test_a_split_survives_the_catalog_being_read_again_and_saves(
    client: AsyncClient, session, tmp_path
):
    game_id, i, s = await _split_game(client, session, tmp_path)
    await _split(client, game_id, i, s)
    new_id = unit_splits.SPLIT_ID_OFFSET + s["unit_id"]
    # Read again from the database.
    game_store.get(game_id).stale = True
    game = await _load_game(session, game_id)
    assert len(deployment.find_unit(game, s["unit_id"]).unit_models) == 5
    assert len(deployment.find_unit(game, new_id).unit_models) == 5
    # Saved and brought back.
    live = game_store.get(game_id)
    path = saves.save_current(live.game, live.catalog)
    restored, catalog = saves.restore(path)
    assert len(catalog.get("Unit", new_id).unit_models) == 5
    assert len(catalog.get("Unit", s["unit_id"]).unit_models) == 5
    # The game put back as it was before the split: so is its catalog.
    before = live.snapshot()
    before.unit_splits.clear()
    live.restore(before)
    assert live.catalog.get("Unit", new_id) is None
    assert len(live.catalog.get("Unit", s["unit_id"]).unit_models) == 10


async def test_only_one_half_can_use_its_cherub(client: AsyncClient, session, tmp_path):
    from tests.test_dread import _ability

    game_id, i, s = await _split_game(client, session, tmp_path)
    await _ability(session, s, "Cherub")
    response = await _split(client, game_id, i, s, cherub_to_new=True)
    assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    new_id = unit_splits.SPLIT_ID_OFFSET + s["unit_id"]
    original, new = (deployment.find_unit(game, u) for u in (s["unit_id"], new_id))
    assert unit_splits.cherub_allowed(game, new)
    assert not unit_splits.cherub_allowed(game, original)


async def test_the_agent_can_split(client: AsyncClient, session, tmp_path):
    from tests.test_agent import _decision
    from tests.test_agent_sororitas import _apply

    game_id, i, s = await _split_game(client, session, tmp_path)
    decision = await _decision(client, game_id)
    [action] = [a for a in decision["actions"] if a["type"] == "split_unit"]
    result = await _apply(client, game_id, action)
    assert result["log"]["ok"], result["log"]
    actions = result["decision"]["actions"]
    # Not declared until a half's embarked.
    assert not [a for a in actions if a["type"] == "declare_formations" and a["seat"] == 2]
    assert not [a for a in actions if a["type"] == "split_unit"]
    assert live_games.game(game_id).unit_splits


async def test_picking_the_models_that_go_in_the_transport(
    client: AsyncClient, session, tmp_path
):
    game_id, i, s = await _split_game(client, session, tmp_path)
    player = await _formations(client, game_id)
    [candidate] = player["splits"][0]["candidates"]
    assert candidate["sizes"] == [5] and len(candidate["models"]) == 10
    ids = [m["unit_model_id"] for m in candidate["models"]]
    # As equal as possible.
    response = await _split(client, game_id, i, s, unit_model_ids=ids[:4], embark=True)
    assert response.status_code == 400
    picked = ids[::2]
    response = await _split(client, game_id, i, s, unit_model_ids=picked, embark=True)
    assert response.status_code == 200, response.text
    player = next(p for p in response.json()["players"] if p["seat"] == 2)
    new_id = unit_splits.SPLIT_ID_OFFSET + s["unit_id"]
    new = next(u for u in player["units"] if u["unit_id"] == new_id)
    assert (new["place"], new["transport_unit_id"]) == ("embarked", i["unit_id"])
    game = await _load_game(session, game_id)
    assert sorted(m.id for m in deployment.find_unit(game, new_id).unit_models) == sorted(picked)
    # Ready to declare.
    response = await client.post(f"/games/{game_id}/formations/done", json={"seat": 2})
    assert response.status_code == 200, response.text
