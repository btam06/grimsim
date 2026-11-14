from httpx import AsyncClient

from app.engine import saves
from tests.test_deployment import _game, _game_payload, _layout_file, _setup

# Games made for machine learning are flagged (see Game.ml).


async def test_a_game_made_as_an_ml_game(client: AsyncClient, session, tmp_path):
    from app.seeds import terrain_layouts as terrain_seed

    ids = await _setup(client)
    await terrain_seed.seed(session, _layout_file(tmp_path))
    response = await client.post("/games", json={**_game_payload(ids, attacker=1), "ml": True})
    assert response.status_code == 201, response.text
    assert response.json()["ml"] is True


async def test_marking_a_game_ml_shows_in_the_list(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path)
    assert game["ml"] is False
    response = await client.put(f"/games/{game['id']}/ml", json={"ml": True})
    assert response.status_code == 200, response.text
    assert response.json()["ml"] is True
    listed = {g["id"]: g for g in (await client.get("/games")).json()}
    assert listed[game["id"]]["ml"] is True
    # Saved so: brought back from its save, it still is.
    restored, _ = saves.restore(saves.latest(game["id"]))
    assert restored.ml is True
    response = await client.put(f"/games/{game['id']}/ml", json={"ml": False})
    assert response.json()["ml"] is False
