from httpx import AsyncClient


async def _create_detachment(client: AsyncClient, faction_id: int, name: str = "Gladius") -> int:
    response = await client.post("/detachments", json={"name": name, "faction_id": faction_id})
    assert response.status_code == 201
    return response.json()["id"]


def _list_payload(faction_id: int, detachment_id: int, **overrides) -> dict:
    payload = {
        "name": "My List",
        "points_limit": 1000,
        "faction_id": faction_id,
        "detachment_id": detachment_id,
    }
    payload.update(overrides)
    return payload


async def test_create_and_list_army_list(client: AsyncClient, faction_id: int):
    detachment_id = await _create_detachment(client, faction_id)

    response = await client.post("/lists", json=_list_payload(faction_id, detachment_id))
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My List"
    assert body["points_limit"] == 1000

    response = await client.get("/lists")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_list_with_invalid_points_limit_returns_422(
    client: AsyncClient, faction_id: int
):
    detachment_id = await _create_detachment(client, faction_id)
    response = await client.post(
        "/lists", json=_list_payload(faction_id, detachment_id, points_limit=1500)
    )
    assert response.status_code == 422


async def test_create_list_with_2000_points(client: AsyncClient, faction_id: int):
    detachment_id = await _create_detachment(client, faction_id)
    response = await client.post(
        "/lists", json=_list_payload(faction_id, detachment_id, points_limit=2000)
    )
    assert response.status_code == 201
    assert response.json()["points_limit"] == 2000


async def test_create_list_with_invalid_faction_returns_400(client: AsyncClient, faction_id: int):
    detachment_id = await _create_detachment(client, faction_id)
    response = await client.post(
        "/lists", json=_list_payload(faction_id=9999, detachment_id=detachment_id)
    )
    assert response.status_code == 400


async def test_create_list_with_invalid_detachment_returns_400(
    client: AsyncClient, faction_id: int
):
    response = await client.post("/lists", json=_list_payload(faction_id, detachment_id=9999))
    assert response.status_code == 400


async def test_create_list_with_detachment_from_other_faction_returns_400(
    client: AsyncClient, session, faction_id: int
):
    from app.models import Faction

    other_faction = Faction(name="Other Faction")
    session.add(other_faction)
    await session.commit()

    detachment_id = await _create_detachment(client, other_faction.id)

    response = await client.post("/lists", json=_list_payload(faction_id, detachment_id))
    assert response.status_code == 400


async def test_update_list_changes_fields(client: AsyncClient, faction_id: int):
    detachment_id = await _create_detachment(client, faction_id)
    list_id = (
        await client.post("/lists", json=_list_payload(faction_id, detachment_id))
    ).json()["id"]

    response = await client.put(
        f"/lists/{list_id}",
        json=_list_payload(faction_id, detachment_id, name="Updated List", points_limit=2000),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == list_id
    assert body["name"] == "Updated List"
    assert body["points_limit"] == 2000

    response = await client.get("/lists")
    assert response.json()[0]["name"] == "Updated List"


async def test_update_list_with_detachment_from_other_faction_returns_400(
    client: AsyncClient, session, faction_id: int
):
    from app.models import Faction

    detachment_id = await _create_detachment(client, faction_id)
    list_id = (
        await client.post("/lists", json=_list_payload(faction_id, detachment_id))
    ).json()["id"]

    other_faction = Faction(name="Other Faction")
    session.add(other_faction)
    await session.commit()
    other_detachment_id = await _create_detachment(client, other_faction.id, name="Other")

    response = await client.put(
        f"/lists/{list_id}", json=_list_payload(faction_id, other_detachment_id)
    )
    assert response.status_code == 400


async def test_update_nonexistent_list_returns_404(client: AsyncClient, faction_id: int):
    detachment_id = await _create_detachment(client, faction_id)
    response = await client.put("/lists/9999", json=_list_payload(faction_id, detachment_id))
    assert response.status_code == 404


async def test_delete_list(client: AsyncClient, faction_id: int):
    detachment_id = await _create_detachment(client, faction_id)
    list_id = (
        await client.post("/lists", json=_list_payload(faction_id, detachment_id))
    ).json()["id"]

    response = await client.delete(f"/lists/{list_id}")
    assert response.status_code == 204

    response = await client.get("/lists")
    assert response.json() == []


async def test_delete_list_unassigns_units(client: AsyncClient, faction_id: int):
    detachment_id = await _create_detachment(client, faction_id)
    list_id = (
        await client.post("/lists", json=_list_payload(faction_id, detachment_id))
    ).json()["id"]
    unit_id = (
        await client.post("/units", json={"name": "Squad", "points": 100, "list_id": list_id})
    ).json()["id"]

    response = await client.delete(f"/lists/{list_id}")
    assert response.status_code == 204

    units = (await client.get("/units")).json()
    unassigned = next(u for u in units if u["id"] == unit_id)
    assert unassigned["list_id"] is None


async def test_delete_nonexistent_list_returns_404(client: AsyncClient):
    response = await client.delete("/lists/9999")
    assert response.status_code == 404
