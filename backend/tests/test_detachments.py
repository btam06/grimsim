from httpx import AsyncClient


async def test_create_and_list_detachment(client: AsyncClient, faction_id: int):
    response = await client.post(
        "/detachments", json={"name": "Gladius Task Force", "faction_id": faction_id, "dp": 2}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Gladius Task Force"
    assert body["faction_id"] == faction_id
    assert body["dp"] == 2
    assert body["disposition_ids"] == []

    response = await client.get("/detachments")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_detachment_without_dp_returns_422(client: AsyncClient, faction_id: int):
    response = await client.post(
        "/detachments", json={"name": "Gladius Task Force", "faction_id": faction_id}
    )
    assert response.status_code == 422


async def test_create_detachment_with_invalid_faction_returns_400(client: AsyncClient):
    response = await client.post(
        "/detachments", json={"name": "Gladius Task Force", "faction_id": 9999, "dp": 2}
    )
    assert response.status_code == 400


async def test_create_detachment_with_dispositions(client: AsyncClient, faction_id: int):
    disposition_id = (
        await client.post("/dispositions", json={"name": "Aggressive"})
    ).json()["id"]

    response = await client.post(
        "/detachments",
        json={
            "name": "Gladius Task Force",
            "faction_id": faction_id,
            "dp": 2,
            "disposition_ids": [disposition_id],
        },
    )
    assert response.status_code == 201
    assert response.json()["disposition_ids"] == [disposition_id]

    response = await client.get("/detachments")
    assert response.json()[0]["disposition_ids"] == [disposition_id]


async def test_create_detachment_with_invalid_disposition_id_returns_400(
    client: AsyncClient, faction_id: int
):
    response = await client.post(
        "/detachments",
        json={
            "name": "Gladius Task Force",
            "faction_id": faction_id,
            "dp": 2,
            "disposition_ids": [9999],
        },
    )
    assert response.status_code == 400


async def test_delete_detachment(client: AsyncClient, faction_id: int):
    detachment_id = (
        await client.post(
            "/detachments", json={"name": "Gladius Task Force", "faction_id": faction_id, "dp": 2}
        )
    ).json()["id"]

    response = await client.delete(f"/detachments/{detachment_id}")
    assert response.status_code == 204

    response = await client.get("/detachments")
    assert response.json() == []


async def test_delete_detachment_with_dispositions(client: AsyncClient, faction_id: int):
    disposition_id = (await client.post("/dispositions", json={"name": "Aggressive"})).json()["id"]
    detachment_id = (
        await client.post(
            "/detachments",
            json={
                "name": "Gladius Task Force",
                "faction_id": faction_id,
                "dp": 2,
                "disposition_ids": [disposition_id],
            },
        )
    ).json()["id"]

    response = await client.delete(f"/detachments/{detachment_id}")
    assert response.status_code == 204


async def test_delete_nonexistent_detachment_returns_404(client: AsyncClient):
    response = await client.delete("/detachments/9999")
    assert response.status_code == 404


async def test_delete_detachment_in_use_returns_400(client: AsyncClient, faction_id: int):
    detachment_id = (
        await client.post(
            "/detachments", json={"name": "Gladius Task Force", "faction_id": faction_id, "dp": 2}
        )
    ).json()["id"]
    response = await client.post(
        "/lists",
        json={
            "name": "My List",
            "points_limit": 1000,
            "faction_id": faction_id,
            "detachment_id": detachment_id,
        },
    )
    assert response.status_code == 201

    response = await client.delete(f"/detachments/{detachment_id}")
    assert response.status_code == 400
