import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DatasheetLoadout
from app.seeds import datasheets as datasheet_data
from app.seeds.factions import loadout_of

STATS = {"save": 4, "toughness": 3, "oc": 2, "movement": 6, "wounds": 1, "leadership": 7}


async def _model(client, faction_id, name, weapons, keywords=()):
    model = (await client.post("/models", json={**STATS, "name": name, "faction_id": faction_id})).json()
    ids = {}
    for weapon, melee, default in weapons:
        made = await client.post("/weapons", json={
            "name": weapon, "model_id": model["id"], "damage": "1", "attacks": "1", "skill": 4,
            "strength": 4, "ap": 0, "weapon_type": "melee" if melee else "ranged",
            "range": None if melee else 24, "is_default": default,
        })
        assert made.status_code == 201, made.text
        ids[weapon] = made.json()["id"]
    return model["id"], ids


async def _rangers(client: AsyncClient, session: AsyncSession, faction_id: int):
    # Skitarii Rangers, as the datasheet has them: 1 Alpha and 9 Rangers.
    alpha, alpha_weapons = await _model(client, faction_id, "Skitarii Ranger Alpha", [
        ("Galvanic rifle", False, False), ("Close combat weapon", True, False),
        ("Alpha combat weapon", True, False), ("Mechanicus pistol", False, False),
    ])
    ranger, weapons = await _model(client, faction_id, "Skitarii Ranger", [
        ("Galvanic rifle", False, False), ("Close combat weapon", True, False),
        ("Arc rifle", False, False), ("Plasma caliver – standard", False, False),
        ("Plasma caliver – supercharge", False, False), ("Transuranic arquebus", False, False),
    ])
    omnispex = (
        await client.post("/wargear", json={"name": "Omnispex", "model_id": ranger})
    ).json()["id"]
    unit_id = (
        await client.post("/faction-units", json={"name": "Skitarii Rangers", "faction_id": faction_id})
    ).json()["id"]
    loadout = ["Galvanic rifle", "Close combat weapon"]
    session.add(DatasheetLoadout(
        faction_unit_id=unit_id, models=["Skitarii Ranger Alpha", "Skitarii Ranger"],
        composition=[
            {"model": "Skitarii Ranger Alpha", "min": 1, "max": 1, "equipped": loadout},
            {"model": "Skitarii Ranger", "min": 9, "max": 9, "equipped": loadout},
        ],
        options=[
            {"model": "Skitarii Ranger Alpha", "with": [["Alpha combat weapon"]]},
            {"model": "Skitarii Ranger Alpha", "replace": ["Galvanic rifle"], "with": [["Mechanicus pistol"]]},
            {"model": "Skitarii Ranger", "replace": ["Galvanic rifle"], "with": [["Arc rifle"]], "max": 1},
            {"model": "Skitarii Ranger", "replace": ["Galvanic rifle"], "with": [["Plasma caliver"]], "max": 1},
            {"model": "Skitarii Ranger", "with": [["Omnispex"]], "requires": ["Galvanic rifle"], "max": 1},
        ],
    ))
    await session.commit()
    return unit_id, (alpha, alpha_weapons), (ranger, weapons, omnispex)


def _member(model_id, *weapon_ids, wargear=()):
    return {"model_id": model_id, "weapon_ids": list(weapon_ids), "wargear_ids": list(wargear)}


async def test_loadout_endpoint_resolves_the_datasheet(
    client: AsyncClient, session: AsyncSession, faction_id: int
):
    unit_id, (alpha, aw), (ranger, rw, omnispex) = await _rangers(client, session, faction_id)
    loadout = (await client.get(f"/faction-units/{unit_id}/loadout")).json()
    assert loadout["model_ids"] == [alpha, ranger] and not loadout["auto"]
    assert loadout["composition"][1] == {
        "model_id": ranger, "min": 9, "max": 9,
        "weapon_ids": [rw["Galvanic rifle"], rw["Close combat weapon"]], "wargear_ids": [],
    }
    plasma = loadout["options"][3]
    assert plasma["label"] == "Galvanic rifle → Plasma caliver"
    # (Both of its profiles.)
    assert sorted(plasma["choices"][0]["weapon_ids"]) == sorted(
        [rw["Plasma caliver – standard"], rw["Plasma caliver – supercharge"]]
    )
    assert plasma["replace"]["weapon_ids"] == [rw["Galvanic rifle"]] and plasma["max"] == 1


