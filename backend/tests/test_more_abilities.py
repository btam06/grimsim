from httpx import AsyncClient

from app.models import WeaponAbility
from app.routers.games import _load_game
from app.services.in_game import battle_shock, command_phase, deployment, movement, shooting, unit_effects
from app.services.list_building.warlord import warlord_reason
from tests.test_admech_characters import _give
from tests.test_combat import _model, _resolve, _unit, _unit_model, _weapon
from tests.test_deployment import _unit_named
from tests.test_fighting import BLADE, _to_fight
from tests.test_movement import _battle
from tests.test_shooting import _place, _to_shooting

# Abilities that were text only: Psychic Hood, Protective Disciples, Enslaved
# Star God, Karnivore, Dynamic Efficiency, Neurostatic Interference,
# Data-spike and Matter Absorption. Seat 2 goes first; each battle starts in
# its movement phase.


def test_psychic_hood_against_psychic_weapons(monkeypatch):
    from app.seeds.factions.space_marines import datasheet_abilities as sm

    for psychic, fnp_rolls in ((True, [4]), (False, [])):
        rolls = iter([6, 6, 1, 4])  # hit, wound, save, fnp
        monkeypatch.setattr("app.services.dice.randint", lambda a, b: next(rolls, 1))
        weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, damage="1", weapon_type="ranged")
        weapon.id = 1
        weapon.abilities = [WeaponAbility(name="Psychic")] if psychic else []
        attacker = _unit([_unit_model(_model(), [weapon])])
        defender = _unit([_unit_model(_model(wounds=10, save=7), [])])
        result = _resolve(attacker, defender, weapon, defender_rules=sm.RULES["Psychic Hood"])
        assert result.fnp_rolls == fnp_rolls


async def test_protective_disciples(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("N", 1, {}), ("C", 1, {"keywords": ("DESTROYER CULT",)})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units,
                                      spots={"A": (20, 38), "N": (20, 4), "C": (24, 4)})
    game_id = game["id"]
    n, c = _unit_named(deployment_, "N"), _unit_named(deployment_, "C")
    await _give(session, n, "Protective Disciples")
    game_ = await _load_game(session, game_id)
    assert shooting.lone_operative(game_, deployment.find_unit(game_, n["unit_id"]))
    await _place(session, c, [(40, 4)])
    game_ = await _load_game(session, game_id)
    assert not shooting.lone_operative(game_, deployment.find_unit(game_, n["unit_id"]))


async def test_enslaved_star_god_cant_be_warlord(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path)
    a = _unit_named(deployment_, "A")
    await _give(session, a, "Enslaved Star God")
    list_id = next(p["list_id"] for p in game["players"] if p["seat"] == 1)
    assert await warlord_reason(session, list_id, a["unit_id"]) == "A can't be the list's Warlord"


