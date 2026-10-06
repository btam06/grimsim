from httpx import AsyncClient


def _model_payload(faction_id: int, **overrides) -> dict:
    payload = {
        "name": "Intercessor",
        "faction_id": faction_id,
        "points": 20,
        "save": 3,
        "toughness": 4,
        "oc": 2,
        "movement": 6,
        "wounds": 2,
        "invulnerable": None,
        "feel_no_pain": None,
    }
    payload.update(overrides)
    return payload


async def test_create_and_list_model(client: AsyncClient, faction_id: int):
    response = await client.post("/models", json=_model_payload(faction_id))
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Intercessor"
    assert body["faction_id"] == faction_id
    assert body["wounds"] == 2

    response = await client.get("/models")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_model_with_invalid_faction_returns_400(client: AsyncClient):
    response = await client.post("/models", json=_model_payload(faction_id=9999))
    assert response.status_code == 400


async def test_create_model_with_abilities(client: AsyncClient, faction_id: int):
    ability_response = await client.post("/datasheet-abilities", json={"name": "Deep Strike"})
    ability_id = ability_response.json()["id"]

    response = await client.post(
        "/models", json=_model_payload(faction_id, ability_ids=[ability_id])
    )
    assert response.status_code == 201
    assert response.json()["ability_ids"] == [ability_id]

    response = await client.get("/models")
    assert response.json()[0]["ability_ids"] == [ability_id]


async def test_create_model_with_invalid_ability_id_returns_400(client: AsyncClient, faction_id: int):
    response = await client.post("/models", json=_model_payload(faction_id, ability_ids=[9999]))
    assert response.status_code == 400


async def test_create_model_with_weapons_reassigns_them(client: AsyncClient, faction_id: int):
    owner_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    weapon_response = await client.post(
        "/weapons",
        json={
            "name": "Bolt Rifle",
            "model_id": owner_id,
            "damage": 1,
            "range": 24,
            "strength": 4,
            "attacks": 2,
        },
    )
    weapon_id = weapon_response.json()["id"]

    response = await client.post(
        "/models", json=_model_payload(faction_id, weapon_ids=[weapon_id])
    )
    assert response.status_code == 201
    body = response.json()
    assert body["weapon_ids"] == [weapon_id]

    weapons = (await client.get("/weapons")).json()
    reassigned = next(w for w in weapons if w["id"] == weapon_id)
    assert reassigned["model_id"] == body["id"]


async def test_create_model_with_invalid_weapon_id_returns_400(client: AsyncClient, faction_id: int):
    response = await client.post("/models", json=_model_payload(faction_id, weapon_ids=[9999]))
    assert response.status_code == 400


async def test_update_model_changes_fields(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, name="Veteran Intercessor", points=25)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == model_id
    assert body["name"] == "Veteran Intercessor"
    assert body["points"] == 25

    response = await client.get("/models")
    assert response.json()[0]["name"] == "Veteran Intercessor"


async def test_update_model_replaces_abilities(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    ability_a = (await client.post("/datasheet-abilities", json={"name": "Deep Strike"})).json()["id"]
    ability_b = (await client.post("/datasheet-abilities", json={"name": "Stealth"})).json()["id"]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, ability_ids=[ability_a])
    )
    assert response.json()["ability_ids"] == [ability_a]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, ability_ids=[ability_b])
    )
    assert response.json()["ability_ids"] == [ability_b]

    response = await client.put(f"/models/{model_id}", json=_model_payload(faction_id))
    assert response.json()["ability_ids"] == []


async def test_update_model_additively_reassigns_weapons(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    other_model_id = (
        await client.post("/models", json=_model_payload(faction_id, name="Other"))
    ).json()["id"]
    weapon_id = (
        await client.post(
            "/weapons",
            json={
                "name": "Bolt Rifle",
                "model_id": other_model_id,
                "damage": 1,
                "range": 24,
                "strength": 4,
                "attacks": 2,
            },
        )
    ).json()["id"]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, weapon_ids=[weapon_id])
    )
    assert response.status_code == 200
    assert response.json()["weapon_ids"] == [weapon_id]

    weapons = (await client.get("/weapons")).json()
    reassigned = next(w for w in weapons if w["id"] == weapon_id)
    assert reassigned["model_id"] == model_id


async def test_update_model_with_invalid_faction_returns_400(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    response = await client.put(f"/models/{model_id}", json=_model_payload(faction_id=9999))
    assert response.status_code == 400


async def test_update_nonexistent_model_returns_404(client: AsyncClient, faction_id: int):
    response = await client.put("/models/9999", json=_model_payload(faction_id))
    assert response.status_code == 404
