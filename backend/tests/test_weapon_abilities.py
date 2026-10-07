from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Condition, Effect


async def _create_condition(session: AsyncSession, keyword: str = "critical_hit") -> int:
    condition = Condition(keyword=keyword, name=keyword, description=None)
    session.add(condition)
    await session.commit()
    return condition.id


async def _create_effect(session: AsyncSession, keyword: str = "add_extra_hit") -> int:
    effect = Effect(keyword=keyword, name=keyword, description=None)
    session.add(effect)
    await session.commit()
    return effect.id


async def test_create_and_list_weapon_ability(client: AsyncClient):
    response = await client.post(
        "/weapon-abilities",
        json={"name": "Lethal Hits", "description": "Critical hits wound automatically"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Lethal Hits"
    assert body["description"] == "Critical hits wound automatically"
    assert body["condition_ids"] == []
    assert body["effect_ids"] == []

    response = await client.get("/weapon-abilities")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_weapon_ability_without_description(client: AsyncClient):
    response = await client.post("/weapon-abilities", json={"name": "Twin-linked"})
    assert response.status_code == 201
    assert response.json()["description"] is None


async def test_create_weapon_ability_with_conditions_and_effects(
    client: AsyncClient, session: AsyncSession
):
    condition_id = await _create_condition(session)
    effect_id = await _create_effect(session)

    response = await client.post(
        "/weapon-abilities",
        json={
            "name": "SUSTAINED 1",
            "condition_ids": [condition_id],
            "effect_ids": [effect_id],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["condition_ids"] == [condition_id]
    assert body["effect_ids"] == [effect_id]

    response = await client.get("/weapon-abilities")
    assert response.json()[0]["condition_ids"] == [condition_id]
    assert response.json()[0]["effect_ids"] == [effect_id]


async def test_create_weapon_ability_with_multiple_conditions_and_effects(
    client: AsyncClient, session: AsyncSession
):
    condition_a = await _create_condition(session, "critical_hit")
    condition_b = await _create_condition(session, "some_other_condition")
    effect_a = await _create_effect(session, "add_extra_hit")
    effect_b = await _create_effect(session, "auto_pass_wound")

    response = await client.post(
        "/weapon-abilities",
        json={
            "name": "Stacked",
            "condition_ids": [condition_a, condition_b],
            "effect_ids": [effect_a, effect_b],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body["condition_ids"]) == {condition_a, condition_b}
    assert set(body["effect_ids"]) == {effect_a, effect_b}


async def test_create_weapon_ability_with_invalid_condition_id_returns_400(client: AsyncClient):
    response = await client.post(
        "/weapon-abilities", json={"name": "Bad", "condition_ids": [9999]}
    )
    assert response.status_code == 400


async def test_create_weapon_ability_with_invalid_effect_id_returns_400(client: AsyncClient):
    response = await client.post("/weapon-abilities", json={"name": "Bad", "effect_ids": [9999]})
    assert response.status_code == 400


async def test_weapon_ability_can_be_attached_to_multiple_weapons(
    client: AsyncClient, faction_id: int
):
    model_response = await client.post(
        "/models",
        json={
            "name": "Intercessor",
            "faction_id": faction_id,
            "save": 3,
            "toughness": 4,
            "oc": 2,
            "movement": 6,
            "wounds": 2,
            "leadership": 7,
        },
    )
    model_id = model_response.json()["id"]

    ability_id = (
        await client.post("/weapon-abilities", json={"name": "Twin-linked"})
    ).json()["id"]

    def weapon_payload(name: str) -> dict:
        return {
            "name": name,
            "model_id": model_id,
            "damage": "1",
            "range": 24,
            "strength": 4,
            "ap": -1,
            "attacks": "2",
            "skill": 3,
            "ability_ids": [ability_id],
        }

    weapon_a_id = (
        await client.post("/weapons", json=weapon_payload("Bolt Rifle"))
    ).json()["id"]
    weapon_b_id = (
        await client.post("/weapons", json=weapon_payload("Bolt Pistol"))
    ).json()["id"]

    response = await client.get("/weapons")
    weapons_by_id = {w["id"]: w for w in response.json()}
    assert weapons_by_id[weapon_a_id]["ability_ids"] == [ability_id]
    assert weapons_by_id[weapon_b_id]["ability_ids"] == [ability_id]
