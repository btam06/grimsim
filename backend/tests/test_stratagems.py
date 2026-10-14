from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Condition, Effect


async def _create_detachment(client: AsyncClient, faction_id: int, name: str = "Gladius") -> int:
    response = await client.post(
        "/detachments", json={"name": name, "faction_id": faction_id, "dp": 2}
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_and_list_core_stratagem(client: AsyncClient):
    response = await client.post(
        "/stratagems",
        json={"name": "Command Re-roll", "description": "Re-roll one roll", "cp": 1, "is_core": True},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Command Re-roll"
    assert body["description"] == "Re-roll one roll"
    assert body["cp"] == 1
    assert body["is_core"] is True
    assert body["detachment_ids"] == []
    assert body["condition_ids"] == []
    assert body["effect_ids"] == []

    response = await client.get("/stratagems")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_stratagem_with_multiple_detachments(client: AsyncClient, faction_id: int):
    detachment_a = await _create_detachment(client, faction_id, "Gladius")
    detachment_b = await _create_detachment(client, faction_id, "Ironstorm")

    response = await client.post(
        "/stratagems",
        json={"name": "Armour of Contempt", "cp": 1, "detachment_ids": [detachment_a, detachment_b]},
    )
    assert response.status_code == 201
    assert sorted(response.json()["detachment_ids"]) == sorted([detachment_a, detachment_b])

    response = await client.get("/stratagems")
    assert sorted(response.json()[0]["detachment_ids"]) == sorted([detachment_a, detachment_b])


async def test_create_stratagem_with_conditions_and_effects(
    client: AsyncClient, session: AsyncSession
):
    condition = Condition(keyword="always", name="always", description=None)
    effect = Effect(keyword="reroll_failed_hits", name="reroll_failed_hits", description=None)
    session.add_all([condition, effect])
    await session.commit()

    response = await client.post(
        "/stratagems",
        json={
            "name": "Hit Rerolls",
            "cp": 1,
            "is_core": True,
            "condition_ids": [condition.id],
            "effect_ids": [effect.id],
        },
    )
    assert response.status_code == 201
    assert response.json()["condition_ids"] == [condition.id]
    assert response.json()["effect_ids"] == [effect.id]


async def test_create_non_core_stratagem_without_detachments_returns_422(client: AsyncClient):
    response = await client.post("/stratagems", json={"name": "Orphan", "cp": 1})
    assert response.status_code == 422


async def test_create_core_stratagem_with_detachments_returns_422(
    client: AsyncClient, faction_id: int
):
    detachment_id = await _create_detachment(client, faction_id)
    response = await client.post(
        "/stratagems",
        json={"name": "Bad", "cp": 1, "is_core": True, "detachment_ids": [detachment_id]},
    )
    assert response.status_code == 422


async def test_create_stratagem_with_negative_cp_returns_422(client: AsyncClient):
    response = await client.post("/stratagems", json={"name": "Bad", "cp": -1, "is_core": True})
    assert response.status_code == 422


async def test_create_stratagem_with_invalid_detachment_id_returns_400(client: AsyncClient):
    response = await client.post(
        "/stratagems", json={"name": "Bad", "cp": 1, "detachment_ids": [9999]}
    )
    assert response.status_code == 400


async def test_create_stratagem_with_invalid_condition_id_returns_400(client: AsyncClient):
    response = await client.post(
        "/stratagems", json={"name": "Bad", "cp": 1, "is_core": True, "condition_ids": [9999]}
    )
    assert response.status_code == 400


async def test_create_stratagem_with_invalid_effect_id_returns_400(client: AsyncClient):
    response = await client.post(
        "/stratagems", json={"name": "Bad", "cp": 1, "is_core": True, "effect_ids": [9999]}
    )
    assert response.status_code == 400


async def test_delete_stratagem(client: AsyncClient, faction_id: int):
    detachment_id = await _create_detachment(client, faction_id)
    stratagem_id = (
        await client.post(
            "/stratagems", json={"name": "Gone", "cp": 1, "detachment_ids": [detachment_id]}
        )
    ).json()["id"]

    response = await client.delete(f"/stratagems/{stratagem_id}")
    assert response.status_code == 204
    assert (await client.get("/stratagems")).json() == []


async def test_delete_nonexistent_stratagem_returns_404(client: AsyncClient):
    response = await client.delete("/stratagems/9999")
    assert response.status_code == 404


async def test_delete_detachment_unlinks_its_stratagems(client: AsyncClient, faction_id: int):
    detachment_a = await _create_detachment(client, faction_id, "Gladius")
    detachment_b = await _create_detachment(client, faction_id, "Ironstorm")
    await client.post(
        "/stratagems",
        json={"name": "Shared", "cp": 1, "detachment_ids": [detachment_a, detachment_b]},
    )

    response = await client.delete(f"/detachments/{detachment_a}")
    assert response.status_code == 204
    assert (await client.get("/stratagems")).json()[0]["detachment_ids"] == [detachment_b]
