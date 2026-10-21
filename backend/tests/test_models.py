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


async def _create_faction_ability(
    client: AsyncClient, faction_id: int, name: str = "Doctrina Imperatives"
) -> int:
    response = await client.post(
        "/faction-abilities", json={"name": name, "faction_id": faction_id}
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_model_with_faction_abilities(client: AsyncClient, faction_id: int):
    faction_ability_id = await _create_faction_ability(client, faction_id)

    response = await client.post(
        "/models", json=_model_payload(faction_id, faction_ability_ids=[faction_ability_id])
    )
    assert response.status_code == 201
    assert response.json()["faction_ability_ids"] == [faction_ability_id]
    # Faction abilities are their own thing, not keywords or datasheet abilities.
    assert response.json()["keyword_ids"] == []
    assert response.json()["ability_ids"] == []

    response = await client.get("/models")
    assert response.json()[0]["faction_ability_ids"] == [faction_ability_id]


async def test_create_model_defaults_to_no_faction_abilities(
    client: AsyncClient, faction_id: int
):
    response = await client.post("/models", json=_model_payload(faction_id))
    assert response.json()["faction_ability_ids"] == []


async def test_create_model_with_invalid_faction_ability_id_returns_400(
    client: AsyncClient, faction_id: int
):
    response = await client.post(
        "/models", json=_model_payload(faction_id, faction_ability_ids=[9999])
    )
    assert response.status_code == 400


async def test_update_model_replaces_faction_abilities(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    ability_a = await _create_faction_ability(client, faction_id, "Doctrina Imperatives")
    ability_b = await _create_faction_ability(client, faction_id, "Canticles")

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, faction_ability_ids=[ability_a])
    )
    assert response.json()["faction_ability_ids"] == [ability_a]

    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, faction_ability_ids=[ability_b])
    )
    assert response.json()["faction_ability_ids"] == [ability_b]

    response = await client.put(f"/models/{model_id}", json=_model_payload(faction_id))
    assert response.json()["faction_ability_ids"] == []


async def test_update_model_with_invalid_faction_ability_id_returns_400(
    client: AsyncClient, faction_id: int
):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    response = await client.put(
        f"/models/{model_id}", json=_model_payload(faction_id, faction_ability_ids=[9999])
    )
    assert response.status_code == 400


async def test_deleting_faction_ability_removes_it_from_models(
    client: AsyncClient, faction_id: int
):
    faction_ability_id = await _create_faction_ability(client, faction_id)
    await client.post(
        "/models", json=_model_payload(faction_id, faction_ability_ids=[faction_ability_id])
    )

    response = await client.delete(f"/faction-abilities/{faction_ability_id}")
    assert response.status_code == 204
    assert (await client.get("/models")).json()[0]["faction_ability_ids"] == []


async def test_attach_and_detach_datasheet_ability(client: AsyncClient, faction_id: int):
    model_a = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    model_b = (
        await client.post("/models", json=_model_payload(faction_id, name="Other"))
    ).json()["id"]
    ability_id = (await client.post("/datasheet-abilities", json={"name": "Shared"})).json()["id"]

    for model_id in (model_a, model_b):
        response = await client.put(f"/models/{model_id}/abilities/{ability_id}")
        assert response.status_code == 204
    # Attaching twice is a no-op.
    assert (await client.put(f"/models/{model_a}/abilities/{ability_id}")).status_code == 204

    models = {m["id"]: m for m in (await client.get("/models")).json()}
    assert models[model_a]["ability_ids"] == [ability_id]
    assert models[model_b]["ability_ids"] == [ability_id]

    # Detaching from one model leaves the ability and the other model alone.
    response = await client.delete(f"/models/{model_a}/abilities/{ability_id}")
    assert response.status_code == 204
    models = {m["id"]: m for m in (await client.get("/models")).json()}
    assert models[model_a]["ability_ids"] == []
    assert models[model_b]["ability_ids"] == [ability_id]
    assert [a["id"] for a in (await client.get("/datasheet-abilities")).json()] == [ability_id]


async def test_attach_datasheet_ability_unknown_ids_return_404(client: AsyncClient, faction_id: int):
    model_id = (await client.post("/models", json=_model_payload(faction_id))).json()["id"]
    ability_id = (await client.post("/datasheet-abilities", json={"name": "A"})).json()["id"]

    assert (await client.put(f"/models/9999/abilities/{ability_id}")).status_code == 404
    assert (await client.put(f"/models/{model_id}/abilities/9999")).status_code == 404
    assert (await client.delete(f"/models/9999/abilities/{ability_id}")).status_code == 404


async def test_model_base_size(client: AsyncClient, faction_id: int):
    oval = (await client.post("/base-sizes", json={"name": "105 x 70mm"})).json()["id"]
    round_ = (await client.post("/base-sizes", json={"name": "32mm"})).json()["id"]
    response = await client.post("/models", json=_model_payload(faction_id, base_size_id=oval))
    assert response.status_code == 201
    model = response.json()
    assert model["base_size_id"] == oval
    listed = next(m for m in (await client.get("/models")).json() if m["id"] == model["id"])
    assert listed["base_size_id"] == oval

    updated = await client.put(
        f"/models/{model['id']}", json=_model_payload(faction_id, base_size_id=round_)
    )
    assert updated.json()["base_size_id"] == round_
    cleared = await client.put(f"/models/{model['id']}", json=_model_payload(faction_id))
    assert cleared.json()["base_size_id"] is None


async def test_model_base_size_defaults_to_none(client: AsyncClient, faction_id: int):
    response = await client.post("/models", json=_model_payload(faction_id))
    assert response.json()["base_size_id"] is None


async def test_model_with_invalid_base_size_returns_400(client: AsyncClient, faction_id: int):
    response = await client.post("/models", json=_model_payload(faction_id, base_size_id=9999))
    assert response.status_code == 400


async def test_create_and_list_base_sizes(client: AsyncClient):
    response = await client.post("/base-sizes", json={"name": " 40mm "})
    assert response.status_code == 201
    assert response.json()["name"] == "40mm"
    assert [b["name"] for b in (await client.get("/base-sizes")).json()] == ["40mm"]
    assert (await client.post("/base-sizes", json={"name": "40mm"})).status_code == 400
    assert (await client.post("/base-sizes", json={"name": ""})).status_code == 422


async def test_model_feel_no_pain_against_mortal_wounds(client: AsyncClient, faction_id: int):
    response = await client.post(
        "/models", json=_model_payload(faction_id, feel_no_pain_mortal=5)
    )
    model = response.json()
    assert model["feel_no_pain_mortal"] == 5
    listed = next(m for m in (await client.get("/models")).json() if m["id"] == model["id"])
    assert listed["feel_no_pain_mortal"] == 5
    cleared = await client.put(f"/models/{model['id']}", json=_model_payload(faction_id))
    assert cleared.json()["feel_no_pain_mortal"] is None
