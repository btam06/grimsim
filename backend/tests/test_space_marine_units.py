from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.combat_rules.conditions import CONTROLLING_OBJECTIVE
from app.models import DatasheetAbility, Model, UnitModel
from app.models.model import TransportCapacity
from app.seeds import wargear_abilities as wargear_ability_seeds
from app.seeds import weapon_abilities as weapon_ability_seeds
from app.seeds.factions.space_marines import datasheet_abilities as sm_datasheets
from app.services import combat
from tests.test_combat import (
    _condition,
    _effect,
    _model,
    _unit,
    _unit_model,
    _wargear,
    _wargear_ability,
    _weapon,
)
from tests.test_deployment import _declare, _deployment, _game, _set, _unit_named
from tests.test_embarking import _disembark
from tests.test_movement import _move, _shifted
from tests.test_reinforcements import _advance_to
from tests.test_scoring_rules import _transport_game
from tests.test_space_marines import _applies

# The Heavy Intercessor Squad's and the Impulsor's rules.

IMPULSOR = TransportCapacity(
    capacity=7,
    keywords=("ADEPTUS ASTARTES", "INFANTRY"),
    excluded_keywords=("TERMINATOR", "JUMP PACK"),
    space={"GRAVIS": 2},
)


async def _model_of(session, unit) -> Model:
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    return (
        await session.execute(
            select(Model).options(selectinload(Model.abilities)).where(Model.id == unit_model.model_id)
        )
    ).scalar_one()


# --- transport capacity ---


async def test_a_transport_carries_only_what_it_can(client: AsyncClient, session, tmp_path):
    infantry = ("ADEPTUS ASTARTES", "INFANTRY")
    units = {
        1: [
            ("T", 1, {"keywords": ("TRANSPORT",)}),
            ("A", 3, {"keywords": infantry}),
            ("G", 2, {"keywords": infantry + ("GRAVIS",)}),
            ("B", 1, {"keywords": infantry}),
            ("X", 1, {"keywords": infantry + ("TERMINATOR",)}),
            ("V", 1, {"keywords": ("ADEPTUS ASTARTES", "VEHICLE")}),
        ],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    t, a, g, b, x, v = (_unit_named(deployment_, n) for n in "TAGBXV")
    model = await _model_of(session, t)
    model.transport = IMPULSOR
    await session.commit()

    response = await _set(client, game_id, 1, x, "embarked", t)
    assert "can't carry TERMINATOR" in response.json()["detail"]
    response = await _set(client, game_id, 1, v, "embarked", t)
    assert "can only carry ADEPTUS ASTARTES INFANTRY" in response.json()["detail"]
    # 3 models, then 2 GRAVIS models taking up 2 each: 7, full.
    for unit in (a, g):
        response = await _set(client, game_id, 1, unit, "embarked", t)
        assert response.status_code == 200, response.text
    response = await _set(client, game_id, 1, b, "embarked", t)
    assert "isn't room" in response.json()["detail"]
    # Declared again where it is, it still fits.
    response = await _set(client, game_id, 1, g, "embarked", t)
    assert response.status_code == 200, response.text
    await _declare(client, game_id, 1)


# --- Rapid Disembarkation ---


async def _advance_transport(client, session, tmp_path, rapid: bool):
    game_id, t, p = await _transport_game(client, session, tmp_path)
    if rapid:
        model = await _model_of(session, t)
        model.abilities.append(
            DatasheetAbility(name="Rapid Disembarkation", description="Rapid Disembarkation")
        )
        await session.commit()
    await _advance_to(client, game_id, 1, 1, "movement")
    response = await client.post(
        f"/games/{game_id}/movement/advance", json={"unit_id": t["unit_id"]}
    )
    assert response.status_code == 200, response.text
    t = _unit_named(await _deployment(client, game_id), "T")
    response = await _move(client, game_id, t, "advance", _shifted(t, dy=-1))
    assert response.status_code == 200, response.text
    return game_id, p


async def test_rapid_disembarkation_shock_disembarks_after_advancing(
    client: AsyncClient, session, tmp_path
):
    game_id, p = await _advance_transport(client, session, tmp_path, rapid=True)
    response = await _disembark(client, game_id, p, [(21.5, 37), (21.5, 38.5)])
    assert response.status_code == 200, response.text
    # A shock disembark: no charge this turn.
    await _advance_to(client, game_id, 1, 1, "charge")
    charge = {u["name"]: u for u in (await client.get(f"/games/{game_id}/charge")).json()["units"]}
    assert charge["P"]["reason"] == "it made a shock disembark move this turn"


async def test_no_disembarking_after_advancing_without_it(client: AsyncClient, session, tmp_path):
    game_id, p = await _advance_transport(client, session, tmp_path, rapid=False)
    response = await _disembark(client, game_id, p, [(21.5, 37), (21.5, 38.5)])
    assert "its transport Advanced this turn" in response.json()["detail"]


# --- Unyielding in the Face of the Foe, Shield Dome ---


def test_unyielding_in_the_face_of_the_foe_while_controlling_an_objective():
    rules = sm_datasheets.RULES["Unyielding in the Face of the Foe"]
    assert _applies(rules, {"defender_positions": {CONTROLLING_OBJECTIVE}})
    assert not _applies(rules, {"defender_positions": {"in_range_of_objective"}})


def _attack(monkeypatch, roll, attacker_gear=(), defender_gear=(), **kwargs):
    # One S8 AP-1 attack against a 3+ save, every die rolling `roll`.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: roll)
    weapon = _weapon(attacks="1", skill=3, strength=8, ap=kwargs.pop("ap", -1), weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon], wargear=list(attacker_gear))])
    defender = _unit([_unit_model(_model(wounds=5), [], wargear=list(defender_gear))])
    return combat.resolve_combat(
        attacker, defender, {weapon.id},
        in_engagement_range=False, visible=True, in_range=True, in_cover=False,
        half_range=False, moved_less_than_3=False, advanced=False, **kwargs,
    )


