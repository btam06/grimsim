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
    }
    response = await client.post("/models", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _weapon_payload(model_id: int, **overrides) -> dict:
    payload = {
        "name": "Bolt Rifle",
        "model_id": model_id,
        "damage": "1",
        "range": 24,
        "strength": 4,
        "ap": -1,
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
    assert body["ap"] == -1
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


async def test_create_weapon_with_dice_damage(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    for valid_damage in ["1", "9", "10", "123", "D3", "D6", "1D3", "2D6", "0D3", "10D6"]:
        response = await client.post(
            "/weapons", json=_weapon_payload(model_id, damage=valid_damage)
        )
        assert response.status_code == 201, valid_damage
        assert response.json()["damage"] == valid_damage


async def test_create_weapon_with_invalid_damage_returns_422(
    client: AsyncClient, faction_id: int
):
    model_id = await _create_model(client, faction_id)
    for invalid_damage in ["1D4", "1d6", "D", "DD3", "1D", "D36", ""]:
        response = await client.post(
            "/weapons", json=_weapon_payload(model_id, damage=invalid_damage)
        )
        assert response.status_code == 422, invalid_damage


async def test_update_weapon_changes_fields(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    weapon_id = (await client.post("/weapons", json=_weapon_payload(model_id))).json()["id"]

    response = await client.put(
        f"/weapons/{weapon_id}",
        json=_weapon_payload(model_id, name="Heavy Bolt Rifle", damage="2D6"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == weapon_id
    assert body["name"] == "Heavy Bolt Rifle"
    assert body["damage"] == "2D6"

    response = await client.get("/weapons")
    assert response.json()[0]["name"] == "Heavy Bolt Rifle"


async def test_update_weapon_replaces_abilities(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    weapon_id = (await client.post("/weapons", json=_weapon_payload(model_id))).json()["id"]
    ability_id = (await client.post("/weapon-abilities", json={"name": "Lethal Hits"})).json()["id"]

    response = await client.put(
        f"/weapons/{weapon_id}", json=_weapon_payload(model_id, ability_ids=[ability_id])
    )
    assert response.json()["ability_ids"] == [ability_id]

    response = await client.put(f"/weapons/{weapon_id}", json=_weapon_payload(model_id))
    assert response.json()["ability_ids"] == []


async def test_update_weapon_can_change_model(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    other_model_id = await _create_model(client, faction_id)
    weapon_id = (await client.post("/weapons", json=_weapon_payload(model_id))).json()["id"]

    response = await client.put(
        f"/weapons/{weapon_id}", json=_weapon_payload(other_model_id)
    )
    assert response.status_code == 200
    assert response.json()["model_id"] == other_model_id


async def test_update_weapon_with_invalid_model_returns_400(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    weapon_id = (await client.post("/weapons", json=_weapon_payload(model_id))).json()["id"]

    response = await client.put(f"/weapons/{weapon_id}", json=_weapon_payload(model_id=9999))
    assert response.status_code == 400


async def test_update_nonexistent_weapon_returns_404(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    response = await client.put("/weapons/9999", json=_weapon_payload(model_id))
    assert response.status_code == 404


async def test_delete_weapon(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    weapon_id = (await client.post("/weapons", json=_weapon_payload(model_id))).json()["id"]

    response = await client.delete(f"/weapons/{weapon_id}")
    assert response.status_code == 204

    response = await client.get("/weapons")
    assert response.json() == []


async def test_delete_weapon_with_abilities(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    ability_id = (await client.post("/weapon-abilities", json={"name": "Lethal Hits"})).json()["id"]
    weapon_id = (
        await client.post("/weapons", json=_weapon_payload(model_id, ability_ids=[ability_id]))
    ).json()["id"]

    response = await client.delete(f"/weapons/{weapon_id}")
    assert response.status_code == 204


async def test_delete_nonexistent_weapon_returns_404(client: AsyncClient):
    response = await client.delete("/weapons/9999")
    assert response.status_code == 404


async def test_delete_weapon_equipped_by_unit_returns_400(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id)
    weapon_id = (await client.post("/weapons", json=_weapon_payload(model_id))).json()["id"]

    response = await client.post(
        "/units",
        json={
            "name": "Squad",
            "points": 100,
            "unit_models": [{"model_id": model_id, "weapon_ids": [weapon_id]}],
        },
    )
    assert response.status_code == 201

    response = await client.delete(f"/weapons/{weapon_id}")
    assert response.status_code == 400
