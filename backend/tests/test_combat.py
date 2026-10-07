import pytest
from httpx import AsyncClient

from app.models import Model, Unit, UnitModel, Weapon
from app.services import combat


def _model(**overrides) -> Model:
    defaults = dict(
        name="Target",
        faction_id=1,
        save=3,
        toughness=4,
        oc=1,
        movement=6,
        wounds=2,
        leadership=7,
        invulnerable=None,
        feel_no_pain=None,
    )
    defaults.update(overrides)
    return Model(**defaults)


def _weapon(**overrides) -> Weapon:
    defaults = dict(
        name="Gun",
        model_id=1,
        damage="1",
        range=24,
        strength=4,
        ap=0,
        attacks=1,
        skill=3,
        weapon_type=None,
    )
    defaults.update(overrides)
    return Weapon(**defaults)


def _unit_model(model: Model, weapons: list[Weapon]) -> UnitModel:
    um = UnitModel(unit_id=1, model_id=1)
    um.model = model
    um.weapons = weapons
    return um


def _unit(unit_models: list[UnitModel]) -> Unit:
    unit = Unit(faction_unit_id=1, points=100)
    unit.unit_models = unit_models
    return unit


# --- wound_threshold table ---


@pytest.mark.parametrize(
    "strength,toughness,expected",
    [
        (8, 4, 2),  # double or more -> 2+
        (6, 4, 3),  # greater -> 3+
        (4, 4, 4),  # equal -> 4+
        (3, 4, 5),  # defender tougher -> 5+
        (2, 4, 6),  # defender double or more -> 6+
    ],
)
def test_wound_threshold(strength, toughness, expected):
    assert combat.wound_threshold(strength, toughness) == expected


# --- roll_damage ---


def test_roll_damage_flat():
    assert combat.roll_damage("5") == 5


def test_roll_damage_bare_die(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)
    assert combat.roll_damage("D6") == 4


def test_roll_damage_multi_die(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)
    assert combat.roll_damage("2D6") == 8


# --- resolve_combat ---


def test_resolve_combat_not_visible_deals_no_damage(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks=2, skill=2)
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=False, in_range=True
    )
    assert result.total_attacks == 0
    assert result.total_damage == 0


def test_resolve_combat_not_in_range_deals_no_damage(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks=2, skill=2)
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=False
    )
    assert result.total_attacks == 0


def test_resolve_combat_unselected_weapon_does_not_attack(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks=3, skill=2)
    weapon.id = 42
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=10), [])])

    result = combat.resolve_combat(
        attacker, defender, set(), in_engagement_range=False, visible=True, in_range=True
    )
    assert result.total_attacks == 0