def test_plus_one_to_save(monkeypatch):
    unyielding = sm_datasheets.RULES["Unyielding in the Face of the Foe"]
    # A 3 fails a 4+ save...
    assert _attack(monkeypatch, 3).total_damage == 1
    # ...but passes with +1, while controlling an objective.
    result = _attack(
        monkeypatch, 3, defender_rules=unyielding, defender_positions={CONTROLLING_OBJECTIVE}
    )
    assert result.total_damage == 0


def test_shield_dome_protects_its_bearer(monkeypatch):
    dome = _wargear(
        [_wargear_ability([_condition("always")], [_effect("invulnerable_5")])]
    )
    # AP-4 against a 3+ save: a 5 fails it, but not a 5+ invulnerable save.
    assert _attack(monkeypatch, 5, ap=-4).total_damage == 1
    assert _attack(monkeypatch, 5, ap=-4, defender_gear=[dome]).total_damage == 0
    # On the attacker, it doesn't protect its target.
    assert _attack(monkeypatch, 5, ap=-4, attacker_gear=[dome]).total_damage == 1


def test_the_impulsors_weapon_and_wargear_abilities():
    weapons = {entry[0]: entry for entry in weapon_ability_seeds.ENTRIES}
    assert weapons["Rapid Fire 4"][3] == ["add_four_attacks"]
    assert weapons["Rapid Fire 6"][3] == ["add_six_attacks"]
    assert weapons["Blast 2"][3] == ["blast_2"]
    wargear = {entry[0] for entry in wargear_ability_seeds.ENTRIES}
    assert {"5+ Invulnerable Save", 'Scouts 6"'} <= wargear


# --- Firing Deck ---


