from app.seeds import datasheet_abilities as ability_seeds
from tests.test_admech_datasheets import _gun, _shooter, _with
from tests.test_combat import _keyword
from tests.test_sororitas_units import _resolve, _rolls, _target

# The Chaos Knights datasheet abilities added from the 11th edition
# datasheets (see app/seeds/factions/chaos_knights/datasheet_abilities.py).


def test_macro_extinction_protocols(monkeypatch):
    rules = ability_seeds.RULES["Macro-extinction Protocols"]
    gun = _gun(skill=4, strength=4)
    tank = _target(keywords=[_keyword("VEHICLE")], toughness=4)
    knight = _target(keywords=[_keyword("VEHICLE"), _keyword("TITANIC")], toughness=4)
    # A 3 hits a VEHICLE with +1; a 3 to wound (S4 vs T4 needs 4+) only with
    # +1 against a TITANIC one.
    _rolls(monkeypatch, [3, 3, 1])
    assert _resolve(_shooter(gun), tank, attacker_rules=rules).total_damage == 0
    _rolls(monkeypatch, [3, 3, 1])
    assert _resolve(_shooter(gun), knight, attacker_rules=rules).total_damage == 1
    _rolls(monkeypatch, [3, 4, 1])
    assert _resolve(_shooter(gun), _target(), attacker_rules=rules).total_damage == 0


def test_seething_hatred_rerolls_one_failed_hit(monkeypatch):
    rules = ability_seeds.RULES["Seething Hatred"]
    gun = _gun(attacks="2", skill=4)
    # Two misses (1, 1): one re-rolled to a hit (6), which wounds (4).
    _rolls(monkeypatch, [1, 1, 6, 4, 1])
    assert _resolve(_shooter(gun), _target(), attacker_rules=rules).total_damage == 1
    _rolls(monkeypatch, [1, 1, 6, 4, 1])
    assert _resolve(_shooter(gun), _target()).total_damage == 0


def test_sunderer_of_fortresses_against_vehicles(monkeypatch):
    rules = ability_seeds.RULES["Sunderer of Fortresses"]
    gun = _gun(skill=3, strength=4, damage="1")
    tank = _target(keywords=[_keyword("VEHICLE")], toughness=5)
    # S5 vs T5: a 4 wounds; D2.
    _rolls(monkeypatch, [3, 4, 1])
    assert _resolve(_shooter(gun), tank, attacker_rules=rules).total_damage == 2


def test_war_dog_auras_reach_only_war_dogs():
    for ability in ("Taskmaster (Aura)", "Preysight (Aura)", "Dark Fervour (Aura)"):
        [option] = ability_seeds.OPTIONS[ability].values()
        assert option.aura_keywords == ("WAR DOG",)
    assert ability_seeds.QUARRIES["Methodical Destruction"]["again_with"] == "always"
    assert ability_seeds.REINFORCEMENT_DENIAL["Bastion of Corruption"] == 12.0
    assert ability_seeds.AFTER_SHOOTING_EFFECTS["Storm of Bolts"].hit == -1
    assert ability_seeds.RESERVE_ROUND_BONUS["Bestial Raiders"] == 1


# --- in a game ---


async def test_storm_of_bolts_suppresses_while_its_source_is_there(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import casualties, deployment, unit_effects
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle

    game, deployment_ = await _battle(client, session, tmp_path)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, d, "Storm of Bolts")
    game_ = await _load_game(session, game["id"])
    game_.phase = "shooting"
    castigator, target = deployment.find_unit(game_, d["unit_id"]), deployment.find_unit(game_, a["unit_id"])
    unit_effects.after_shooting(game_, castigator, target, 1)
    [rule] = unit_effects.own_attack_rules(game_, target)
    assert rule.effects == ("minus_one_to_hit",)
    # Once the Castigator's gone, it isn't.
    for m in castigator.unit_models:
        casualties._lose(game_, m, m.wounds)
    assert unit_effects.own_attack_rules(game_, target) == []


async def test_methodical_destruction_selects_a_new_victim(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import casualties, deployment, quarry
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle

    units = {1: [("A", 1, {}), ("B", 1, {})], 2: [("D", 1, {})]}
    spots = {"A": (20, 38), "B": (30, 38), "D": (20, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    a, b, d = (_unit_named(deployment_, n) for n in "ABD")
    await _with(session, d, "Methodical Destruction")
    game_ = await _load_game(session, game["id"])
    ruinator = deployment.find_unit(game_, d["unit_id"])
    victim = deployment.find_unit(game_, a["unit_id"])
    quarry.select(game_, ruinator, victim)
    assert quarry.reason(game_, ruinator) == "its quarry hasn't been destroyed"
    for m in victim.unit_models:
        casualties._lose(game_, m, m.wounds)
    assert quarry.reason(game_, ruinator) is None
    quarry.select(game_, ruinator, deployment.find_unit(game_, b["unit_id"]))
    assert quarry.quarry_of(game_, ruinator) == b["unit_id"]


async def test_dark_ritual_lets_it_charge_after_advancing(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import activations, command_phase, deployment
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle

    game, deployment_ = await _battle(client, session, tmp_path)
    d = _unit_named(deployment_, "D")
    await _with(session, d, "Dark Ritual")
    game_ = await _load_game(session, game["id"])
    game_.phase = "command"
    unit = deployment.find_unit(game_, d["unit_id"])
    assert not command_phase.eligible_after(game_, unit, "advanced", "charge")
    activations.use(game_, unit, "Dark Ritual")
    assert command_phase.eligible_after(game_, unit, "advanced", "charge")
    [rule] = activations.own_rules(game_, unit)
    assert set(rule.effects) == {"plus_one_to_hit", "plus_one_to_wound"}
