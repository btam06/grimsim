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


async def test_delete_faction(client: AsyncClient):
    faction_id = (await client.post("/factions", json={"name": "Ultramarines"})).json()["id"]

    response = await client.delete(f"/factions/{faction_id}")
    assert response.status_code == 204

    response = await client.get("/factions")
    assert response.json() == []


async def test_delete_nonexistent_faction_returns_404(client: AsyncClient):
    response = await client.delete("/factions/9999")
    assert response.status_code == 404


async def test_delete_faction_in_use_returns_400(client: AsyncClient, faction_id: int):
    response = await client.post(
        "/models",
        json={
            "name": "Intercessor",
            "faction_id": faction_id,
            "save": 3,
            "toughness": 4,
            "oc": 2,
            "movement": 6,
            "wounds": 2,
            "leadership": 7,
        },
    )
    assert response.status_code == 201

    response = await client.delete(f"/factions/{faction_id}")
    assert response.status_code == 400
