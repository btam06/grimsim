import pytest
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


async def test_create_stratagem_with_required_keywords(client: AsyncClient):
    keyword_id = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]
    response = await client.post(
        "/stratagems",
        json={"name": "Epic Challenge", "cp": 1, "is_core": True, "keyword_ids": [keyword_id]},
    )
    assert response.status_code == 201
    assert response.json()["keyword_ids"] == [keyword_id]
    assert (await client.get("/stratagems")).json()[0]["keyword_ids"] == [keyword_id]


async def test_create_stratagem_defaults_to_no_required_keywords(client: AsyncClient):
    response = await client.post("/stratagems", json={"name": "Any", "cp": 1, "is_core": True})
    assert response.json()["keyword_ids"] == []


async def test_create_stratagem_with_invalid_keyword_id_returns_400(client: AsyncClient):
    response = await client.post(
        "/stratagems", json={"name": "Bad", "cp": 1, "is_core": True, "keyword_ids": [9999]}
    )
    assert response.status_code == 400


async def test_create_stratagem_with_a_game_action(client: AsyncClient):
    response = await client.post(
        "/stratagems",
        json={"name": "New Orders", "cp": 1, "is_core": True, "game_action": "replace_secondary"},
    )
    assert response.status_code == 201
    assert response.json()["game_action"] == "replace_secondary"
    assert (await client.get("/stratagems")).json()[0]["game_action"] == "replace_secondary"
    plain = await client.post("/stratagems", json={"name": "Plain", "cp": 1, "is_core": True})
    assert plain.json()["game_action"] is None
    bad = await client.post(
        "/stratagems", json={"name": "Bad", "cp": 1, "is_core": True, "game_action": "explode"}
    )
    assert bad.status_code == 422


async def test_create_stratagem_with_a_combat_side(client: AsyncClient):
    response = await client.post(
        "/stratagems",
        json={"name": "Bulwark", "cp": 2, "is_core": True, "combat_side": "defender"},
    )
    assert response.status_code == 201
    assert response.json()["combat_side"] == "defender"
    assert (await client.get("/stratagems")).json()[0]["combat_side"] == "defender"
    plain = await client.post("/stratagems", json={"name": "Plain", "cp": 1, "is_core": True})
    assert plain.json()["combat_side"] is None
    bad = await client.post(
        "/stratagems", json={"name": "Bad", "cp": 1, "is_core": True, "combat_side": "both"}
    )
    assert bad.status_code == 422


async def test_create_stratagem_with_excluded_keywords(client: AsyncClient):
    keyword_id = (await client.post("/keywords", json={"name": "VEHICLE"})).json()["id"]
    response = await client.post(
        "/stratagems",
        json={"name": "Halo", "cp": 2, "is_core": True, "excluded_keyword_ids": [keyword_id]},
    )
    assert response.status_code == 201
    assert response.json()["excluded_keyword_ids"] == [keyword_id]
    assert response.json()["keyword_ids"] == []
    assert (await client.get("/stratagems")).json()[0]["excluded_keyword_ids"] == [keyword_id]


async def test_create_stratagem_with_invalid_excluded_keyword_id_returns_400(client: AsyncClient):
    response = await client.post(
        "/stratagems",
        json={"name": "Bad", "cp": 1, "is_core": True, "excluded_keyword_ids": [9999]},
    )
    assert response.status_code == 400


async def test_create_stratagem_requiring_and_excluding_a_keyword_returns_400(
    client: AsyncClient,
):
    keyword_id = (await client.post("/keywords", json={"name": "VEHICLE"})).json()["id"]
    response = await client.post(
        "/stratagems",
        json={
            "name": "Bad",
            "cp": 1,
            "is_core": True,
            "keyword_ids": [keyword_id],
            "excluded_keyword_ids": [keyword_id],
        },
    )
    assert response.status_code == 400


async def test_delete_keyword_unlinks_it_from_stratagems(client: AsyncClient):
    required = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]
    excluded = (await client.post("/keywords", json={"name": "VEHICLE"})).json()["id"]
    await client.post(
        "/stratagems",
        json={
            "name": "Halo",
            "cp": 1,
            "is_core": True,
            "keyword_ids": [required],
            "excluded_keyword_ids": [excluded],
        },
    )
    assert (await client.delete(f"/keywords/{required}")).status_code == 204
    assert (await client.delete(f"/keywords/{excluded}")).status_code == 204
    stratagem = (await client.get("/stratagems")).json()[0]
    assert (stratagem["keyword_ids"], stratagem["excluded_keyword_ids"]) == ([], [])


async def test_create_stratagem_with_keyword_options(client: AsyncClient):
    a = (await client.post("/keywords", json={"name": "SKITARII"})).json()["id"]
    b = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]
    c = (await client.post("/keywords", json={"name": "SICARIAN"})).json()["id"]
    response = await client.post(
        "/stratagems",
        json={"name": "Withdraw", "cp": 1, "is_core": True, "keyword_option_ids": [[c], [a, b]]},
    )
    assert response.status_code == 201, response.text
    # Options keep their order; the keywords within one are a set.
    for stratagem in (response.json(), (await client.get("/stratagems")).json()[0]):
        assert [set(o) for o in stratagem["keyword_option_ids"]] == [{c}, {a, b}]


@pytest.mark.parametrize("options", [[[]], [[9999]]])
async def test_create_stratagem_with_bad_keyword_options_returns_400(client: AsyncClient, options):
    response = await client.post(
        "/stratagems",
        json={"name": "Bad", "cp": 1, "is_core": True, "keyword_option_ids": options},
    )
    assert response.status_code == 400


async def test_delete_keyword_removes_it_from_keyword_options(client: AsyncClient):
    keyword = (await client.post("/keywords", json={"name": "SICARIAN"})).json()["id"]
    await client.post(
        "/stratagems",
        json={"name": "Bionic", "cp": 1, "is_core": True, "keyword_option_ids": [[keyword]]},
    )
    assert (await client.delete(f"/keywords/{keyword}")).status_code == 204
    assert (await client.get("/stratagems")).json()[0]["keyword_option_ids"] == []
