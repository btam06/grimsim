from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def test_create_and_list_faction_ability(client: AsyncClient, faction_id: int):
    response = await client.post(
        "/faction-abilities",
        json={
            "name": "Oath of Moment",
            "description": "Designate one enemy unit as the target of this Oath.",
            "faction_id": faction_id,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Oath of Moment"
    assert body["description"] == "Designate one enemy unit as the target of this Oath."
    assert body["faction_id"] == faction_id

    response = await client.get("/faction-abilities")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_faction_ability_without_description(client: AsyncClient, faction_id: int):
    response = await client.post(
        "/faction-abilities", json={"name": "Waaagh!", "faction_id": faction_id}
    )
    assert response.status_code == 201
    assert response.json()["description"] is None


async def test_create_faction_ability_with_invalid_faction_returns_400(client: AsyncClient):
    response = await client.post(
        "/faction-abilities", json={"name": "Oath of Moment", "faction_id": 9999}
    )
    assert response.status_code == 400


async def test_create_faction_ability_with_duplicate_name_in_faction_returns_400(
    client: AsyncClient, faction_id: int
):
    await client.post(
        "/faction-abilities", json={"name": "Oath of Moment", "faction_id": faction_id}
    )
    response = await client.post(
        "/faction-abilities", json={"name": "Oath of Moment", "faction_id": faction_id}
    )
    assert response.status_code == 400


async def test_delete_faction_ability(client: AsyncClient, faction_id: int):
    faction_ability_id = (
        await client.post(
            "/faction-abilities", json={"name": "Oath of Moment", "faction_id": faction_id}
        )
    ).json()["id"]

    response = await client.delete(f"/faction-abilities/{faction_ability_id}")
    assert response.status_code == 204

    response = await client.get("/faction-abilities")
    assert response.json() == []


async def test_delete_nonexistent_faction_ability_returns_404(client: AsyncClient):
    response = await client.delete("/faction-abilities/9999")
    assert response.status_code == 404


async def test_faction_ability_lists_its_rule_options(client: AsyncClient):
    faction_id = (await client.post("/factions", json={"name": "Adeptus Mechanicus"})).json()["id"]
    response = await client.post(
        "/faction-abilities", json={"name": "Doctrina Imperatives", "faction_id": faction_id}
    )
    assert response.json()["rule_options"] == ["Protector Imperative", "Conqueror Imperative"]

    response = await client.get("/faction-abilities")
    assert response.json()[0]["rule_options"] == ["Protector Imperative", "Conqueror Imperative"]


async def test_faction_ability_without_options_has_no_rule_options(
    client: AsyncClient, faction_id: int
):
    response = await client.post(
        "/faction-abilities", json={"name": "Oath of Moment", "faction_id": faction_id}
    )
    assert response.json()["rule_options"] == []


async def test_waaagh_lists_riled_up_rule_option(client: AsyncClient):
    faction_id = (await client.post("/factions", json={"name": "Orks"})).json()["id"]
    response = await client.post(
        "/faction-abilities", json={"name": "Waaagh!", "faction_id": faction_id}
    )
    assert response.json()["rule_options"] == ["Riled Up"]


async def test_faction_abilities_show_option_descriptions_and_notes(
    client: AsyncClient, session: AsyncSession
):
    from app.seeds import factions

    await factions.seed(session)
    await factions.seed_abilities(session)
    abilities = {a["name"]: a for a in (await client.get("/faction-abilities")).json()}

    doctrina = abilities["Doctrina Imperatives"]
    assert set(doctrina["rule_option_descriptions"]) == {
        "Protector Imperative",
        "Conqueror Imperative",
    }
    assert "[HEAVY]" in doctrina["rule_option_descriptions"]["Protector Imperative"]
    assert doctrina["calculator_notes"] == []
    assert "War Cry" in abilities["Waaagh!"]["calculator_notes"][0]
