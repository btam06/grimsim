from app.combat_rules import Rule
from app.combat_rules.conditions import CRITICAL_HIT
from app.combat_rules.effects import ADD_EXTRA_HIT
from app.models import DatasheetAbility
from app.seeds import datasheet_abilities as ability_seeds
from tests.test_admech_datasheets import _gun, _shooter, _with
from tests.test_combat import _keyword, _model, _unit, _unit_model
from tests.test_sororitas_datasheets import _melee
from tests.test_sororitas_units import _resolve, _rolls, _target

# The Necron datasheet abilities added from the 11th edition datasheets (see
# app/seeds/factions/necrons/datasheet_abilities.py).

_SUSTAINED = Rule(conditions=(CRITICAL_HIT,), effects=(ADD_EXTRA_HIT,))


def test_implacable_eradication_rerolls_against_units_on_objectives(monkeypatch):
    rules = ability_seeds.RULES["Implacable Eradication"]
    gun = _gun(skill=3)
    # A hit; a Wound roll of 2 fails - re-rolled to a 4 only on an objective.
    _rolls(monkeypatch, [3, 2, 4, 1])
    on = {"defender_positions": {"in_range_of_objective"}}
    assert _resolve(_shooter(gun), _target(), attacker_rules=rules, **on).total_damage == 1
    _rolls(monkeypatch, [3, 2, 4, 1])
    assert _resolve(_shooter(gun), _target(), attacker_rules=rules).total_damage == 0


def test_flesh_hunger_makes_successful_hits_critical(monkeypatch):
    rules = ability_seeds.RULES["Flesh Hunger"] + [_SUSTAINED]
    flayers = _unit([_unit_model(_model(), [_melee(skill=3)])])
    below = {"defender_positions": {"below_half_strength"}}
    # A 3 to hit: a Critical Hit against a Below Half-strength unit - two hits.
    _rolls(monkeypatch, [3, 4, 4, 1, 1])
    result = _resolve(flayers, _target(), in_engagement_range=True, attacker_rules=rules, **below)
    assert result.total_damage == 2
    _rolls(monkeypatch, [3, 4, 4, 1, 1])
    result = _resolve(flayers, _target(), in_engagement_range=True, attacker_rules=rules)
    assert result.total_damage == 1


def test_the_silent_kings_damaged_profile_halves_szarekhs_attacks(monkeypatch):
    rules = ability_seeds.RULES["Damaged: 1-6 Wounds Remaining (Szarekh)"]
    name = "Damaged: 1-6 Wounds Remaining (Szarekh)"
    szarekh = _model(wounds=16, abilities=[DatasheetAbility(name=name, description=None)])
    unit = _unit([_unit_model(szarekh, [_melee(attacks="6")])])
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: 6)
    whole = _resolve(unit, _target(save=7), in_engagement_range=True, attacker_rules=rules)
    damaged = _resolve(
        unit, _target(save=7), in_engagement_range=True, attacker_rules=rules, attacker_damaged=True
    )
    assert (whole.total_damage, damaged.total_damage) == (6, 3)


def test_mechanical_augmentation_reaches_only_battleline():
    [option] = ability_seeds.OPTIONS["Mechanical Augmentation (Aura)"].values()
    assert option.aura_range == 3.0 and option.aura_keywords == ("BATTLELINE",)
    assert {r.side for r in option.rules} == {"attacker", "defender"}
    growth = ability_seeds.AURA_RANGE_GROWTH["Atomic Energy Manipulator"]
    assert (growth["by"], growth["most"]) == (3.0, 12.0)


def test_the_new_tables_are_wired_up():
    assert ability_seeds.SNAP_SHOTS_ON["Inescapable Death"] == 2
    assert ability_seeds.SNAP_SHOTS_ON["Sentinel Construct"] == 5
    assert ability_seeds.SHOOT_SCOOT["Evasion Engrams"]["reach"] == 6.0
    assert "Relentless Combatants" in ability_seeds.CHARGE_REROLLS
    assert ability_seeds.COMMAND_START_CP["Grand Strategist"] == 1
    assert "Quantum Invader" in ability_seeds.FIRST_ROUND_INGRESS
    assert ability_seeds.FIGHTS_ON_DEATH["Systematic Vigour"] == 2
    assert "Terrifying Monstrosity" in ability_seeds.FIGHT_START_BATTLE_SHOCK
    assert ability_seeds.START_OF_SHOOTING["Living Lightning"]["dice"] == 4
    assert "Lord of the Storm" in ability_seeds.ACTIVATIONS
    assert "Hyperspace Hunters" in ability_seeds.REACTIVE_SHOTS


