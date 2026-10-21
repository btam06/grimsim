import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules import Rule
from app.models import (
    Condition,
    DatasheetAbility,
    DetachmentRule,
    DetachmentRuleDatasheetAbility,
    DetachmentRuleWeaponAbility,
    Effect,
    Keyword,
    Model,
    Unit,
    UnitModel,
    Weapon,
    WeaponAbility,
)
from app.seeds import conditions as conditions_seed
from app.seeds import data_files
from app.seeds import datasheet_abilities as datasheet_abilities_seed
from app.seeds import effects as effects_seed
from app.seeds import factions as faction_seeds
from app.seeds import run_all
from app.seeds import weapon_abilities as weapon_abilities_seed
from app.services import combat
from app.services import detachment_rules

# --- which units a rule reaches ---


def _unit(*model_keywords: tuple[str, ...]) -> Unit:
    unit = Unit(faction_unit_id=1, points=0)
    unit.unit_models = []
    for keywords in model_keywords:
        model = Model(
            name="M", faction_id=1, save=4, toughness=4, oc=1, movement=6, wounds=1, leadership=7
        )
        model.keywords = [Keyword(name=k) for k in keywords]
        model.abilities = []
        unit_model = UnitModel(unit_id=1, model_id=1)
        unit_model.model = model
        unit_model.weapons = []
        unit_model.wargear = []
        unit.unit_models.append(unit_model)
    return unit


def _rule(*options: tuple[str, ...]) -> DetachmentRule:
    rule = DetachmentRule(detachment_id=1, name="Rule")
    rule.keyword_options = [[Keyword(name=k) for k in option] for option in options]
    rule.weapon_ability_grants = []
    rule.datasheet_ability_grants = []
    return rule


STEALTH_OPTIMISATION = (("SKITARII", "INFANTRY"), ("SKITARII", "MOUNTED"), ("IRONSTRIDER",))


@pytest.mark.parametrize(
    "models,reached",
    [
        ([("SKITARII", "INFANTRY")], True),
        ([("INFANTRY", "SKITARII", "BATTLELINE")], True),  # keywords are a set
        ([("SKITARII", "MOUNTED")], True),
        ([("IRONSTRIDER", "VEHICLE")], True),
        ([("SKITARII", "VEHICLE")], False),
        ([("INFANTRY",)], False),  # needs both SKITARII and INFANTRY
        # A Tech-priest leading Skitarii isn't SKITARII: the unit isn't reached.
        ([("CHARACTER", "INFANTRY"), ("SKITARII", "INFANTRY")], False),
        # Every model matching some option is enough.
        ([("SKITARII", "INFANTRY"), ("SKITARII", "MOUNTED")], True),
        ([], False),
    ],
)
def test_rule_reaches_units_whose_every_model_matches_an_option(models, reached):
    rule = _rule(*STEALTH_OPTIMISATION)
    assert detachment_rules.applies_to(rule, _unit(*models)) is reached


def test_rule_without_options_reaches_every_unit():
    assert detachment_rules.applies_to(_rule(), _unit(("ANYTHING",)))


def test_rule_grants_weapon_abilities_in_combat(monkeypatch):
    # +1 to hit on ranged weapons for INFANTRY units: a 3 hits against BS4.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)
    plus_one = WeaponAbility(name="+1", description=None)
    plus_one.conditions = [Condition(keyword="always", name="always", description=None)]
    plus_one.effects = [Effect(keyword="plus_one_to_hit", name="+1", description=None)]
    rule = _rule(("INFANTRY",))
    rule.weapon_ability_grants = [
        DetachmentRuleWeaponAbility(weapon_ability=plus_one, weapon_type="ranged")
    ]

    def damage(attacker_keywords, rules):
        attacker = _unit(attacker_keywords)
        gun = Weapon(
            name="Gun",
            model_id=1,
            damage="1",
            range=24,
            strength=10,
            ap=-10,
            attacks="1",
            skill=4,
            weapon_type="ranged",
        )
        gun.id = 1
        gun.abilities = []
        attacker.unit_models[0].weapons = [gun]
        defender = _unit(("INFANTRY",))
        target = defender.unit_models[0].model
        target.toughness, target.wounds, target.save = 1, 10, 7
        return combat.resolve_combat(
            attacker,
            defender,
            {1},
            in_engagement_range=False,
            visible=True,
            in_range=True,
            in_cover=False,
            half_range=False,
            moved_less_than_3=False,
            advanced=False,
            attacker_detachment_rules=rules,
        ).total_damage

    assert damage(("INFANTRY",), [rule]) == 1
    assert damage(("INFANTRY",), []) == 0
    assert damage(("VEHICLE",), [rule]) == 0  # not reached


