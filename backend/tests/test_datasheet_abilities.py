from httpx import AsyncClient


async def test_create_and_list_datasheet_ability(client: AsyncClient):
    response = await client.post(
        "/datasheet-abilities",
        json={"name": "Deep Strike", "description": "May be set up in reserve"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Deep Strike"
    assert body["description"] == "May be set up in reserve"

    response = await client.get("/datasheet-abilities")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_datasheet_ability_without_description(client: AsyncClient):
    response = await client.post("/datasheet-abilities", json={"name": "Stealth"})
    assert response.status_code == 201
    assert response.json()["description"] is None
