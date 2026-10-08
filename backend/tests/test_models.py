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
        "leadership": 7,
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


async def test_create_model_defaults_support_and_leader_false(
    client: AsyncClient, faction_id: int
):
    response = await client.post("/models", json=_model_payload(faction_id))
    assert response.status_code == 201
    body = response.json()
    assert body["is_support"] is False
    assert body["is_leader"] is False
    assert body["leadership"] == 7


async def test_create_model_as_support_and_leader(client: AsyncClient, faction_id: int):
    response = await client.post(
        "/models", json=_model_payload(faction_id, is_support=True, is_leader=True)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["is_support"] is True
    assert body["is_leader"] is True


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


async def test_create_model_with_keywords(client: AsyncClient, faction_id: int):
    keyword_id = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]

    response = await client.post(
        "/models", json=_model_payload(faction_id, keyword_ids=[keyword_id])
    )
    assert response.status_code == 201
    assert response.json()["keyword_ids"] == [keyword_id]

    response = await client.get("/models")
    assert response.json()[0]["keyword_ids"] == [keyword_id]


async def test_create_model_with_multiple_keywords(client: AsyncClient, faction_id: int):
    keyword_a = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]
    keyword_b = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]

    response = await client.post(
        "/models", json=_model_payload(faction_id, keyword_ids=[keyword_a, keyword_b])
    )
    assert response.status_code == 201
    assert set(response.json()["keyword_ids"]) == {keyword_a, keyword_b}


async def test_create_model_with_invalid_keyword_id_returns_400(client: AsyncClient, faction_id: int):
    response = await client.post("/models", json=_model_payload(faction_id, keyword_ids=[9999]))
    assert response.status_code == 400


async def test_keyword_can_be_attached_to_multiple_models(client: AsyncClient, faction_id: int):
    keyword_id = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]

    model_a_id = (
        await client.post("/models", json=_model_payload(faction_id, keyword_ids=[keyword_id]))
    ).json()["id"]
    model_b_id = (
        await client.post(
            "/models", json=_model_payload(faction_id, name="Other", keyword_ids=[keyword_id])
        )
    ).json()["id"]

    response = await client.get("/models")
    models_by_id = {m["id"]: m for m in response.json()}
    assert models_by_id[model_a_id]["keyword_ids"] == [keyword_id]
    assert models_by_id[model_b_id]["keyword_ids"] == [keyword_id]


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


async def test_update_model_replaces_keywords(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    keyword_a = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]
    keyword_b = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, keyword_ids=[keyword_a])
    )
    assert response.json()["keyword_ids"] == [keyword_a]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, keyword_ids=[keyword_b])
    )
    assert response.json()["keyword_ids"] == [keyword_b]

    response = await client.put(f"/models/{model_id}", json=_model_payload(faction_id))
    assert response.json()["keyword_ids"] == []


async def test_update_model_changes_support_and_leader(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, is_support=True, leadership=9)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_support"] is True
    assert body["is_leader"] is False
    assert body["leadership"] == 9


async def test_update_model_with_invalid_faction_returns_400(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    response = await client.put(f"/models/{model_id}", json=_model_payload(faction_id=9999))
    assert response.status_code == 400


async def test_update_nonexistent_model_returns_404(client: AsyncClient, faction_id: int):
    response = await client.put("/models/9999", json=_model_payload(faction_id))
    assert response.status_code == 404
