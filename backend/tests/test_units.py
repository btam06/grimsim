from httpx import AsyncClient


async def _create_model(client: AsyncClient, faction_id: int, name: str) -> int:
    payload = {
        "name": name,
        "faction_id": faction_id,
        "save": 3,
        "toughness": 4,
        "oc": 2,
        "movement": 6,
        "wounds": 2,
        "leadership": 7,
    }
    response = await client.post("/models", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_weapon(client: AsyncClient, model_id: int, name: str = "Bolt Rifle") -> int:
    response = await client.post(
        "/weapons",
        json={
            "name": name,
            "model_id": model_id,
            "damage": "1",
            "range": 24,
            "strength": 4,
            "ap": -1,
            "attacks": 2,
            "skill": 3,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_wargear(client: AsyncClient, model_id: int, name: str = "Frag Grenades") -> int:
    response = await client.post("/wargear", json={"name": name, "model_id": model_id})
    assert response.status_code == 201
    return response.json()["id"]


async def _create_faction_unit(
    client: AsyncClient, faction_id: int, name: str = "Intercessor Squad"
) -> int:
    response = await client.post(
        "/faction-units", json={"name": name, "faction_id": faction_id}
    )
    assert response.status_code == 201
    return response.json()["id"]


def _unit_payload(faction_unit_id: int, **overrides) -> dict:
    payload = {"faction_unit_id": faction_unit_id, "points": 100, "unit_models": []}
    payload.update(overrides)
    return payload


async def test_create_unit_with_duplicate_models(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id, "Intercessor")
    faction_unit_id = await _create_faction_unit(client, faction_id)

    response = await client.post(
        "/units",
        json=_unit_payload(
            faction_unit_id,
            unit_models=[{"model_id": model_id}, {"model_id": model_id}],
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["faction_unit_id"] == faction_unit_id
    assert body["points"] == 100
    assert len(body["unit_models"]) == 2
    assert [um["model_id"] for um in body["unit_models"]] == [model_id, model_id]
    assert body["unit_models"][0]["id"] != body["unit_models"][1]["id"]

    response = await client.get("/units")
    listed = response.json()
    assert len(listed) == 1
    assert len(listed[0]["unit_models"]) == 2


async def test_create_unit_with_per_model_weapon_and_wargear(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id, "Intercessor")
    weapon_id = await _create_weapon(client, model_id)
    wargear_id = await _create_wargear(client, model_id)
    faction_unit_id = await _create_faction_unit(client, faction_id)

    response = await client.post(
        "/units",
        json=_unit_payload(
            faction_unit_id,
            unit_models=[
                {"model_id": model_id, "weapon_ids": [weapon_id], "wargear_ids": [wargear_id]}
            ],
        ),
    )
    assert response.status_code == 201
    unit_model = response.json()["unit_models"][0]
    assert unit_model["weapon_ids"] == [weapon_id]
    assert unit_model["wargear_ids"] == [wargear_id]


async def test_create_unit_without_models(client: AsyncClient, faction_id: int):
    faction_unit_id = await _create_faction_unit(client, faction_id, "Empty Squad")
    response = await client.post("/units", json=_unit_payload(faction_unit_id))
    assert response.status_code == 201
    assert response.json()["unit_models"] == []


async def test_create_unit_with_invalid_model_id_returns_400(client: AsyncClient, faction_id: int):
    faction_unit_id = await _create_faction_unit(client, faction_id, "Bad Squad")
    response = await client.post(
        "/units",
        json=_unit_payload(faction_unit_id, unit_models=[{"model_id": 9999}]),
    )
    assert response.status_code == 400


async def test_create_unit_with_invalid_faction_unit_id_returns_400(client: AsyncClient):
    response = await client.post("/units", json=_unit_payload(9999))
    assert response.status_code == 400


async def test_create_unit_with_invalid_weapon_id_returns_400(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id, "Intercessor")
    faction_unit_id = await _create_faction_unit(client, faction_id, "Bad Squad")
    response = await client.post(
        "/units",
        json=_unit_payload(
            faction_unit_id, unit_models=[{"model_id": model_id, "weapon_ids": [9999]}]
        ),
    )
    assert response.status_code == 400


async def test_create_unit_with_weapon_from_other_model_returns_400(
    client: AsyncClient, faction_id: int
):
    model_id = await _create_model(client, faction_id, "Intercessor")
    other_model_id = await _create_model(client, faction_id, "Terminator")
    weapon_id = await _create_weapon(client, other_model_id)
    faction_unit_id = await _create_faction_unit(client, faction_id, "Bad Squad")

    response = await client.post(
        "/units",
        json=_unit_payload(
            faction_unit_id, unit_models=[{"model_id": model_id, "weapon_ids": [weapon_id]}]
        ),
    )
    assert response.status_code == 400


async def test_create_unit_with_wargear_from_other_model_returns_400(
    client: AsyncClient, faction_id: int
):
    model_id = await _create_model(client, faction_id, "Intercessor")
    other_model_id = await _create_model(client, faction_id, "Terminator")
    wargear_id = await _create_wargear(client, other_model_id)
    faction_unit_id = await _create_faction_unit(client, faction_id, "Bad Squad")

    response = await client.post(
        "/units",
        json=_unit_payload(
            faction_unit_id, unit_models=[{"model_id": model_id, "wargear_ids": [wargear_id]}]
        ),
    )
    assert response.status_code == 400


async def test_create_unit_with_list_id(client: AsyncClient, faction_id: int):
    detachment_id = (
        await client.post(
            "/detachments", json={"name": "Gladius", "faction_id": faction_id, "dp": 2}
        )
    ).json()["id"]
    list_id = (
        await client.post(
            "/lists",
            json={
                "name": "My List",
                "points_limit": 1000,
                "faction_id": faction_id,
                "detachment_ids": [detachment_id],
            },
        )
    ).json()["id"]
    faction_unit_id = await _create_faction_unit(client, faction_id)

    response = await client.post("/units", json=_unit_payload(faction_unit_id, list_id=list_id))
    assert response.status_code == 201
    assert response.json()["list_id"] == list_id


async def test_create_unit_with_invalid_list_id_returns_400(client: AsyncClient, faction_id: int):
    faction_unit_id = await _create_faction_unit(client, faction_id)
    response = await client.post("/units", json=_unit_payload(faction_unit_id, list_id=9999))
    assert response.status_code == 400


async def test_update_unit_changes_fields(client: AsyncClient, faction_id: int):
    faction_unit_id = await _create_faction_unit(client, faction_id)
    other_faction_unit_id = await _create_faction_unit(client, faction_id, "Veteran Squad")
    unit_id = (
        await client.post("/units", json=_unit_payload(faction_unit_id))
    ).json()["id"]

    response = await client.put(
        f"/units/{unit_id}",
        json=_unit_payload(other_faction_unit_id, points=150),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == unit_id
    assert body["faction_unit_id"] == other_faction_unit_id
    assert body["points"] == 150

    response = await client.get("/units")
    assert response.json()[0]["faction_unit_id"] == other_faction_unit_id


async def test_update_unit_replaces_unit_models(client: AsyncClient, faction_id: int):
    model_a = await _create_model(client, faction_id, "Intercessor")
    model_b = await _create_model(client, faction_id, "Terminator")
    faction_unit_id = await _create_faction_unit(client, faction_id)
    unit_id = (
        await client.post(
            "/units", json=_unit_payload(faction_unit_id, unit_models=[{"model_id": model_a}])
        )
    ).json()["id"]

    response = await client.put(
        f"/units/{unit_id}",
        json=_unit_payload(faction_unit_id, unit_models=[{"model_id": model_b}]),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["unit_models"]) == 1
    assert body["unit_models"][0]["model_id"] == model_b

    response = await client.get("/units")
    listed = response.json()[0]
    assert len(listed["unit_models"]) == 1
    assert listed["unit_models"][0]["model_id"] == model_b


async def test_update_unit_can_change_list(client: AsyncClient, faction_id: int):
    detachment_id = (
        await client.post(
            "/detachments", json={"name": "Gladius", "faction_id": faction_id, "dp": 2}
        )
    ).json()["id"]
    list_id = (
        await client.post(
            "/lists",
            json={
                "name": "My List",
                "points_limit": 1000,
                "faction_id": faction_id,
                "detachment_ids": [detachment_id],
            },
        )
    ).json()["id"]
    faction_unit_id = await _create_faction_unit(client, faction_id)
    unit_id = (await client.post("/units", json=_unit_payload(faction_unit_id))).json()["id"]

    response = await client.put(
        f"/units/{unit_id}", json=_unit_payload(faction_unit_id, list_id=list_id)
    )
    assert response.status_code == 200
    assert response.json()["list_id"] == list_id


async def test_update_unit_with_invalid_list_id_returns_400(client: AsyncClient, faction_id: int):
    faction_unit_id = await _create_faction_unit(client, faction_id)
    unit_id = (await client.post("/units", json=_unit_payload(faction_unit_id))).json()["id"]
    response = await client.put(
        f"/units/{unit_id}", json=_unit_payload(faction_unit_id, list_id=9999)
    )
    assert response.status_code == 400


async def test_update_unit_with_invalid_faction_unit_id_returns_400(
    client: AsyncClient, faction_id: int
):
    faction_unit_id = await _create_faction_unit(client, faction_id)
    unit_id = (await client.post("/units", json=_unit_payload(faction_unit_id))).json()["id"]
    response = await client.put(f"/units/{unit_id}", json=_unit_payload(9999))
    assert response.status_code == 400


async def test_update_nonexistent_unit_returns_404(client: AsyncClient, faction_id: int):
    faction_unit_id = await _create_faction_unit(client, faction_id)
    response = await client.put("/units/9999", json=_unit_payload(faction_unit_id))
    assert response.status_code == 404


async def test_delete_unit(client: AsyncClient, faction_id: int):
    faction_unit_id = await _create_faction_unit(client, faction_id)
    unit_id = (await client.post("/units", json=_unit_payload(faction_unit_id))).json()["id"]

    response = await client.delete(f"/units/{unit_id}")
    assert response.status_code == 204

    response = await client.get("/units")
    assert response.json() == []


async def test_delete_unit_cascades_unit_models(client: AsyncClient, faction_id: int):
    model_id = await _create_model(client, faction_id, "Intercessor")
    faction_unit_id = await _create_faction_unit(client, faction_id)
    unit_id = (
        await client.post(
            "/units", json=_unit_payload(faction_unit_id, unit_models=[{"model_id": model_id}])
        )
    ).json()["id"]

    response = await client.delete(f"/units/{unit_id}")
    assert response.status_code == 204


async def test_delete_nonexistent_unit_returns_404(client: AsyncClient):
    response = await client.delete("/units/9999")
    assert response.status_code == 404