async def test_loadout_lists_every_way_to_equip_each_model_sergeant_first(
    client: AsyncClient, session: AsyncSession, faction_id: int
):
    unit_id, (alpha, aw), (ranger, rw, omnispex) = await _rangers(client, session, faction_id)
    # (The data lists the Rangers first; the Alpha is still first.)
    row = await session.get(DatasheetLoadout, unit_id)
    row.composition = list(reversed(row.composition))
    await session.commit()
    loadout = (await client.get(f"/faction-units/{unit_id}/loadout")).json()
    assert [p["model_id"] for p in loadout["composition"]] == [alpha, ranger]
    names = [v["name"] for v in loadout["variants"]]
    assert names == [
        "Skitarii Ranger Alpha — as equipped",
        "Skitarii Ranger Alpha — Alpha combat weapon",
        "Skitarii Ranger Alpha — Mechanicus pistol",
        "Skitarii Ranger Alpha — Alpha combat weapon, Mechanicus pistol",
        "Skitarii Ranger — as equipped",
        "Skitarii Ranger — Arc rifle",
        "Skitarii Ranger — Omnispex",
        "Skitarii Ranger — Plasma caliver",
    ]
    omni = loadout["variants"][names.index("Skitarii Ranger — Omnispex")]
    assert omni["wargear_ids"] == [omnispex]
    assert sorted(omni["weapon_ids"]) == sorted([rw["Galvanic rifle"], rw["Close combat weapon"]])
    assert len(omni["options"]) == 1


async def test_units_must_follow_the_composition_and_wargear_options(
    client: AsyncClient, session: AsyncSession, faction_id: int
):
    unit_id, (alpha, aw), (ranger, rw, omnispex) = await _rangers(client, session, faction_id)
    rifle, ccw = rw["Galvanic rifle"], rw["Close combat weapon"]
    plain = _member(ranger, rifle, ccw)
    alpha_model = _member(alpha, aw["Galvanic rifle"], aw["Close combat weapon"])

    async def post(members):
        return await client.post("/units", json={"faction_unit_id": unit_id, "unit_models": members})

    ok = await post([alpha_model, _member(ranger, rw["Arc rifle"], ccw),
                     _member(ranger, rifle, ccw, wargear=[omnispex]), *[plain] * 7])
    assert ok.status_code == 201, ok.text

    alpha_both = _member(alpha, aw["Mechanicus pistol"], aw["Close combat weapon"], aw["Alpha combat weapon"])
    assert (await post([alpha_both, *[plain] * 9])).status_code == 201

    cases = {
        "the unit needs 9 Skitarii Ranger (has 8)": [alpha_model, *[plain] * 8],
        "the unit needs 1 Skitarii Ranger Alpha (has 0)": [*[plain] * 9],
        # Only one arc rifle.
        "only 1 Skitarii Ranger can take Galvanic rifle → Arc rifle": [
            alpha_model, *[_member(ranger, rw["Arc rifle"], ccw)] * 2, *[plain] * 7
        ],
        # An omnispex bearer's galvanic rifle can't be replaced.
        "Skitarii Ranger: that wargear isn't one of its options": [
            alpha_model, _member(ranger, rw["Arc rifle"], ccw, wargear=[omnispex]), *[plain] * 8
        ],
    }
    for reason, members in cases.items():
        response = await post(members)
        assert response.status_code == 400 and response.json()["detail"] == reason, (reason, response.text)

    # Not one of the datasheet's models.
    other, _ = await _model(client, faction_id, "Servitor", [("Servo-arm", True, True)])
    response = await post([alpha_model, *[plain] * 9, _member(other)])
    assert response.json()["detail"] == "Servitor isn't one of this datasheet's models"


async def test_a_character_with_nothing_to_decide_is_added_automatically(
    client: AsyncClient, session: AsyncSession, faction_id: int
):
    marshal, weapons = await _model(client, faction_id, "Skitarii Marshal", [
        ("Control stave", True, True), ("Master-crafted radium serpenta", False, True),
    ])
    unit_id = (
        await client.post("/faction-units", json={"name": "Skitarii Marshal", "faction_id": faction_id})
    ).json()["id"]
    session.add(DatasheetLoadout(
        faction_unit_id=unit_id, models=["Skitarii Marshal"],
        composition=[{"model": "Skitarii Marshal", "min": 1, "max": 1, "equipped": None}],
        options=[],
    ))
    await session.commit()

    loadout = (await client.get(f"/faction-units/{unit_id}/loadout")).json()
    assert loadout["auto"]
    # (Its only way to be equipped: named just by the model.)
    assert [v["name"] for v in loadout["variants"]] == ["Skitarii Marshal"]
    made = await client.post("/units", json={"faction_unit_id": unit_id, "unit_models": []})
    assert made.status_code == 201, made.text
    [member] = made.json()["unit_models"]
    assert member["model_id"] == marshal
    assert sorted(member["weapon_ids"]) == sorted(weapons.values())


def _sheet(models, **extra):
    return {"name": "Sheet", "models": models, **extra}


def _spec(name, weapons=(), wargear=(), keywords=("CHARACTER",)):
    return {
        "name": name, **{k: v for k, v in STATS.items()}, "keywords": list(keywords),
        "weapons": [
            {"name": w, "weapon_type": "ranged", "range": 24, "attacks": "1", "skill": 4,
             "strength": 4, "ap": 0, "damage": "1", "default": default}
            for w, default in weapons
        ],
        "wargear": [{"name": g} for g in wargear],
    }


