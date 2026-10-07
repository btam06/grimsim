from httpx import AsyncClient


async def test_create_and_list_faction_unit(client: AsyncClient, faction_id: int):
    response = await client.post(
        "/faction-units", json={"name": "Belisarius Cawl", "faction_id": faction_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Belisarius Cawl"
    assert body["faction_id"] == faction_id

    response = await client.get("/faction-units")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_faction_unit_with_invalid_faction_returns_400(client: AsyncClient):
    response = await client.post(
        "/faction-units", json={"name": "Belisarius Cawl", "faction_id": 9999}
    )
    assert response.status_code == 400


async def test_create_faction_unit_with_duplicate_name_in_faction_returns_400(
    client: AsyncClient, faction_id: int
):
    await client.post(
        "/faction-units", json={"name": "Belisarius Cawl", "faction_id": faction_id}
    )
    response = await client.post(
        "/faction-units", json={"name": "Belisarius Cawl", "faction_id": faction_id}
    )
    assert response.status_code == 400


async def test_delete_faction_unit(client: AsyncClient, faction_id: int):
    faction_unit_id = (
        await client.post(
            "/faction-units", json={"name": "Belisarius Cawl", "faction_id": faction_id}
        )
    ).json()["id"]

    response = await client.delete(f"/faction-units/{faction_unit_id}")
    assert response.status_code == 204

    response = await client.get("/faction-units")
    assert response.json() == []


async def test_delete_nonexistent_faction_unit_returns_404(client: AsyncClient):
    response = await client.delete("/faction-units/9999")
    assert response.status_code == 404


async def test_delete_faction_unit_in_use_returns_400(client: AsyncClient, faction_id: int):
    faction_unit_id = (
        await client.post(
            "/faction-units", json={"name": "Belisarius Cawl", "faction_id": faction_id}
        )
    ).json()["id"]
    response = await client.post(
        "/units", json={"faction_unit_id": faction_unit_id, "points": 100}
    )
    assert response.status_code == 201

    response = await client.delete(f"/faction-units/{faction_unit_id}")
    assert response.status_code == 400