def test_rule_grants_datasheet_abilities():
    stealth = DatasheetAbility(name="Stealth", description=None)
    rule = _rule(("INFANTRY",))
    rule.datasheet_ability_grants = [DetachmentRuleDatasheetAbility(datasheet_ability=stealth)]
    assert detachment_rules.granted_datasheet_abilities([rule], _unit(("INFANTRY",))) == [
        stealth
    ]
    assert detachment_rules.granted_datasheet_abilities([rule], _unit(("VEHICLE",))) == []


# --- API ---


async def _seed_abilities(session: AsyncSession):
    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)
    await datasheet_abilities_seed.seed(session)


async def _id(client: AsyncClient, path: str, name: str) -> int:
    return next(row["id"] for row in (await client.get(path)).json() if row["name"] == name)


async def _detachment(client: AsyncClient, faction_id: int, name: str = "Hunters") -> int:
    response = await client.post(
        "/detachments", json={"name": name, "faction_id": faction_id, "dp": 2}
    )
    return response.json()["id"]


async def test_create_list_and_delete_detachment_rule(
    client: AsyncClient, faction_id: int, session: AsyncSession
):
    await _seed_abilities(session)
    detachment = await _detachment(client, faction_id)
    skitarii = (await client.post("/keywords", json={"name": "SKITARII"})).json()["id"]
    infantry = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]
    stealth = await _id(client, "/datasheet-abilities", "Stealth")
    sustained = await _id(client, "/weapon-abilities", "Sustained 1")
    payload = {
        "detachment_id": detachment,
        "name": "Stealth Optimisation",
        "description": "Stealth for Skitarii.",
        "keyword_option_ids": [[skitarii, infantry]],
        "weapon_abilities": [{"weapon_ability_id": sustained, "weapon_type": "ranged"}],
        "datasheet_ability_ids": [stealth],
    }
    response = await client.post("/detachment-rules", json=payload)
    assert response.status_code == 201, response.text
    listed = (await client.get("/detachment-rules")).json()
    assert len(listed) == 1
    for rule in (response.json(), listed[0]):
        assert [set(o) for o in rule["keyword_option_ids"]] == [{skitarii, infantry}]
        assert rule["weapon_abilities"] == payload["weapon_abilities"]
        assert rule["datasheet_ability_ids"] == [stealth]

    assert (await client.delete(f"/detachment-rules/{listed[0]['id']}")).status_code == 204
    assert (await client.get("/detachment-rules")).json() == []
    assert (await client.delete(f"/detachment-rules/{listed[0]['id']}")).status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"detachment_id": 9999},
        {"keyword_option_ids": [[]]},
        {"keyword_option_ids": [[9999]]},
        {"datasheet_ability_ids": [9999]},
        {"weapon_abilities": [{"weapon_ability_id": 9999}]},
    ],
)
async def test_create_detachment_rule_rejects_bad_input(
    client: AsyncClient, faction_id: int, overrides
):
    detachment = await _detachment(client, faction_id)
    payload = {"detachment_id": detachment, "name": "Bad", **overrides}
    assert (await client.post("/detachment-rules", json=payload)).status_code == 400