# --- in a game ---


async def _game(client, session, tmp_path, units=None):
    from tests.test_movement import _battle

    return await _battle(client, session, tmp_path, units=units)


async def test_lord_of_the_storm_once_a_battle(client, session, tmp_path, monkeypatch):
    from app.routers.games import _load_game
    from app.services.in_game import activations, casualties, deployment
    from tests.test_deployment import _unit_named
    from tests.test_shooting import _place

    game, deployment_ = await _game(client, session, tmp_path, {1: [("A", 5, {})], 2: [("D", 1, {})]})
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, d, "Lord of the Storm")
    await _place(session, d, [(20, 30)])
    game_ = await _load_game(session, game["id"])
    game_.phase = "command"
    imotekh = deployment.find_unit(game_, d["unit_id"])
    # (At the end of the Command phase: its end step.)
    [lord] = [x for x in activations.available(game_, 2) if x.ability == "Lord of the Storm"]
    assert lord.reason == "it's used at the end of the phase"
    from app.services.in_game import phase_end

    assert phase_end.to_open(game_)
    phase_end.open(game_)
    [lord] = [x for x in activations.available(game_, 2) if x.ability == "Lord of the Storm"]
    assert lord.reason is None
    # A 6: D3+3 (a 2 on the D3 -> 5) to A, within 12".
    rolls = iter([6, 2])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: next(rolls, 1))
    activations.use(game_, imotekh, "Lord of the Storm")
    damage = casualties.damage(game_)
    assert sum(damage[m["unit_model_id"]].wounds_lost for m in a["models"] if m["unit_model_id"] in damage) == 5
    [lord] = [x for x in activations.available(game_, 2) if x.ability == "Lord of the Storm"]
    assert lord.reason == "it's been used"


async def test_tectonic_reverberations_pins_and_gravitic_pulse_halves(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import activations, deployment, movement
    from tests.test_deployment import _unit_named
    from tests.test_shooting import _place

    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _game(client, session, tmp_path, units)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, d, "Tectonic Reverberations")
    await _with(session, a, "Gravitic Pulse")
    await _place(session, d, [(20, 30)])
    game_ = await _load_game(session, game["id"])
    geomancer, enemy = deployment.find_unit(game_, d["unit_id"]), deployment.find_unit(game_, a["unit_id"])
    base_move = enemy.unit_models[0].model.movement
    # (The abilities were added once the phase had begun: its start step
    # again, as if they'd been there.)
    game_.phase_start_uses.clear()
    # Seat 2's Movement phase: D pins A (-2" Move).
    activations.use(game_, geomancer, "Tectonic Reverberations", enemy)
    assert movement.move_characteristic(game_, enemy, enemy.unit_models[0]) == base_move - 2
    # And A - its opponent's turn - halves D's Move.
    activations.use(game_, enemy, "Gravitic Pulse", geomancer)
    assert activations.halved(game_, geomancer)
    m = geomancer.unit_models[0]
    assert movement.move_characteristic(game_, geomancer, m) == m.model.movement - m.model.movement // 2


async def test_triarch_abilities_choose_an_aura(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import activations, auras, deployment
    from tests.test_deployment import _unit_named

    game, deployment_ = await _game(client, session, tmp_path)
    d = _unit_named(deployment_, "D")
    await _with(session, d, "Triarch Abilities", keywords=("NECRONS",))
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, d["unit_id"])
    # (At the start of the battle round - and one must be selected then.)
    from app.services.in_game import battle_round

    game_.phase = battle_round.START_OF_ROUND
    [triarch] = [x for x in activations.available(game_, 2) if x.ability == "Triarch Abilities"]
    assert "Relentless March" in triarch.options
    assert any("Triarch Abilities" in m for m in battle_round.missing_choices(game_))
    activations.use(game_, unit, "Triarch Abilities", option="Relentless March")
    assert not any("Triarch Abilities" in m for m in battle_round.missing_choices(game_))
    assert activations.chosen(game_, unit, "Triarch Abilities") == "Relentless March"
    # (Its own unit's within range of itself.)
    assert auras.move_bonus(game_, unit) == 2