def test_resolve_combat_engagement_range_selects_melee_only(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    melee = _weapon(attacks=2, skill=2, weapon_type="melee")
    melee.id = 1
    ranged = _weapon(attacks=5, skill=2, weapon_type="ranged")
    ranged.id = 2
    attacker = _unit([_unit_model(_model(), [melee, ranged])])
    defender = _unit([_unit_model(_model(wounds=100, save=7), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {melee.id, ranged.id},
        in_engagement_range=True,
        visible=True,
        in_range=True,
    )
    assert result.total_attacks == 2  # only the melee weapon's attacks counted


def test_resolve_combat_not_in_engagement_range_selects_ranged_only(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    melee = _weapon(attacks=2, skill=2, weapon_type="melee")
    melee.id = 1
    ranged = _weapon(attacks=5, skill=2, weapon_type="ranged")
    ranged.id = 2
    attacker = _unit([_unit_model(_model(), [melee, ranged])])
    defender = _unit([_unit_model(_model(wounds=100, save=7), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {melee.id, ranged.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
    )
    assert result.total_attacks == 5  # only the ranged weapon's attacks counted


def test_resolve_combat_full_resolution_with_spillover_and_kills(monkeypatch):
    # A constant roll of 6 always hits/wounds (thresholds engineered <= 6) and the
    # save is engineered to be impossible (save_needed > 6), with no FNP to roll.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks=1, skill=2, strength=10, ap=-10, damage="2")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender_models = [
        _unit_model(_model(wounds=1, save=2, feel_no_pain=None), []),
        _unit_model(_model(wounds=1, save=2, feel_no_pain=None), []),
    ]
    defender = _unit(defender_models)

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True
    )
    assert result.total_attacks == 1
    assert result.total_hits == 1
    assert result.total_wounds == 1
    assert result.failed_saves == 1
    assert result.total_damage == 2
    assert result.models_destroyed == 2
    assert result.defending_models_remaining == 0


def test_resolve_combat_feel_no_pain_negates_some_damage(monkeypatch):
    rolls = iter([6, 6, 1, 6, 2, 5])  # hit, wound, save(fail), fnp x3 (succeed, fail, succeed)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    weapon = _weapon(attacks=1, skill=2, strength=10, ap=-10, damage="3")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=4), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True
    )
    assert result.failed_saves == 1
    assert result.total_damage == 1  # only the middle fnp roll (2) failed to negate
    assert result.models_destroyed == 0
    assert result.defending_models_remaining == 1


# --- API endpoint ---


async def _create_model(client: AsyncClient, faction_id: int, **overrides) -> int:
    payload = {
        "name": "Combatant",
        "faction_id": faction_id,
        "save": 3,
        "toughness": 4,
        "oc": 1,
        "movement": 6,
        "wounds": 2,
        "leadership": 7,
    }
    payload.update(overrides)
    response = await client.post("/models", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_weapon(client: AsyncClient, model_id: int, **overrides) -> int:
    payload = {
        "name": "Gun",
        "model_id": model_id,
        "damage": "1",
        "range": 24,
        "strength": 4,
        "ap": 0,
        "attacks": 1,
        "skill": 3,
    }
    payload.update(overrides)
    response = await client.post("/weapons", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_faction_unit(client: AsyncClient, faction_id: int, name: str) -> int:
    response = await client.post("/faction-units", json={"name": name, "faction_id": faction_id})
    assert response.status_code == 201
    return response.json()["id"]


async def _create_unit(
    client: AsyncClient, faction_unit_id: int, model_id: int | None = None, weapon_id: int | None = None
) -> int:
    unit_models = []
    if model_id is not None:
        unit_models.append({"model_id": model_id, "weapon_ids": [weapon_id] if weapon_id else []})
    response = await client.post(
        "/units",
        json={"faction_unit_id": faction_unit_id, "points": 100, "unit_models": unit_models},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_combat_endpoint_resolves_with_calculator_defaults(
    client: AsyncClient, faction_id: int, monkeypatch
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(client, attacker_model_id, strength=10, ap=-10, skill=2)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=1)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["visible"] is True
    assert body["in_range"] is True
    assert body["total_attacks"] == 1
    assert body["models_destroyed"] == 1


async def test_combat_endpoint_calculator_ignores_visible_and_range_overrides(
    client: AsyncClient, faction_id: int, monkeypatch
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(client, attacker_model_id)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "game_id": None,
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "defender_visible": False,
            "defender_in_range": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["visible"] is True
    assert body["in_range"] is True


async def test_combat_endpoint_game_mode_honors_visible_override(
    client: AsyncClient, faction_id: int
):
    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(client, attacker_model_id)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "game_id": 1,
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "defender_visible": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["visible"] is False
    assert body["total_attacks"] == 0


async def test_combat_endpoint_invalid_attacking_unit_returns_400(
    client: AsyncClient, faction_id: int
):
    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": 9999,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [],
        },
    )
    assert response.status_code == 400


async def test_combat_endpoint_weapon_not_equipped_by_attacker_returns_400(
    client: AsyncClient, faction_id: int
):
    attacker_model_id = await _create_model(client, faction_id)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id)

    other_model_id = await _create_model(client, faction_id)
    other_weapon_id = await _create_weapon(client, other_model_id)

    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [other_weapon_id],
        },
    )
    assert response.status_code == 400
