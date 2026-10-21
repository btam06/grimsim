import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.seeds import conditions as conditions_seed
from app.seeds import data_files
from app.seeds import datasheet_abilities as datasheet_abilities_seed
from app.seeds import effects as effects_seed
from app.seeds import factions as faction_seeds
from app.seeds import run_all


async def _keyword(client: AsyncClient, name: str) -> int:
    existing = {k["name"]: k["id"] for k in (await client.get("/keywords")).json()}
    if name in existing:
        return existing[name]
    return (await client.post("/keywords", json={"name": name})).json()["id"]


async def _model(client: AsyncClient, faction_id: int, name: str, *keywords: str) -> int:
    response = await client.post(
        "/models",
        json={
            "name": name,
            "faction_id": faction_id,
            "save": 3,
            "toughness": 4,
            "oc": 1,
            "movement": 6,
            "wounds": 4,
            "leadership": 6,
            "keyword_ids": [await _keyword(client, k) for k in keywords],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _detachment(client: AsyncClient, faction_id: int, name: str) -> int:
    response = await client.post(
        "/detachments", json={"name": name, "faction_id": faction_id, "dp": 1}
    )
    return response.json()["id"]


async def _enhancement(client: AsyncClient, detachment_id: int, name: str, kind: str, **extra):
    response = await client.post(
        "/enhancements",
        json={"name": name, "points": 15, "kind": kind, "detachment_id": detachment_id, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _list(client: AsyncClient, faction_id: int, detachment_ids: list[int]) -> int:
    response = await client.post(
        "/lists",
        json={
            "name": "List",
            "points_limit": 2000,
            "faction_id": faction_id,
            "detachment_ids": detachment_ids,
        },
    )
    return response.json()["id"]


async def _faction_unit(client: AsyncClient, faction_id: int) -> int:
    response = await client.post("/faction-units", json={"name": "Unit", "faction_id": faction_id})
    return response.json()["id"]


async def _unit(client: AsyncClient, faction_unit_id: int, list_id, models, upgrade_id=None):
    # `models`: [(model_id, enhancement_id or None)].
    return await client.post(
        "/units",
        json={
            "faction_unit_id": faction_unit_id,
            "points": 100,
            "list_id": list_id,
            "upgrade_id": upgrade_id,
            "unit_models": [
                {"model_id": model_id, "enhancement_id": enhancement_id}
                for model_id, enhancement_id in models
            ],
        },
    )


@pytest.fixture
async def army(client: AsyncClient, faction_id: int):
    # A list with the "Mine" detachment, its enhancements and upgrades, and
    # models to put them on.
    mine = await _detachment(client, faction_id, "Mine")
    other = await _detachment(client, faction_id, "Other")
    return {
        "mine": mine,
        "list": await _list(client, faction_id, [mine]),
        "faction_unit": await _faction_unit(client, faction_id),
        "relic": await _enhancement(client, mine, "Relic", "enhancement"),
        "skitarii_relic": await _enhancement(
            client,
            mine,
            "Skitarii Relic",
            "enhancement",
            keyword_ids=[await _keyword(client, "SKITARII")],
        ),
        "other_relic": await _enhancement(client, other, "Other Relic", "enhancement"),
        "drill": await _enhancement(
            client,
            mine,
            "Drill",
            "upgrade",
            excluded_keyword_ids=[await _keyword(client, "VEHICLE")],
        ),
        "hero": await _model(client, faction_id, "Hero", "CHARACTER", "INFANTRY"),
        "skitarii_hero": await _model(client, faction_id, "Alpha", "CHARACTER", "SKITARII"),
        "epic": await _model(client, faction_id, "Cawl", "CHARACTER", "EPIC HERO"),
        "trooper": await _model(client, faction_id, "Trooper", "INFANTRY"),
        "tank": await _model(client, faction_id, "Tank", "VEHICLE"),
    }


async def test_create_and_list_enhancements(client: AsyncClient, army):
    enhancements = (await client.get("/enhancements")).json()
    assert {e["name"]: e["kind"] for e in enhancements} == {
        "Relic": "enhancement",
        "Skitarii Relic": "enhancement",
        "Other Relic": "enhancement",
        "Drill": "upgrade",
    }
    relic = next(e for e in enhancements if e["name"] == "Relic")
    assert (relic["points"], relic["detachment_id"]) == (15, army["mine"])


@pytest.mark.parametrize(
    "overrides",
    [{"kind": "relic"}, {"points": -1}, {"detachment_id": 9999}, {"keyword_ids": [9999]}],
)
async def test_create_enhancement_rejects_bad_input(client: AsyncClient, army, overrides):
    payload = {"name": "Bad", "points": 10, "kind": "enhancement", "detachment_id": army["mine"]}
    response = await client.post("/enhancements", json={**payload, **overrides})
    assert response.status_code in (400, 422)


async def _available(client, army, model, unit_id=None) -> set[str]:
    params = {"list_id": army["list"], "model_id": army[model]}
    if unit_id is not None:
        params["unit_id"] = unit_id
    response = await client.get("/enhancements/available", params=params)
    assert response.status_code == 200
    return {e["name"] for e in response.json()}


async def _available_upgrades(client, army, *models) -> set[str]:
    response = await client.get(
        "/enhancements/available-upgrades",
        params={"list_id": army["list"], "model_ids": [army[m] for m in models]},
    )
    assert response.status_code == 200
    return {e["name"] for e in response.json()}


async def test_enhancements_are_offered_to_applicable_characters_only(client, army):
    assert await _available(client, army, "hero") == {"Relic"}
    assert await _available(client, army, "skitarii_hero") == {"Relic", "Skitarii Relic"}
    assert await _available(client, army, "epic") == set()  # EPIC HEROes can't
    assert await _available(client, army, "trooper") == set()  # not a CHARACTER


async def test_upgrades_are_offered_to_applicable_units_only(client, army):
    assert await _available_upgrades(client, army, "trooper", "trooper") == {"Drill"}
    assert await _available_upgrades(client, army, "trooper", "tank") == set()
    assert await _available_upgrades(client, army) == set()


async def test_unit_with_an_enhancement_and_an_upgrade(client: AsyncClient, army):
    response = await _unit(
        client,
        army["faction_unit"],
        army["list"],
        [(army["hero"], army["relic"]), (army["trooper"], None)],
        upgrade_id=army["drill"],
    )
    assert response.status_code == 201, response.text
    unit = response.json()
    assert [um["enhancement_id"] for um in unit["unit_models"]] == [army["relic"], None]
    assert unit["upgrade_id"] == army["drill"]
    listed = next(u for u in (await client.get("/units")).json() if u["id"] == unit["id"])
    assert listed["upgrade_id"] == army["drill"]
    assert listed["unit_models"][0]["enhancement_id"] == army["relic"]


@pytest.mark.parametrize(
    "models,upgrade,message",
    [
        ([("trooper", "relic")], None, "CHARACTER"),
        ([("epic", "relic")], None, "EPIC HERO"),
        ([("hero", "skitarii_relic")], None, "SKITARII"),
        ([("hero", "other_relic")], None, "detachment"),
        ([("hero", "drill")], None, "upgrade"),
        ([("tank", None)], "drill", "VEHICLE"),
        ([("hero", None)], "relic", "enhancement"),
        ([("skitarii_hero", "relic"), ("skitarii_hero", "relic")], None, "once"),
    ],
)
async def test_unit_rejects_inapplicable_enhancements(
    client: AsyncClient, army, models, upgrade, message
):
    response = await _unit(
        client,
        army["faction_unit"],
        army["list"],
        [(army[m], army[e] if e else None) for m, e in models],
        upgrade_id=army[upgrade] if upgrade else None,
    )
    assert response.status_code == 400
    assert message in response.json()["detail"]


async def test_unit_outside_a_list_cannot_take_enhancements(client: AsyncClient, army):
    response = await _unit(client, army["faction_unit"], None, [(army["hero"], army["relic"])])
    assert response.status_code == 400


async def test_each_enhancement_once_per_list(client: AsyncClient, army):
    first = await _unit(
        client, army["faction_unit"], army["list"], [(army["hero"], army["relic"])]
    )
    assert first.status_code == 201
    second = await _unit(
        client, army["faction_unit"], army["list"], [(army["hero"], army["relic"])]
    )
    assert second.status_code == 400
    assert "already taken" in second.json()["detail"]
    # ...and it's no longer offered, except to the unit that has it.
    assert await _available(client, army, "hero") == set()
    assert await _available(client, army, "hero", unit_id=first.json()["id"]) == {"Relic"}


async def test_editing_a_unit_keeps_its_own_enhancement(client: AsyncClient, army):
    unit = (
        await _unit(client, army["faction_unit"], army["list"], [(army["hero"], army["relic"])])
    ).json()
    response = await client.put(
        f"/units/{unit['id']}",
        json={
            "faction_unit_id": army["faction_unit"],
            "points": 120,
            "list_id": army["list"],
            "unit_models": [{"model_id": army["hero"], "enhancement_id": army["relic"]}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["unit_models"][0]["enhancement_id"] == army["relic"]


async def test_delete_enhancement_takes_it_off_units(client: AsyncClient, army):
    unit = (
        await _unit(
            client,
            army["faction_unit"],
            army["list"],
            [(army["hero"], army["relic"])],
            upgrade_id=army["drill"],
        )
    ).json()
    assert (await client.delete(f"/enhancements/{army['relic']}")).status_code == 204
    assert (await client.delete(f"/enhancements/{army['drill']}")).status_code == 204
    listed = next(u for u in (await client.get("/units")).json() if u["id"] == unit["id"])
    assert listed["upgrade_id"] is None
    assert listed["unit_models"][0]["enhancement_id"] is None


async def test_delete_detachment_deletes_its_enhancements(client: AsyncClient, faction_id: int):
    detachment = await _detachment(client, faction_id, "Short-lived")
    await _enhancement(client, detachment, "Gone", "enhancement")
    assert (await client.delete(f"/detachments/{detachment}")).status_code == 204
    assert (await client.get("/enhancements")).json() == []


async def test_delete_unit_with_enhancements(client: AsyncClient, army):
    unit = (
        await _unit(
            client,
            army["faction_unit"],
            army["list"],
            [(army["hero"], army["relic"])],
            upgrade_id=army["drill"],
        )
    ).json()
    assert (await client.delete(f"/units/{unit['id']}")).status_code == 204
    assert await _available(client, army, "hero") == {"Relic"}


# --- seeding, from factions/<faction>/enhancements.json ---


async def test_seed_enhancements_from_data_file(
    session: AsyncSession, client: AsyncClient, fixture_game_data
):
    await run_all(session)
    await run_all(session)  # idempotent
    enhancements = (await client.get("/enhancements")).json()
    assert {(e["name"], e["kind"], e["points"]) for e in enhancements} == {
        ("Test Kustom Job", "enhancement", 20),
        ("Test Boarding Gear", "upgrade", 10),
    }
    keywords = {k["id"]: k["name"] for k in (await client.get("/keywords")).json()}
    gear = next(e for e in enhancements if e["name"] == "Test Boarding Gear")
    assert [keywords[i] for i in gear["keyword_ids"]] == ["INFANTRY"]

    weapon_abilities = {
        a["id"]: a["name"] for a in (await client.get("/weapon-abilities")).json()
    }
    datasheet_abilities = {
        a["id"]: a["name"] for a in (await client.get("/datasheet-abilities")).json()
    }
    job = next(e for e in enhancements if e["name"] == "Test Kustom Job")
    assert [
        (weapon_abilities[g["weapon_ability_id"]], g["weapon_type"], g["scope"])
        for g in job["weapon_abilities"]
    ] == [("Sustained 1", "ranged", "led_unit")]
    assert [
        (datasheet_abilities[g["datasheet_ability_id"]], g["scope"])
        for g in job["datasheet_abilities"]
    ] == [("Stealth", "bearer")]
    assert gear["weapon_abilities"] == gear["datasheet_abilities"] == []
    [shoota] = job["weapons"]
    assert (shoota["name"], shoota["attacks"], shoota["skill"]) == ("Test Shoota", "2", 5)
    assert [weapon_abilities[i] for i in shoota["ability_ids"]] == ["Sustained 1"]
    assert [(keywords[g["keyword_id"]], g["scope"]) for g in job["granted_keywords"]] == [
        ("GRENADES", "bearer")
    ]


async def test_seed_fills_in_weapons_and_keywords_on_an_existing_enhancement(
    session: AsyncSession, client: AsyncClient, fixture_game_data
):
    from sqlalchemy import select

    from app.models import Enhancement

    await run_all(session)
    job = (
        await session.execute(select(Enhancement).where(Enhancement.name == "Test Kustom Job"))
    ).scalar_one()
    job.weapons = []
    job.keyword_grants = []
    await session.commit()

    await run_all(session)
    enhancements = (await client.get("/enhancements")).json()
    job = next(e for e in enhancements if e["name"] == "Test Kustom Job")
    assert [w["name"] for w in job["weapons"]] == ["Test Shoota"]
    assert len(job["granted_keywords"]) == 1


@pytest.mark.parametrize(
    "entry,message",
    [
        ({"detachment": "Mob", "kind": "relic"}, "unknown kind"),
        ({"detachment": "Nope", "kind": "enhancement"}, "unknown detachment"),
        ({"detachment": "Mob", "kind": "enhancement", "keywords": ["NOPE"]}, "unknown keyword"),
        (
            {
                "detachment": "Mob",
                "kind": "enhancement",
                "weapon_abilities": [{"name": "Nope", "scope": "bearer"}],
            },
            "unknown weapon ability",
        ),
        (
            {
                "detachment": "Mob",
                "kind": "upgrade",
                "datasheet_abilities": [{"name": "Stealth", "scope": "bearer"}],
            },
            "scope 'bearer'",
        ),
    ],
)
async def test_seed_enhancements_rejects_bad_entries(
    session: AsyncSession, tmp_path, monkeypatch, entry, message
):
    import json

    folder = tmp_path / "factions" / "orks"
    folder.mkdir(parents=True)
    (folder / "detachments.json").write_text(
        json.dumps(
            {"faction": "Orks", "detachments": [{"name": "Mob", "dp": 1, "dispositions": []}]}
        )
    )
    (folder / "enhancements.json").write_text(
        json.dumps({"faction": "Orks", "enhancements": [{"name": "Bad", "points": 5, **entry}]})
    )
    monkeypatch.setattr(data_files, "DATA_DIR", tmp_path)
    await faction_seeds.seed(session)
    await faction_seeds.seed_detachments(session)
    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await datasheet_abilities_seed.seed(session)
    with pytest.raises(ValueError, match=message):
        await faction_seeds.seed_enhancements(session)


async def test_create_enhancement_with_granted_abilities(client: AsyncClient, army, session):
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)
    await datasheet_abilities_seed.seed(session)
    sustained = next(
        a["id"]
        for a in (await client.get("/weapon-abilities")).json()
        if a["name"] == "Sustained 1"
    )
    stealth = next(
        a["id"]
        for a in (await client.get("/datasheet-abilities")).json()
        if a["name"] == "Stealth"
    )
    grants = {
        "weapon_abilities": [
            {"weapon_ability_id": sustained, "weapon_type": "ranged", "scope": "led_unit"}
        ],
        "datasheet_abilities": [{"datasheet_ability_id": stealth, "scope": "bearer"}],
    }
    response = await client.post(
        "/enhancements",
        json={
            "name": "Eradicator",
            "points": 20,
            "kind": "enhancement",
            "detachment_id": army["mine"],
            **grants,
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert {k: created[k] for k in grants} == grants
    enhancements = (await client.get("/enhancements")).json()
    listed = next(e for e in enhancements if e["id"] == created["id"])
    assert {k: listed[k] for k in grants} == grants

    # An enhancement can't reach "unit", nor an upgrade "bearer"/"led_unit".
    for kind, scope in [("enhancement", "unit"), ("upgrade", "bearer"), ("upgrade", "led_unit")]:
        bad = await client.post(
            "/enhancements",
            json={
                "name": "Bad",
                "points": 1,
                "kind": kind,
                "detachment_id": army["mine"],
                "datasheet_abilities": [{"datasheet_ability_id": stealth, "scope": scope}],
            },
        )
        assert bad.status_code == 422, (kind, scope)
    missing = await client.post(
        "/enhancements",
        json={
            "name": "Bad",
            "points": 1,
            "kind": "enhancement",
            "detachment_id": army["mine"],
            "weapon_abilities": [{"weapon_ability_id": 9999, "scope": "bearer"}],
        },
    )
    assert missing.status_code == 400


async def test_enhancement_with_a_weapon_and_granted_keywords(
    client: AsyncClient, army, session: AsyncSession
):
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)
    hazardous = next(
        a["id"]
        for a in (await client.get("/weapon-abilities")).json()
        if a["name"] == "Hazardous"
    )
    skitarii = await _keyword(client, "SKITARII")
    weapon = {
        "name": "TL-4Ø9",
        "weapon_type": "ranged",
        "range": 24,
        "attacks": "3",
        "skill": 2,
        "strength": 11,
        "ap": -2,
        "damage": "D3+2",
        "ability_ids": [hazardous],
    }
    response = await client.post(
        "/enhancements",
        json={
            "name": "Casket",
            "points": 30,
            "kind": "enhancement",
            "detachment_id": army["mine"],
            "weapons": [weapon],
            "granted_keywords": [{"keyword_id": skitarii, "scope": "bearers_unit"}],
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    [out] = created["weapons"]
    assert {k: out[k] for k in weapon} == weapon
    assert created["granted_keywords"] == [{"keyword_id": skitarii, "scope": "bearers_unit"}]

    # An upgrade can't give a weapon; scopes follow the kind; ids must exist.
    for bad in (
        {"kind": "upgrade", "weapons": [weapon]},
        {"granted_keywords": [{"keyword_id": skitarii, "scope": "unit"}]},
        {"weapons": [{**weapon, "attacks": "lots"}]},
    ):
        payload = {
            "name": "Bad",
            "points": 1,
            "kind": "enhancement",
            "detachment_id": army["mine"],
            **bad,
        }
        assert (await client.post("/enhancements", json=payload)).status_code == 422, bad
    for bad in (
        {"granted_keywords": [{"keyword_id": 9999, "scope": "bearer"}]},
        {"weapons": [{**weapon, "ability_ids": [9999]}]},
    ):
        payload = {
            "name": "Bad",
            "points": 1,
            "kind": "enhancement",
            "detachment_id": army["mine"],
            **bad,
        }
        assert (await client.post("/enhancements", json=payload)).status_code == 400, bad

    # Deleting it removes its weapon too.
    assert (await client.delete(f"/enhancements/{created['id']}")).status_code == 204


async def test_combat_endpoint_fires_a_selected_enhancement_weapon(
    client: AsyncClient, army, monkeypatch
):
    from app.services import combat

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    casket = await client.post(
        "/enhancements",
        json={
            "name": "Casket",
            "points": 30,
            "kind": "enhancement",
            "detachment_id": army["mine"],
            "weapons": [
                {
                    "name": "TL-4Ø9",
                    "weapon_type": "ranged",
                    "range": 24,
                    "attacks": "3",
                    "skill": 2,
                    "strength": 11,
                    "ap": -2,
                    "damage": "1",
                }
            ],
        },
    )
    casket = casket.json()
    attacker = await _unit(
        client, army["faction_unit"], army["list"], [(army["hero"], casket["id"])]
    )
    assert attacker.status_code == 201, attacker.text
    target = await _unit(client, army["faction_unit"], army["list"], [(army["trooper"], None)])
    request = {
        "attacking_unit_id": attacker.json()["id"],
        "defending_unit_id": target.json()["id"],
        "selected_weapon_ids": [],
        "selected_enhancement_weapon_ids": [casket["weapons"][0]["id"]],
    }
    response = await client.post("/combat", json=request)
    assert response.status_code == 200, response.text
    assert [w["name"] for w in response.json()["weapon_results"]] == ["TL-4Ø9"]
    assert len(response.json()["attack_rolls"]) == 3

    # Not the attacking unit's.
    request["selected_enhancement_weapon_ids"] = [9999]
    assert (await client.post("/combat", json=request)).status_code == 400
