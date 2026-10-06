from httpx import AsyncClient


def _model_payload(faction_id: int, **overrides) -> dict:
    payload = {
        "name": "Intercessor",
        "faction_id": faction_id,
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


async def test_create_model_with_wargear_reassigns_it(client: AsyncClient, faction_id: int):
    owner_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    wargear_id = (
        await client.post("/wargear", json={"name": "Frag Grenades", "model_id": owner_id})
    ).json()["id"]

    response = await client.post(
        "/models", json=_model_payload(faction_id, wargear_ids=[wargear_id])
    )
    assert response.status_code == 201
    body = response.json()
    assert body["wargear_ids"] == [wargear_id]

    wargear = (await client.get("/wargear")).json()
    reassigned = next(g for g in wargear if g["id"] == wargear_id)
    assert reassigned["model_id"] == body["id"]


async def test_create_model_with_invalid_wargear_id_returns_400(client: AsyncClient, faction_id: int):
    response = await client.post("/models", json=_model_payload(faction_id, wargear_ids=[9999]))
    assert response.status_code == 400


async def test_update_model_additively_reassigns_wargear(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    other_model_id = (
        await client.post("/models", json=_model_payload(faction_id, name="Other"))
    ).json()["id"]
    wargear_id = (
        await client.post("/wargear", json={"name": "Frag Grenades", "model_id": other_model_id})
    ).json()["id"]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, wargear_ids=[wargear_id])
    )
    assert response.status_code == 200
    assert response.json()["wargear_ids"] == [wargear_id]

    wargear = (await client.get("/wargear")).json()
    reassigned = next(g for g in wargear if g["id"] == wargear_id)
    assert reassigned["model_id"] == model_id


async def test_update_model_changes_fields(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]

    response = await client.put(
        f"/models/{model_id}",
        json=_model_payload(faction_id, name="Veteran Intercessor", toughness=5),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == model_id
    assert body["name"] == "Veteran Intercessor"
    assert body["toughness"] == 5

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


async def test_update_model_with_invalid_faction_returns_400(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    response = await client.put(f"/models/{model_id}", json=_model_payload(faction_id=9999))
    assert response.status_code == 400


async def test_update_nonexistent_model_returns_404(client: AsyncClient, faction_id: int):
    response = await client.put("/models/9999", json=_model_payload(faction_id))
    assert response.status_code == 404