def test_loading_rejects_options_naming_what_a_model_has_not():
    sheet = _sheet(
        [_spec("Ranger", [("Galvanic rifle", True)])],
        wargear_options=[{"model": "Ranger", "replace": "Galvanic rifle", "with": ["Arc rifle"]}],
    )
    with pytest.raises(ValueError, match="no weapon or wargear 'Arc rifle'"):
        datasheet_data._datasheet(sheet)


def test_only_a_lone_character_with_no_choices_is_inferred():
    def composed(**spec):
        return loadout_of(datasheet_data._datasheet(_sheet([_spec("Hero", **spec)])))[0]

    assert composed(weapons=[("Sword", True)]) == [
        {"model": "Hero", "min": 1, "max": 1, "equipped": None}
    ]
    assert composed(weapons=[("Sword", True), ("Axe", False)]) == []
    assert composed(weapons=[("Sword", True)], wargear=["Shield"]) == []
    assert composed(weapons=[("Sword", True)], keywords=["INFANTRY"]) == []


def test_a_weapons_ranged_and_melee_profiles_are_one_weapon():
    from types import SimpleNamespace as NS

    from app.services.list_building import loadouts

    ranged = NS(id=1, name="Electrostatic gauntlets", weapon_type="ranged")
    melee = NS(id=2, name="Electrostatic gauntlets", weapon_type="melee")
    stubbers = [NS(id=3 + i, name="Heavy stubber", weapon_type="ranged") for i in range(2)]
    model = NS(weapons=[ranged, melee, *stubbers], wargear=[])
    assert loadouts.items_of([ranged, melee], []) == {"electrostaticgauntlets": 1}
    assert loadouts.items_of(stubbers, []) == {"heavystubber": 2}
    assert loadouts.ids_for(model, {"electrostaticgauntlets": 1}) == ([1, 2], [])
    assert loadouts.ids_for(model, {"heavystubber": 1}) == ([3], [])


async def test_options_that_dont_depend_on_each_other_are_picked_separately(
    client: AsyncClient, session: AsyncSession, faction_id: int
):
    # An Onager Dunecrawler: its beamer swap, an extra stubber and a
    # data-tether are three pickers, not 4 x 2 x 2 loadouts in one.
    crawler, weapons = await _model(client, faction_id, "Onager Dunecrawler", [
        ("Eradication beamer", False, False), ("Daedalus missile launcher", False, False),
        ("Icarus array", False, False), ("Neutron laser", False, False),
        ("Cognis heavy stubber", False, False), ("Twin Onager heavy phosphor blaster", False, False),
    ])
    tether = (
        await client.post("/wargear", json={"name": "Broad spectrum data-tether", "model_id": crawler})
    ).json()["id"]
    unit_id = (
        await client.post("/faction-units", json={"name": "Onager Dunecrawler", "faction_id": faction_id})
    ).json()["id"]
    session.add(DatasheetLoadout(
        faction_unit_id=unit_id, models=["Onager Dunecrawler"],
        composition=[{"model": "Onager Dunecrawler", "min": 1, "max": 1, "equipped": ["Eradication beamer"]}],
        options=[
            {"model": "Onager Dunecrawler", "replace": ["Eradication beamer"], "with": [
                ["Daedalus missile launcher", "Icarus array"], ["Neutron laser", "Cognis heavy stubber"],
                ["Twin Onager heavy phosphor blaster"],
            ]},
            {"model": "Onager Dunecrawler", "with": [["Cognis heavy stubber"]]},
            {"model": "Onager Dunecrawler", "with": [["Broad spectrum data-tether"]]},
        ],
    ))
    await session.commit()

    loadout = (await client.get(f"/faction-units/{unit_id}/loadout")).json()
    groups = {g["name"]: g for g in loadout["groups"]}
    assert set(groups) == {"Eradication beamer", "Cognis heavy stubber", "Broad spectrum data-tether"}
    assert groups["Eradication beamer"]["choices"][0] == "Eradication beamer"
    assert len(groups["Eradication beamer"]["choices"]) == 4
    assert groups["Broad spectrum data-tether"]["choices"] == ["None", "Broad spectrum data-tether"]
    assert len(loadout["variants"]) == 16

    # Neutron laser (with its stubber), plus the extra stubber, plus the tether.
    order = [g["name"] for g in loadout["groups"]]
    picks = [0] * 3
    picks[order.index("Eradication beamer")] = groups["Eradication beamer"]["choices"].index(
        "Cognis heavy stubber, Neutron laser"
    )
    picks[order.index("Cognis heavy stubber")] = 1
    picks[order.index("Broad spectrum data-tether")] = 1
    [variant] = [v for v in loadout["variants"] if v["picks"] == picks]
    assert variant["wargear_ids"] == [tether]
    assert weapons["Neutron laser"] in variant["weapon_ids"]
    assert weapons["Cognis heavy stubber"] in variant["weapon_ids"]
    assert weapons["Eradication beamer"] not in variant["weapon_ids"]
    made = await client.post("/units", json={"faction_unit_id": unit_id, "unit_models": [
        _member(crawler, *variant["weapon_ids"], wargear=variant["wargear_ids"]),
    ]})
    assert made.status_code == 201, made.text