async def test_firing_deck_fires_embarked_models_weapons(client: AsyncClient, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import deployment, shooting
    from tests.test_deployment import _deploy, _row

    units = {
        1: [
            ("T", 1, {"keywords": ("TRANSPORT",), "weapon_range": 24}),
            ("P", 3, {"weapon_range": 24}),
        ],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    t, p, d = (_unit_named(deployment_, n) for n in "TPD")
    model = await _model_of(session, t)
    model.abilities.append(DatasheetAbility(name="Firing Deck 2", description="Firing Deck 2"))
    await session.commit()
    response = await _set(client, game_id, 1, p, "embarked", t)
    assert response.status_code == 200, response.text
    for seat in (1, 2):
        await _declare(client, game_id, seat)
    for unit, spot in ((t, (20, 33)), (d, (20, 10))):
        response = await _deploy(client, game_id, unit, _row(unit, *spot))
        assert response.status_code == 200, response.text

    await _advance_to(client, game_id, 1, 1, "shooting")
    [target] = (
        await client.get(f"/games/{game_id}/shooting/targets?unit_id={t['unit_id']}")
    ).json()
    deck = next(w for w in target["weapons"] if w["firing_deck"])
    # Every embarked model carries it...
    assert (deck["name"], deck["carried_by"]) == ("P gun (Firing Deck)", 3)
    response = await client.post(
        f"/games/{game_id}/shooting",
        json={
            "unit_id": t["unit_id"],
            "target_unit_id": d["unit_id"],
            "firing_deck_weapon_ids": [deck["id"]],
        },
    )
    assert response.status_code == 200, response.text
    # ...but only 2 of them fire it.
    assert len(response.json()["combat"]["attack_rolls"]) == 2
    # The units in it can't shoot for the rest of the turn.
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, p["unit_id"])
    assert shooting.deck_closed(game_, unit)
    assert shooting.firing_deck(deployment.find_unit(game_, t["unit_id"])) == 2


# --- Deathwatch Terminators, Eradicators, Scouts ---


def test_a_weapons_usual_profile_clashes_with_its_hunter_profile():
    from types import SimpleNamespace

    from app.services.weapon_profiles import conflicting_profiles

    weapon = lambda name: SimpleNamespace(name=name)  # noqa: E731
    assert conflicting_profiles([weapon("Melta Rifle"), weapon("Melta Rifle - Hunter")]) == (
        "Melta Rifle"
    )
    assert conflicting_profiles([weapon("Melta Rifle"), weapon("Bolt Pistol")]) is None
    assert conflicting_profiles([weapon("Melta Rifle"), weapon("Melta Rifle")]) is None


def _damage(monkeypatch, rolls, rules=None):
    # One D3+2 ranged attack that hits, wounds and isn't saved, against a
    # 10-wound model: the damage done, with the dice rolling `rolls` in turn.
    dice = iter(rolls)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(dice))
    weapon = _weapon(attacks="1", skill=3, strength=8, ap=0, damage="D3+2", weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=10), [])])
    return combat.resolve_combat(
        attacker, defender, {weapon.id},
        in_engagement_range=False, visible=True, in_range=True, in_cover=False,
        half_range=False, moved_less_than_3=False, advanced=False, attacker_rules=rules,
    ).total_damage


def test_total_obliteration_rerolls_low_damage(monkeypatch):
    rule = sm_datasheets.RULES["Total Obliteration"]
    assert combat.average_damage("D3+2") == 4
    assert combat.average_damage("2D6") == 7
    # Hit 6, wound 6, save 1, then D3 rolls 1: 3 damage...
    assert _damage(monkeypatch, [6, 6, 1, 1]) == 3
    # ...below its average of 4, so re-rolled: a 3, 5 damage.
    assert _damage(monkeypatch, [6, 6, 1, 1, 3], rules=rule) == 5
    # At or above average, it's kept.
    assert _damage(monkeypatch, [6, 6, 1, 2], rules=rule) == 4


async def test_deathwatch_terminatus_assault(client: AsyncClient, session, tmp_path, monkeypatch):
    from app.routers.games import _load_game
    from tests.test_charging import _charge_game, _make, _roll
    from tests.test_deployment import R32

    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch)
    model = await _model_of(session, d)
    model.abilities.append(
        DatasheetAbility(name="Terminatus Assault (Deathwatch)", description="Terminatus")
    )
    await session.commit()
    charge = await _roll(client, game_id, d)
    assert next(u for u in charge["units"] if u["unit_id"] == d["unit_id"])["can_reroll"]
    response = await client.post(
        f"/games/{game_id}/charge/reroll", json={"unit_id": d["unit_id"]}
    )
    assert response.status_code == 200, response.text
    # Once.
    assert not next(u for u in response.json()["units"] if u["unit_id"] == d["unit_id"])[
        "can_reroll"
    ]
    response = await client.post(
        f"/games/{game_id}/charge/reroll", json={"unit_id": d["unit_id"]}
    )
    assert response.status_code == 400

    # Into Engagement Range of A: A (not IMPERIUM or CHAOS) tests at -1.
    a_y = a["models"][0]["position"]["y"]
    spot = [{"unit_model_id": d["models"][0]["unit_model_id"], "x": 20, "y": a_y - 2 * R32 - 1}]
    response = await _make(client, game_id, d, a, spot)
    assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    [test] = [t for t in game.battle_shock_tests if t.unit_id == a["unit_id"]]
    assert (test.reason, test.modifier) == ("Terminatus Assault (Deathwatch)", -1)


def test_flexible_asset_lets_it_act_after_advancing():
    from types import SimpleNamespace

    from app.services.in_game.actions import _act_after

    unit = SimpleNamespace(
        unit_models=[
            SimpleNamespace(model=SimpleNamespace(abilities=[SimpleNamespace(name="Flexible Asset")]))
        ]
    )
    assert _act_after(unit) == {"advanced", "fell_back"}
