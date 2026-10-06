from httpx import AsyncClient


async def test_create_and_list_disposition(client: AsyncClient):
    response = await client.post(
        "/dispositions", json={"name": "Aggressive", "description": "Push forward"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Aggressive"
    assert body["description"] == "Push forward"

    response = await client.get("/dispositions")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_disposition_without_description(client: AsyncClient):
    response = await client.post("/dispositions", json={"name": "Defensive"})
    assert response.status_code == 201
    assert response.json()["description"] is None
