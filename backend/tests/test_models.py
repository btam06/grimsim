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
