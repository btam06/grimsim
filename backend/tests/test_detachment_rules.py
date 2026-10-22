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


# --- keywords a rule grants ---


def _granting_rule(granted: tuple[str, ...], *options, per_model=False) -> DetachmentRule:
    rule = _rule(*options)
    rule.granted_keywords = [Keyword(name=k) for k in granted]
    rule.per_model = per_model
    return rule


def test_unit_wide_rule_grants_keywords_when_every_model_matches():
    from app.services.enhancements import rule_granted_keywords

    rule = _granting_rule(("BATTLELINE",), ("WAR DOG",))
    assert rule_granted_keywords([rule], [{"WAR DOG"}]) == [{"BATTLELINE"}]
    # A unit with a model that doesn't match isn't reached at all.
    assert rule_granted_keywords([rule], [{"WAR DOG"}, {"INFANTRY"}]) == [set(), set()]


def test_per_model_rule_grants_keywords_to_matching_models_only():
    from app.services.enhancements import rule_granted_keywords

    rule = _granting_rule(("BATTLELINE",), ("WAR DOG",), per_model=True)
    assert rule_granted_keywords([rule], [{"WAR DOG"}, {"INFANTRY"}]) == [{"BATTLELINE"}, set()]


def test_rule_without_options_grants_keywords_to_every_model():
    from app.services.enhancements import rule_granted_keywords

    rule = _granting_rule(("CHAOS",))
    assert rule_granted_keywords([rule], [{"A"}, {"B"}]) == [{"CHAOS"}, {"CHAOS"}]


async def _keyword(client: AsyncClient, name: str) -> int:
    return (await client.post("/keywords", json={"name": name})).json()["id"]


