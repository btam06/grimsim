from httpx import AsyncClient


async def _create_model(client: AsyncClient, faction_id: int) -> int:
    payload = {
        "name": "Intercessor",
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


def _weapon_payload(model_id: int, **overrides) -> dict:
    payload = {
        "name": "Bolt Rifle",
        "model_id": model_id,
        "damage": 1,
        "range": 24,
        "strength": 4,
        "attacks": 2,
    }
    payload.update(overrides)
    return payload


async def test_create_and_list_weapon(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)

    response = await client.post("/weapons", json=_weapon_payload(model_id))
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Bolt Rifle"
    assert body["model_id"] == model_id
    assert body["ability_ids"] == []

    response = await client.get("/weapons")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_weapon_with_abilities(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    ability_response = await client.post("/weapon-abilities", json={"name": "Lethal Hits"})
    ability_id = ability_response.json()["id"]

    response = await client.post(
        "/weapons", json=_weapon_payload(model_id, ability_ids=[ability_id])
    )
    assert response.status_code == 201
    assert response.json()["ability_ids"] == [ability_id]

    response = await client.get("/weapons")
    assert response.json()[0]["ability_ids"] == [ability_id]


async def test_create_weapon_with_invalid_model_id_returns_400(client: AsyncClient):
    response = await client.post("/weapons", json=_weapon_payload(model_id=9999))
    assert response.status_code == 400


async def test_create_weapon_with_invalid_ability_id_returns_400(
    client: AsyncClient, faction_id: int
):
    model_id = await _create_model(client, faction_id)
    response = await client.post(
        "/weapons", json=_weapon_payload(model_id, ability_ids=[9999])
    )
    assert response.status_code == 400