async def test_carrier_wave_adds_oc_and_the_silent_king_leadership(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import battle_shock, deployment, objectives
    from tests.test_deployment import _unit_named
    from tests.test_shooting import _place

    units = {1: [("A", 1, {})], 2: [("D", 1, {}), ("E", 1, {})]}
    spots = {"A": (20, 38), "D": (20, 4), "E": (30, 4)}
    from tests.test_movement import _battle

    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    d, e = _unit_named(deployment_, "D"), _unit_named(deployment_, "E")
    await _with(session, d, "Carrier Wave (Aura)")
    await _with(session, d, "The Silent King")
    await _with(session, e, "Plain", keywords=("NECRONS",))
    await _place(session, e, [(23, 4)])
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, e["unit_id"])
    model = unit.unit_models[0]
    assert objectives.model_oc(game_, model) == (model.model.oc or 0) + 1
    assert battle_shock.leadership_improved(game_, unit) == 1


async def test_drain_life_wounds_each_enemy_unit_nearby(client, session, tmp_path, monkeypatch):
    from app.routers.games import _load_game
    from app.services.in_game import casualties, phase_end
    from tests.test_deployment import _unit_named
    from tests.test_shooting import _place

    game, deployment_ = await _game(client, session, tmp_path, {1: [("A", 5, {})], 2: [("D", 1, {})]})
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, d, "Drain Life")
    await _place(session, d, [(20, 34)])
    game_ = await _load_game(session, game["id"])
    game_.phase = "fight"
    # A 4+ and D3 of 2: 2 mortal wounds to A, within 6".
    rolls = iter([4, 2])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: next(rolls, 1))
    phase_end.mortals(game_)
    damage = casualties.damage(game_)
    assert sum(damage[m["unit_model_id"]].wounds_lost for m in a["models"] if m["unit_model_id"] in damage) == 2


async def test_the_menhirs_are_destroyed_with_szarekh(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import casualties, deployment
    from tests.test_deployment import _unit_named

    game, deployment_ = await _game(client, session, tmp_path, {1: [("A", 3, {})], 2: [("D", 1, {})]})
    a = _unit_named(deployment_, "A")
    # Every model in A has the ability; the first is a CHARACTER (Szarekh).
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Keyword, Model, UnitModel

    ability = DatasheetAbility(name="Triarchal Menhirs", description="x")
    for i, m in enumerate(a["models"]):
        unit_model = await session.get(UnitModel, m["unit_model_id"])
        model = (
            await session.execute(
                select(Model)
                .options(selectinload(Model.abilities), selectinload(Model.keywords))
                .where(Model.id == unit_model.model_id)
            )
        ).scalar_one()
        if ability not in model.abilities:
            model.abilities.append(ability)
        if i == 0:
            szarekh = Model(name="Szarekh", faction_id=model.faction_id, save=2, toughness=10, oc=6,
                            movement=8, wounds=16, leadership=6, base_size=None)
            character = (
                await session.execute(select(Keyword).where(Keyword.name == "CHARACTER"))
            ).scalar_one_or_none() or Keyword(name="CHARACTER")
            szarekh.keywords = [*model.keywords, character]
            szarekh.abilities = [ability]
            session.add(szarekh)
            await session.flush()
            unit_model.model_id = szarekh.id
    await session.commit()
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, a["unit_id"])
    character = next(m for m in unit.unit_models if any(k.name == "CHARACTER" for k in m.model.keywords))
    casualties._lose(game_, character, character.wounds)
    damage = casualties.damage(game_)
    assert all(damage[m.id].destroyed for m in unit.unit_models)


async def test_hyperspace_hunters_can_shoot_a_unit_that_arrived(client, session, tmp_path):
    from app.engine.state import GameUnitMove
    from app.routers.games import _load_game
    from app.services.in_game import deployment, reactive_shots, reinforcements
    from tests.test_deployment import _unit_named
    from tests.test_shooting import _place

    game, deployment_ = await _game(client, session, tmp_path, {1: [("A", 1, {})], 2: [("D", 1, {})]})
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, a, "Hyperspace Hunters")
    await _place(session, d, [(20, 25)])
    game_ = await _load_game(session, game["id"])
    # Seat 2's Movement phase: nothing's arrived yet.
    assert reactive_shots.available(game_) == []
    game_.unit_moves.append(
        GameUnitMove(
            unit_id=d["unit_id"], battle_round=game_.battle_round, turn_seat=game_.turn_seat,
            kind=reinforcements.ARRIVED, completed=True,
        )
    )
    [shot] = reactive_shots.available(game_)
    assert shot.ability == "Hyperspace Hunters" and [t.id for t in shot.targets] == [d["unit_id"]]
    reactive_shots.record(game_, deployment.find_unit(game_, a["unit_id"]), "Hyperspace Hunters")
    assert reactive_shots.available(game_) == []


