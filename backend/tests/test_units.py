from httpx import AsyncClient


async def _create_model(client: AsyncClient, faction_id: int, name: str) -> int:
    payload = {
        "name": name,
        "faction_id": faction_id,
        "points": 20,
        "save": 3,
        "toughness": 4,
        "oc": 2,
        "movement": 6,
        "wounds": 2,
    }
    response = await client.post("/models", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_unit_with_models(client: AsyncClient, faction_id: int):
    model_id_1 = await _create_model(client, faction_id, "Intercessor")
    model_id_2 = await _create_model(client, faction_id, "Sergeant")

    response = await client.post(
        "/units", json={"name": "Intercessor Squad", "model_ids": [model_id_1, model_id_2]}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Intercessor Squad"
    assert sorted(body["model_ids"]) == sorted([model_id_1, model_id_2])

    response = await client.get("/units")
    assert response.status_code == 200
    listed = response.json()
    assert len(listed) == 1
    assert sorted(listed[0]["model_ids"]) == sorted([model_id_1, model_id_2])


async def test_create_unit_without_models(client: AsyncClient):
    response = await client.post("/units", json={"name": "Empty Squad"})
    assert response.status_code == 201
    assert response.json()["model_ids"] == []


async def test_create_unit_with_invalid_model_id_returns_400(client: AsyncClient):
    response = await client.post("/units", json={"name": "Bad Squad", "model_ids": [9999]})
    assert response.status_code == 400
