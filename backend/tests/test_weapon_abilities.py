from httpx import AsyncClient


async def test_create_and_list_weapon_ability(client: AsyncClient):
    response = await client.post(
        "/weapon-abilities",
        json={"name": "Lethal Hits", "description": "Critical hits wound automatically"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Lethal Hits"
    assert body["description"] == "Critical hits wound automatically"

    response = await client.get("/weapon-abilities")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_weapon_ability_without_description(client: AsyncClient):
    response = await client.post("/weapon-abilities", json={"name": "Twin-linked"})
    assert response.status_code == 201
    assert response.json()["description"] is None