async def test_karnivore_rerolls_its_advance(client: AsyncClient, session, tmp_path, monkeypatch):
    game, deployment_ = await _battle(client, session, tmp_path)
    game_id = game["id"]
    d = _unit_named(deployment_, "D")
    await _give(session, d, "Karnivore")
    rolls = iter([1, 6])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: next(rolls, 3))
    await client.post(f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"]})
    movement_state = (await client.get(f"/games/{game_id}/movement")).json()
    [unit] = [u for u in movement_state["units"] if u["unit_id"] == d["unit_id"]]
    assert (unit["advance_roll"], unit["can_reroll_advance"]) == (1, True)
    response = await client.post(f"/games/{game_id}/movement/advance/reroll", json={"unit_id": d["unit_id"]})
    assert response.status_code == 200, response.text
    [unit] = [u for u in response.json()["units"] if u["unit_id"] == d["unit_id"]]
    assert (unit["advance_roll"], unit["can_reroll_advance"]) == (6, False)
    response = await client.post(f"/games/{game_id}/movement/advance/reroll", json={"unit_id": d["unit_id"]})
    assert response.status_code == 400


async def test_dynamic_efficiency(client: AsyncClient, session, tmp_path, monkeypatch):
    game, deployment_ = await _battle(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _give(session, d, "Dynamic Efficiency")
    game_ = await _load_game(session, game_id)
    unit, other = (deployment.find_unit(game_, u["unit_id"]) for u in (d, a))
    assert command_phase.eligible_after(game_, unit, "advanced", "charge")
    assert command_phase.eligible_after(game_, unit, "fell_back", "charge")
    assert not command_phase.eligible_after(game_, other, "advanced", "charge")
    # Desperate Escape: each failed test (a 1) re-rolled (a 6) - no mortal wounds.
    rolls = iter([1] * 5 + [6] * 5)
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: next(rolls, 6))
    movement._desperate_escape(game_, unit)
    assert sum(m.wounds_lost for m in game_.model_damage if m.unit_model_id in {x.id for x in unit.unit_models}) == 0


async def test_neurostatic_interference(client: AsyncClient, session, tmp_path):
    # Seat 1's S (the aura) near seat 2's D: -1 to D's tests - -2 while S is
    # within 6" of a friendly ADEPTUS MECHANICUS BATTLELINE unit (B).
    battleline = {"keywords": ("ADEPTUS MECHANICUS", "BATTLELINE")}
    units = {1: [("S", 1, {}), ("B", 1, battleline)], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units,
                                      spots={"S": (20, 38), "B": (40, 38), "D": (20, 4)})
    game_id = game["id"]
    s, b, d = (_unit_named(deployment_, n) for n in "SBD")
    await _give(session, s, "Neurostatic Interference (Aura)")
    game_ = await _load_game(session, game_id)
    target = deployment.find_unit(game_, d["unit_id"])
    assert battle_shock.aura_modifier(game_, target) == 0
    await _place(session, s, [(20, 9)])
    game_ = await _load_game(session, game_id)
    assert battle_shock.aura_modifier(game_, target) == -1
    await _place(session, b, [(24, 9)])
    game_ = await _load_game(session, game_id)
    assert battle_shock.aura_modifier(game_, target) == -2


async def test_data_spike(client: AsyncClient, session, tmp_path, monkeypatch):
    # Seat 1's Dominus T, engaged with seat 2's VEHICLE V, uses it at the start
    # of seat 2's Fight phase: a 6 - D6 (6) mortal wounds, and V's melee WS is
    # worse for the phase.
    units = {1: [("T", 1, BLADE)], 2: [("V", 4, {**BLADE, "keywords": ("VEHICLE",)})]}
    places = {"V": [(20, 4), (21.5, 4), (23, 4), (24.5, 4)], "T": [(20, 6)]}
    game_id, deployment_ = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    t, v = _unit_named(deployment_, "T"), _unit_named(deployment_, "V")
    await _give(session, t, "Data-spike")
    [ability] = (await client.get(f"/games/{game_id}/shooting-start")).json()
    assert (ability["ability"], [x["unit_id"] for x in ability["targets"]]) == ("Data-spike", [v["unit_id"]])
    response = await client.post(f"/games/{game_id}/shooting-start", json={
        "unit_id": t["unit_id"], "ability": "Data-spike", "target_unit_id": v["unit_id"],
    })
    assert response.status_code == 200, response.text
    game_ = await _load_game(session, game_id)
    v_unit = deployment.find_unit(game_, v["unit_id"])
    assert len(deployment.models_on_battlefield(game_, v_unit)) == 1  # 6 wounds: 3 of 4 models
    assert unit_effects.own_attack_rules(game_, v_unit)


async def test_matter_absorption(client: AsyncClient, session, tmp_path, monkeypatch):
    # Seat 2's C (wounded) uses it at the start of its Shooting phase on seat
    # 1's VEHICLE V within 12": a 3 - 3 mortal wounds, and C regains up to 3.
    from tests import live_games

    units = {1: [("V", 3, {"keywords": ("VEHICLE",)})], 2: [("C", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units,
                                      spots={"V": (20, 38), "C": (20, 4)})
    game_id = game["id"]
    v, c = _unit_named(deployment_, "V"), _unit_named(deployment_, "C")
    await _give(session, c, "Matter Absorption")
    await _place(session, v, [(20, 14), (21.5, 14), (23, 14)])
    live_games.damage(game_id, c["models"][0]["unit_model_id"], wounds_lost=1)
    await _to_shooting(client, game_id)
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 3)
    response = await client.post(f"/games/{game_id}/shooting-start", json={
        "unit_id": c["unit_id"], "ability": "Matter Absorption", "target_unit_id": v["unit_id"],
    })
    assert response.status_code == 200, response.text
    game_ = await _load_game(session, game_id)
    from app.services.in_game import casualties

    assert casualties.wounds_remaining(game_, deployment.find_unit(game_, c["unit_id"])) == {
        c["models"][0]["unit_model_id"]: 2
    }
    assert sum(casualties.wounds_remaining(game_, deployment.find_unit(game_, v["unit_id"])).values()) == 3


def test_achillan_eye(monkeypatch):
    from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech
    from tests.test_combat import _keyword

    for weapon_name, keywords, rerolled in (
        ("Radium jezzail", ["INFANTRY"], True),
        ("Radium jezzail", ["VEHICLE"], False),
        ("Skatros transuranic arquebus", ["VEHICLE"], True),
        ("Skatros transuranic arquebus", ["INFANTRY"], False),
    ):
        rolls = iter([6, 2, 6, 1])  # hit, wound 2 (fails S4 vs T8), re-roll, save
        monkeypatch.setattr("app.services.dice.randint", lambda a, b: next(rolls, 1))
        weapon = _weapon(name=weapon_name, attacks="1", skill=3, strength=4, ap=0, damage="1",
                         weapon_type="ranged")
        weapon.id = 1
        attacker = _unit([_unit_model(_model(), [weapon])])
        defender = _unit([_unit_model(
            _model(toughness=8, wounds=10, save=7, keywords=[_keyword(k) for k in keywords]), []
        )])
        result = _resolve(attacker, defender, weapon, attacker_rules=admech.RULES["Achillan Eye"])
        assert bool(result.wound_rerolls) == rerolled, weapon_name


async def test_dread_snipers(client: AsyncClient, session, tmp_path, monkeypatch):
    from tests.test_shooting import _shoot, _shooting_game

    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 6)
    game, deployment_ = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _give(session, d, "Dread Snipers")
    await _place(session, a, [(20, 22)])
    await _to_shooting(client, game_id)
    assert (await _shoot(client, game_id, d, a)).status_code == 200
    game_ = await _load_game(session, game_id)
    assert [t.unit_id for t in battle_shock.pending(game_)] == [a["unit_id"]]


async def test_sydonian_sentinel_cant_be_warlord(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path)
    a = _unit_named(deployment_, "A")
    await _give(session, a, "Sydonian Sentinel")
    list_id = next(p["list_id"] for p in game["players"] if p["seat"] == 1)
    assert await warlord_reason(session, list_id, a["unit_id"]) == "A can't be the list's Warlord"
