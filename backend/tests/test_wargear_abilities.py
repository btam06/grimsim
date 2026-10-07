from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Condition, Effect


async def _create_condition(session: AsyncSession, keyword: str = "always") -> int:
    condition = Condition(keyword=keyword, name=keyword, description=None)
    session.add(condition)
    await session.commit()
    return condition.id


async def _create_effect(session: AsyncSession, keyword: str = "ignore_cover") -> int:
    effect = Effect(keyword=keyword, name=keyword, description=None)
    session.add(effect)
    await session.commit()
    return effect.id


async def test_create_and_list_wargear_ability(client: AsyncClient):
    response = await client.post(
        "/wargear-abilities",
        json={"name": "Ignores Cover", "description": "Negates the cover to-hit penalty"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Ignores Cover"
    assert body["description"] == "Negates the cover to-hit penalty"
    assert body["condition_ids"] == []
    assert body["effect_ids"] == []

    response = await client.get("/wargear-abilities")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_wargear_ability_without_description(client: AsyncClient):
    response = await client.post("/wargear-abilities", json={"name": "Camo Netting"})
    assert response.status_code == 201
    assert response.json()["description"] is None


async def test_create_wargear_ability_with_conditions_and_effects(
    client: AsyncClient, session: AsyncSession
):
    condition_id = await _create_condition(session)
    effect_id = await _create_effect(session)

    response = await client.post(
        "/wargear-abilities",
        json={
            "name": "Ignores Cover",
            "condition_ids": [condition_id],
            "effect_ids": [effect_id],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["condition_ids"] == [condition_id]
    assert body["effect_ids"] == [effect_id]

    response = await client.get("/wargear-abilities")
    assert response.json()[0]["condition_ids"] == [condition_id]
    assert response.json()[0]["effect_ids"] == [effect_id]


async def test_create_wargear_ability_with_invalid_condition_id_returns_400(client: AsyncClient):
    response = await client.post(
        "/wargear-abilities", json={"name": "Bad", "condition_ids": [9999]}
    )
    assert response.status_code == 400


async def test_create_wargear_ability_with_invalid_effect_id_returns_400(client: AsyncClient):
    response = await client.post(
        "/wargear-abilities", json={"name": "Bad", "effect_ids": [9999]}
    )
    assert response.status_code == 400