async def test_translocation_shroud_advances_6(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import deployment, movement
    from tests.test_deployment import _unit_named

    game, deployment_ = await _game(client, session, tmp_path)
    d = _unit_named(deployment_, "D")
    await _with(session, d, "Translocation Shroud")
    game_ = await _load_game(session, game["id"])
    move = movement.roll_advance(game_, deployment.find_unit(game_, d["unit_id"]))
    assert move.advance_roll == movement.SHROUD_ADVANCE
    assert movement.through(game_, deployment.find_unit(game_, d["unit_id"]), "advance") == "all"


async def test_repair_barge_reanimates_hurt_necron_warriors(client, session, tmp_path, monkeypatch):
    from app.routers.games import _load_game
    from app.seeds.factions.necrons import unit_abilities as necrons
    from app.services.in_game import casualties, deployment
    from tests.test_deployment import _unit_named
    from tests.test_shooting import _place

    units = {1: [("A", 1, {})], 2: [("D", 3, {"keywords": ("NECRON WARRIORS",)}), ("E", 1, {})]}
    spots = {"A": (20, 38), "D": (20, 4), "E": (30, 4)}
    from tests.test_movement import _battle

    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    d, e = _unit_named(deployment_, "D"), _unit_named(deployment_, "E")
    await _with(session, e, "Repair Barge")
    await _place(session, e, [(24, 4)])
    game_ = await _load_game(session, game["id"])
    warriors = deployment.find_unit(game_, d["unit_id"])
    first = warriors.unit_models[0]
    casualties._lose(game_, first, 1)
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 1)
    necrons.repair_barge(game_, [(warriors, 1)])
    assert casualties.damage(game_)[first.id].wounds_lost == 0
    # Once a turn.
    casualties._lose(game_, first, 1)
    necrons.repair_barge(game_, [(warriors, 1)])
    assert casualties.damage(game_)[first.id].wounds_lost == 1


async def test_a_retinue_is_recognised_by_its_ability(session):
    from app.models import Faction, Model
    from app.routers.units import RETINUES, _retinue

    faction = Faction(name="Retinue Test")
    session.add(faction)
    await session.flush()
    model = Model(name="Cryptothrall", faction_id=faction.id, save=4, toughness=5, oc=1, movement=5, wounds=2,
                  leadership=7)
    model.abilities = [DatasheetAbility(name="Cryptek Retinue", description="x")]
    plain = Model(name="Immortal", faction_id=faction.id, save=3, toughness=5, oc=2, movement=5, wounds=1,
                  leadership=7)
    session.add_all([model, plain])
    await session.commit()
    assert "Cryptek Retinue" in RETINUES
    assert await _retinue(session, [model])
    assert not await _retinue(session, [plain])


async def test_the_activation_and_reactive_shot_routes(client, session, tmp_path):
    from tests.test_deployment import _unit_named
    from tests.test_shooting import _place

    game, deployment_ = await _game(client, session, tmp_path)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, d, "Tectonic Reverberations")
    await _place(session, d, [(20, 30)])
    game_id = game["id"]
    [activation] = (await client.get(f"/games/{game_id}/activations")).json()
    assert activation["ability"] == "Tectonic Reverberations" and activation["reason"] is None
    assert [t["unit_id"] for t in activation["targets"]] == [a["unit_id"]]
    response = await client.post(
        f"/games/{game_id}/activations",
        json={"unit_id": d["unit_id"], "ability": "Tectonic Reverberations", "target_unit_id": a["unit_id"]},
    )
    assert response.status_code == 200, response.text
    assert "Move" in response.json()["note"]
    [activation] = response.json()["activations"]
    assert activation["reason"] == "it's been used"
    assert (await client.get(f"/games/{game_id}/reactive-shots")).json() == []
    response = await client.post(
        f"/games/{game_id}/reactive-shots",
        json={"unit_id": a["unit_id"], "target_unit_id": d["unit_id"], "ability": "Hyperspace Hunters"},
    )
    assert response.status_code == 400
