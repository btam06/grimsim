from httpx import AsyncClient


async def test_create_and_list_faction(client: AsyncClient):
    response = await client.post("/factions", json={"name": "Ultramarines"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Ultramarines"

    response = await client.get("/factions")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_faction_with_duplicate_name_returns_400(client: AsyncClient):
    await client.post("/factions", json={"name": "Ultramarines"})
    response = await client.post("/factions", json={"name": "Ultramarines"})
    assert response.status_code == 400
