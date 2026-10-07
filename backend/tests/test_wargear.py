from httpx import AsyncClient


async def _create_model(client: AsyncClient, faction_id: int) -> int:
    payload = {
        "name": "Intercessor",
        "faction_id": faction_id,
        "save": 3,
        "toughness": 4,
        "oc": 2,
        "movement": 6,
        "wounds": 2,
        "leadership": 7,
    }
    response = await client.post("/models", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_and_list_wargear(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)

    response = await client.post(
        "/wargear", json={"name": "Frag Grenades", "model_id": model_id, "description": "Boom"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Frag Grenades"
    assert body["model_id"] == model_id
    assert body["description"] == "Boom"

    response = await client.get("/wargear")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_wargear_without_description(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    response = await client.post("/wargear", json={"name": "Auspex", "model_id": model_id})
    assert response.status_code == 201
    assert response.json()["description"] is None


async def test_create_wargear_with_invalid_model_id_returns_400(client: AsyncClient):
    response = await client.post("/wargear", json={"name": "Auspex", "model_id": 9999})
    assert response.status_code == 400