async def _war_dog_list(client: AsyncClient, faction_id: int, granted: str, with_rule=True):
    # A list with a detachment whose rule gives WAR DOG units `granted`, and a
    # unit of one WAR DOG model in it. Returns (detachment, list, model, unit).
    war_dog = await _keyword(client, "WAR DOG")
    granted_id = await _keyword(client, granted)
    detachment = await _detachment(client, faction_id, "Houndpack Lance")
    if with_rule:
        response = await client.post(
            "/detachment-rules",
            json={
                "detachment_id": detachment,
                "name": "Houndpack Keywords",
                "keyword_option_ids": [[war_dog]],
                "granted_keyword_ids": [granted_id],
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["granted_keyword_ids"] == [granted_id]
    list_id = (
        await client.post(
            "/lists",
            json={
                "name": "Hounds",
                "points_limit": 2000,
                "faction_id": faction_id,
                "detachment_ids": [detachment],
            },
        )
    ).json()["id"]
    model = (
        await client.post(
            "/models",
            json={
                "name": "War Dog",
                "faction_id": faction_id,
                "save": 3,
                "toughness": 10,
                "oc": 8,
                "movement": 12,
                "wounds": 12,
                "leadership": 7,
                "keyword_ids": [war_dog],
            },
        )
    ).json()["id"]
    faction_unit = (
        await client.post("/faction-units", json={"name": "War Dogs", "faction_id": faction_id})
    ).json()["id"]
    unit = (
        await client.post(
            "/units",
            json={
                "faction_unit_id": faction_unit,
                "points": 150,
                "list_id": list_id,
                "unit_models": [{"model_id": model}],
            },
        )
    ).json()["id"]
    return detachment, list_id, model, unit


@pytest.mark.parametrize("with_rule", [True, False])
async def test_granted_keyword_makes_a_stratagem_usable(
    client: AsyncClient, faction_id: int, with_rule
):
    _, _, _, unit = await _war_dog_list(client, faction_id, "BATTLELINE", with_rule)
    battleline = await _id(client, "/keywords", "BATTLELINE")
    await client.post(
        "/stratagems",
        json={"name": "For Battleline", "cp": 1, "is_core": True, "keyword_ids": [battleline]},
    )
    response = await client.get(
        "/combat/stratagems", params={"unit_id": unit, "side": "attacker"}
    )
    names = [s["name"] for s in response.json()]
    assert ("For Battleline" in names) is with_rule


@pytest.mark.parametrize("with_rule,status", [(True, 201), (False, 400)])
async def test_granted_character_lets_a_model_carry_an_enhancement(
    client: AsyncClient, faction_id: int, with_rule, status
):
    detachment, list_id, model, _ = await _war_dog_list(
        client, faction_id, "CHARACTER", with_rule
    )
    enhancement = (
        await client.post(
            "/enhancements",
            json={
                "name": "Loping Predator",
                "points": 10,
                "kind": "enhancement",
                "detachment_id": detachment,
            },
        )
    ).json()["id"]
    available = await client.get(
        "/enhancements/available", params={"list_id": list_id, "model_id": model}
    )
    assert (enhancement in [e["id"] for e in available.json()]) is with_rule

    faction_unit = (
        await client.post("/faction-units", json={"name": "Alpha", "faction_id": faction_id})
    ).json()["id"]
    response = await client.post(
        "/units",
        json={
            "faction_unit_id": faction_unit,
            "points": 160,
            "list_id": list_id,
            "unit_models": [{"model_id": model, "enhancement_id": enhancement}],
        },
    )
    assert response.status_code == status, response.text


async def test_create_detachment_rule_rejects_unknown_granted_keyword(
    client: AsyncClient, faction_id: int
):
    detachment = await _detachment(client, faction_id)
    response = await client.post(
        "/detachment-rules",
        json={"detachment_id": detachment, "name": "Bad", "granted_keyword_ids": [9999]},
    )
    assert response.status_code == 400


# --- rules units are selected for (e.g. Houndpack Alphas) ---


class _Alphas:
    # A Houndpack list whose "Alphas" rule gives CHARACTER to up to 3 WAR DOG
    # units selected for it, a War Dog model and an enhancement needing
    # CHARACTER, all made through the API.

    def __init__(self, client: AsyncClient, faction_id: int):
        self.client = client
        self.faction_id = faction_id

    async def setup(self):
        client = self.client
        war_dog = await _keyword(client, "WAR DOG")
        character = await _keyword(client, "CHARACTER")
        self.detachment = await _detachment(client, self.faction_id, "Houndpack Lance")
        response = await client.post(
            "/detachment-rules",
            json={
                "detachment_id": self.detachment,
                "name": "Houndpack Alphas",
                "keyword_option_ids": [[war_dog]],
                "granted_keyword_ids": [character],
                "selection_limit": 3,
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["selection_limit"] == 3
        self.rule = response.json()["id"]
        self.list_id = (
            await client.post(
                "/lists",
                json={
                    "name": "Hounds",
                    "points_limit": 2000,
                    "faction_id": self.faction_id,
                    "detachment_ids": [self.detachment],
                },
            )
        ).json()["id"]
        self.war_dog = await self._model("War Dog", [war_dog])
        self.trooper = await self._model("Trooper", [])
        self.faction_unit = (
            await client.post(
                "/faction-units", json={"name": "War Dogs", "faction_id": self.faction_id}
            )
        ).json()["id"]
        self.enhancement = (
            await client.post(
                "/enhancements",
                json={
                    "name": "Loping Predator",
                    "points": 10,
                    "kind": "enhancement",
                    "detachment_id": self.detachment,
                },
            )
        ).json()["id"]
        return self

    async def _model(self, name, keyword_ids):
        return (
            await self.client.post(
                "/models",
                json={
                    "name": name,
                    "faction_id": self.faction_id,
                    "save": 3,
                    "toughness": 10,
                    "oc": 8,
                    "movement": 12,
                    "wounds": 12,
                    "leadership": 7,
                    "keyword_ids": keyword_ids,
                },
            )
        ).json()["id"]

    async def unit(self, model=None, selected=True, enhancement=None):
        return await self.client.post(
            "/units",
            json={
                "faction_unit_id": self.faction_unit,
                "points": 150,
                "list_id": self.list_id,
                "unit_models": [
                    {"model_id": model or self.war_dog, "enhancement_id": enhancement}
                ],
                "selected_rule_ids": [self.rule] if selected else [],
            },
        )


async def test_up_to_the_selection_limit_of_units_can_be_selected(
    client: AsyncClient, faction_id: int
):
    alphas = await _Alphas(client, faction_id).setup()
    for _ in range(3):
        response = await alphas.unit()
        assert response.status_code == 201, response.text
        assert response.json()["selected_rule_ids"] == [alphas.rule]
    response = await alphas.unit()
    assert response.status_code == 400
    assert "at most 3" in response.json()["detail"]
    # Unselected War Dogs are still fine.
    assert (await alphas.unit(selected=False)).status_code == 201


async def test_only_units_the_rule_reaches_can_be_selected(
    client: AsyncClient, faction_id: int
):
    alphas = await _Alphas(client, faction_id).setup()
    response = await alphas.unit(model=alphas.trooper)
    assert response.status_code == 400
    assert "can't be selected" in response.json()["detail"]


@pytest.mark.parametrize("selected,status", [(True, 201), (False, 400)])
async def test_only_selected_units_gain_the_rules_keywords(
    client: AsyncClient, faction_id: int, selected, status
):
    alphas = await _Alphas(client, faction_id).setup()
    response = await alphas.unit(selected=selected, enhancement=alphas.enhancement)
    assert response.status_code == status, response.text


@pytest.mark.parametrize("selected", [True, False])
async def test_enhancements_offered_depend_on_the_selection(
    client: AsyncClient, faction_id: int, selected
):
    alphas = await _Alphas(client, faction_id).setup()
    available = await client.get(
        "/enhancements/available",
        params={
            "list_id": alphas.list_id,
            "model_id": alphas.war_dog,
            "selected_rule_ids": [alphas.rule] if selected else [],
        },
    )
    assert (alphas.enhancement in [e["id"] for e in available.json()]) is selected


async def test_selectable_rules_lists_rules_the_unit_can_be_selected_for(
    client: AsyncClient, faction_id: int
):
    alphas = await _Alphas(client, faction_id).setup()
    assert (await alphas.unit()).status_code == 201

    async def selectable(model):
        response = await client.get(
            "/units/selectable-rules",
            params={"list_id": alphas.list_id, "model_ids": [model]},
        )
        assert response.status_code == 200
        return response.json()

    assert [(r["id"], r["selected_elsewhere"]) for r in await selectable(alphas.war_dog)] == [
        (alphas.rule, 1)
    ]
    assert await selectable(alphas.trooper) == []


async def test_selected_unit_gains_keywords_in_combat(client: AsyncClient, faction_id: int):
    alphas = await _Alphas(client, faction_id).setup()
    character = await _id(client, "/keywords", "CHARACTER")
    await client.post(
        "/stratagems",
        json={"name": "For Characters", "cp": 1, "is_core": True, "keyword_ids": [character]},
    )
    selected = (await alphas.unit()).json()["id"]
    unselected = (await alphas.unit(selected=False)).json()["id"]

    async def usable(unit):
        response = await client.get(
            "/combat/stratagems", params={"unit_id": unit, "side": "attacker"}
        )
        return "For Characters" in [s["name"] for s in response.json()]

    assert await usable(selected)
    assert not await usable(unselected)


async def test_rule_cant_be_both_per_model_and_selected(client: AsyncClient, faction_id: int):
    detachment = await _detachment(client, faction_id)
    response = await client.post(
        "/detachment-rules",
        json={
            "detachment_id": detachment,
            "name": "Bad",
            "per_model": True,
            "selection_limit": 2,
        },
    )
    assert response.status_code == 400


async def test_deleting_a_selected_rule_clears_selections(client: AsyncClient, faction_id: int):
    alphas = await _Alphas(client, faction_id).setup()
    unit = (await alphas.unit()).json()["id"]
    assert (await client.delete(f"/detachment-rules/{alphas.rule}")).status_code == 204
    units = (await client.get("/units")).json()
    assert next(u for u in units if u["id"] == unit)["selected_rule_ids"] == []