async def test_deleting_detachment_or_keyword_cleans_up_rules(
    client: AsyncClient, faction_id: int
):
    keyword = (await client.post("/keywords", json={"name": "SKITARII"})).json()["id"]
    detachment = await _detachment(client, faction_id)
    await client.post(
        "/detachment-rules",
        json={"detachment_id": detachment, "name": "R", "keyword_option_ids": [[keyword]]},
    )
    assert (await client.delete(f"/keywords/{keyword}")).status_code == 204
    assert (await client.get("/detachment-rules")).json()[0]["keyword_option_ids"] == []
    assert (await client.delete(f"/detachments/{detachment}")).status_code == 204
    assert (await client.get("/detachment-rules")).json() == []


async def test_combat_endpoint_applies_detachment_rule_stealth(
    client: AsyncClient, faction_id: int, session: AsyncSession, monkeypatch
):
    # The defender's list has a detachment giving its INFANTRY units Stealth:
    # ranged attacks against them are -1 to hit. Every roll is a 4 vs BS4.
    await _seed_abilities(session)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)
    infantry = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]
    detachment = await _detachment(client, faction_id)
    rule = await client.post(
        "/detachment-rules",
        json={
            "detachment_id": detachment,
            "name": "Sneaky",
            "keyword_option_ids": [[infantry]],
            "datasheet_ability_ids": [await _id(client, "/datasheet-abilities", "Stealth")],
        },
    )
    assert rule.status_code == 201

    async def unit(list_id, keyword_ids, **model_stats):
        model = await client.post(
            "/models",
            json={
                "name": "M",
                "faction_id": faction_id,
                "save": 7,
                "toughness": 1,
                "oc": 1,
                "movement": 6,
                "wounds": 5,
                "leadership": 7,
                "keyword_ids": keyword_ids,
                **model_stats,
            },
        )
        model_id = model.json()["id"]
        weapon = await client.post(
            "/weapons",
            json={
                "name": "Gun",
                "model_id": model_id,
                "damage": "1",
                "range": 24,
                "strength": 10,
                "ap": -3,
                "attacks": "1",
                "skill": 4,
                "weapon_type": "ranged",
            },
        )
        faction_unit = await client.post(
            "/faction-units", json={"name": f"U{model_id}", "faction_id": faction_id}
        )
        response = await client.post(
            "/units",
            json={
                "faction_unit_id": faction_unit.json()["id"],
                "points": 1,
                "list_id": list_id,
                "unit_models": [{"model_id": model_id, "weapon_ids": [weapon.json()["id"]]}],
            },
        )
        return response.json()["id"], weapon.json()["id"]

    async def new_list(detachment_ids):
        response = await client.post(
            "/lists",
            json={
                "name": "L",
                "points_limit": 1000,
                "faction_id": faction_id,
                "detachment_ids": detachment_ids,
            },
        )
        return response.json()["id"]

    attacker, weapon = await unit(None, [])
    sneaky_list = await new_list([detachment])
    plain_list = await new_list([])

    async def damage(defender_id):
        response = await client.post(
            "/combat",
            json={
                "attacking_unit_id": attacker,
                "defending_unit_id": defender_id,
                "selected_weapon_ids": [weapon],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["total_damage"]

    assert await damage((await unit(sneaky_list, [infantry]))[0]) == 0  # Stealth
    assert await damage((await unit(plain_list, [infantry]))[0]) == 1  # no detachment
    assert await damage((await unit(sneaky_list, []))[0]) == 1  # not INFANTRY


# --- seeding, from detachments.json ---


async def test_seed_detachment_rules_from_data_file(
    session: AsyncSession, client: AsyncClient, fixture_game_data
):
    await run_all(session)
    await run_all(session)  # idempotent
    rules = (await client.get("/detachment-rules")).json()
    assert [r["name"] for r in rules] == ["Test Sneaky Gits"]
    keywords = {k["id"]: k["name"] for k in (await client.get("/keywords")).json()}
    assert [{keywords[i] for i in o} for o in rules[0]["keyword_option_ids"]] == [{"INFANTRY"}]
    assert rules[0]["datasheet_ability_ids"] == [
        await _id(client, "/datasheet-abilities", "Stealth")
    ]
    assert rules[0]["weapon_abilities"] == [
        {
            "weapon_ability_id": await _id(client, "/weapon-abilities", "Sustained 1"),
            "weapon_type": "ranged",
        }
    ]


@pytest.mark.parametrize(
    "rule,message",
    [
        ({"keyword_options": [["NOPE"]]}, "unknown keyword"),
        ({"keyword_options": [[]]}, "empty keyword option"),
        ({"datasheet_abilities": ["Nope"]}, "unknown datasheet ability"),
        ({"weapon_abilities": [{"name": "Nope"}]}, "unknown weapon ability"),
    ],
)
async def test_seed_detachment_rules_rejects_bad_entries(
    session: AsyncSession, tmp_path, monkeypatch, rule, message
):
    folder = tmp_path / "factions" / "orks"
    folder.mkdir(parents=True)
    detachment = {"name": "Mob", "dp": 1, "dispositions": [], "rules": [{"name": "R", **rule}]}
    (folder / "detachments.json").write_text(
        json.dumps({"faction": "Orks", "detachments": [detachment]})
    )
    monkeypatch.setattr(data_files, "DATA_DIR", tmp_path)
    await faction_seeds.seed(session)
    await faction_seeds.seed_detachments(session)
    await _seed_abilities(session)
    with pytest.raises(ValueError, match=message):
        await faction_seeds.seed_detachment_rules(session)


# --- per-model rules ---


def _per_model_rule(*options: tuple[str, ...]) -> DetachmentRule:
    rule = _rule(*options)
    rule.per_model = True
    return rule


def test_per_model_rule_reaches_matching_models_not_units():
    rule = _per_model_rule(("TECH-PRIEST",))
    unit = _unit(("TECH-PRIEST", "CHARACTER"), ("SKITARII", "INFANTRY"))
    assert detachment_rules.applies_to(rule, unit) is False
    priest, skitarius = ({k.name for k in um.model.keywords} for um in unit.unit_models)
    assert detachment_rules.model_matches(rule, priest)
    assert not detachment_rules.model_matches(rule, skitarius)


def _mantle_rule() -> DetachmentRule:
    # War-Form Mantles-style: TECH-PRIEST models have a 4+ invulnerable save.
    mantle = DatasheetAbility(name="Mantle", description=None)
    mantle.conditions, mantle.effects = [], []
    rule = _per_model_rule(("TECH-PRIEST",))
    rule.datasheet_ability_grants = [DetachmentRuleDatasheetAbility(datasheet_ability=mantle)]
    return rule


MANTLE_RULES = {
    "Mantle": [Rule(conditions=("always",), effects=("invulnerable_4",), side="defender")]
}


def _shot_at(monkeypatch, defender: Unit, rules, apply_precision=False, save_roll=4):
    # One AP-4 attack (3+ saves need a 7): only a 4+ invulnerable save stops a 4.
    rolls = iter([6, 6, save_roll])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    gun = Weapon(
        name="Gun",
        model_id=1,
        damage="1",
        range=24,
        strength=10,
        ap=-4,
        attacks="1",
        skill=3,
        weapon_type="ranged",
    )
    gun.id = 1
    precision = WeaponAbility(name="Precision", description=None)
    precision.conditions = [Condition(keyword="always", name="always", description=None)]
    precision.effects = [Effect(keyword="precision", name="precision", description=None)]
    gun.abilities = [precision] if apply_precision else []
    attacker = _unit(("INFANTRY",))
    attacker.unit_models[0].weapons = [gun]
    for unit_model in defender.unit_models:
        unit_model.model.save, unit_model.model.wounds = 3, 5
    return combat.resolve_combat(
        attacker,
        defender,
        {1},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        apply_precision=apply_precision,
        defender_detachment_rules=rules,
        ability_rules=MANTLE_RULES,
    ).total_damage


def test_per_model_defender_rule_protects_only_the_matching_model(monkeypatch):
    # A lone Tech-Priest saves on a 4+.
    assert _shot_at(monkeypatch, _unit(("TECH-PRIEST",)), [_mantle_rule()]) == 0
    # A Tech-Priest leading Skitarii: the attack goes to a Skitarius first,
    # who doesn't have it...
    leading = _unit(("TECH-PRIEST", "CHARACTER"), ("SKITARII",))
    leading.unit_models[0].model.is_leader = True
    assert _shot_at(monkeypatch, leading, [_mantle_rule()]) == 1
    # ...but one allocated to the Tech-Priest (Precision) gets the save.
    assert _shot_at(monkeypatch, leading, [_mantle_rule()], apply_precision=True) == 0
    # Without the rule, nobody has it.
    assert _shot_at(monkeypatch, _unit(("TECH-PRIEST",)), []) == 1


def test_per_model_attacker_rule_reaches_only_matching_models_weapons(monkeypatch):
    # +1 to hit on ranged weapons for TECH-PRIEST models: a 3 hits against BS4.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)
    plus_one = WeaponAbility(name="+1", description=None)
    plus_one.conditions = [Condition(keyword="always", name="always", description=None)]
    plus_one.effects = [Effect(keyword="plus_one_to_hit", name="+1", description=None)]
    rule = _per_model_rule(("TECH-PRIEST",))
    rule.weapon_ability_grants = [
        DetachmentRuleWeaponAbility(weapon_ability=plus_one, weapon_type="ranged")
    ]
    attacker = _unit(("TECH-PRIEST",), ("SKITARII",))
    for i, unit_model in enumerate(attacker.unit_models, start=1):
        gun = Weapon(
            name=f"Gun {i}",
            model_id=1,
            damage="1",
            range=24,
            strength=10,
            ap=-10,
            attacks="1",
            skill=4,
            weapon_type="ranged",
        )
        gun.id = i
        gun.abilities = []
        unit_model.weapons = [gun]
    defender = _unit(("INFANTRY",))
    target = defender.unit_models[0].model
    target.toughness, target.wounds, target.save = 1, 10, 7
    result = combat.resolve_combat(
        attacker,
        defender,
        {1, 2},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        attacker_detachment_rules=[rule],
    )
    assert {wr.name: wr.total_damage for wr in result.weapon_results} == {"Gun 1": 1, "Gun 2": 0}


async def test_create_per_model_detachment_rule(client: AsyncClient, faction_id: int):
    detachment = await _detachment(client, faction_id)
    for per_model in (True, False):
        response = await client.post(
            "/detachment-rules",
            json={"detachment_id": detachment, "name": f"R{per_model}", "per_model": per_model},
        )
        assert response.status_code == 201
        assert response.json()["per_model"] is per_model
    assert [r["per_model"] for r in (await client.get("/detachment-rules")).json()] == [True, False]


async def test_seed_sets_per_model_on_an_existing_rule(
    session: AsyncSession, client: AsyncClient, tmp_path, monkeypatch
):
    folder = tmp_path / "factions" / "orks"
    folder.mkdir(parents=True)

    def write(rule):
        detachment = {"name": "Mob", "dp": 1, "dispositions": [], "rules": [rule]}
        (folder / "detachments.json").write_text(
            json.dumps({"faction": "Orks", "detachments": [detachment]})
        )

    monkeypatch.setattr(data_files, "DATA_DIR", tmp_path)
    write({"name": "R"})
    await run_all(session)
    assert (await client.get("/detachment-rules")).json()[0]["per_model"] is False
    write({"name": "R", "per_model": True})
    await run_all(session)
    assert (await client.get("/detachment-rules")).json()[0]["per_model"] is True
