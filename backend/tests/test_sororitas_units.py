from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import DatasheetAbility, Keyword, Model, UnitModel
from app.routers.games import _load_game
from app.seeds import datasheet_abilities as ability_seeds
from app.seeds.factions.adepta_sororitas import unit_abilities
from app.services import combat
from app.services.combat import WeaponBonus
from app.services.in_game import battle_shock, casualties, deployment
from tests import live_games
from tests.test_acts_of_faith import _pool, _sororitas_game
from tests.test_combat import _doctrina_combat, _keyword, _model, _unit, _unit_model, _weapon
from tests.test_dread import _ability
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place

# The Adepta Sororitas datasheets' abilities (see
# app/seeds/factions/adepta_sororitas/unit_abilities.py and its
# datasheet_abilities.py). Games from test_acts_of_faith: seat 2's army is
# Adepta Sororitas, its unit "D" (3 models, 2 W) ADEPTA SORORITAS, in seat
# 2's movement phase; seat 1's "A" (3 models).


def _rolls(monkeypatch, values, default=1):
    rolls = iter(values)
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: next(rolls, default))


# --- the combat rules ---


def _led_unit(weapon):
    # A CHARACTER leading another model, both with the weapon.
    weapon.id = 1
    return _unit(
        [
            _unit_model(_model(keywords=[_keyword("CHARACTER")]), [weapon]),
            _unit_model(_model(), []),
        ]
    )


def _resolve(attacker, defender, **kwargs):
    options = dict(
        in_engagement_range=False, visible=True, in_range=True, in_cover=False,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    options.update(kwargs)
    return combat.resolve_combat(attacker, defender, {1}, **options)


def _target(**overrides):
    return _unit([_unit_model(_model(**{"toughness": 4, "wounds": 10, "save": 7, **overrides}), [])])


def test_fury_of_the_righteous_lethal_hits_while_leading(monkeypatch):
    rules = ability_seeds.RULES["Fury of the Righteous"]
    weapon = _weapon(attacks="1", skill=3, strength=1, ap=0, weapon_type="ranged")
    # A 6 to hit (a Critical Hit), then a failed Wound roll: wounds anyway.
    _rolls(monkeypatch, [6, 1])
    assert _resolve(_led_unit(weapon), _target(), attacker_rules=rules).total_damage == 1
    _rolls(monkeypatch, [6, 1])
    assert _resolve(_led_unit(weapon), _target()).total_damage == 0


def test_abbess_sanctorum_rerolls_while_leading(monkeypatch):
    rules = ability_seeds.RULES["Abbess Sanctorum"]
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged")
    # A failed Hit roll re-rolled to a 3, a failed Wound roll re-rolled to a 4.
    _rolls(monkeypatch, [1, 3, 1, 4, 1])
    assert _resolve(_led_unit(weapon), _target(), attacker_rules=rules).total_damage == 1


def test_medicus_ministorum_feel_no_pain_while_leading(monkeypatch):
    rules = ability_seeds.RULES["Medicus Ministorum"]
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged", damage="1")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    led = _unit(
        [
            _unit_model(_model(keywords=[_keyword("CHARACTER")], save=7, wounds=3), []),
            _unit_model(_model(save=7, wounds=3), []),
        ]
    )
    # Hit, wound, (no save), then a 5: Feel No Pain.
    _rolls(monkeypatch, [3, 4, 1, 5])
    assert _resolve(attacker, led, defender_rules=rules).total_damage == 0


def test_weapon_bonuses_in_combat(monkeypatch):
    lance = _weapon(name="Lance of Illumination – strike", attacks="1", skill=2, strength=8,
                    ap=0, weapon_type="melee", range=None, damage="1")
    lance.id = 1
    attacker = _unit([_unit_model(_model(), [lance])])
    attacker.unit_models[0].id = 5
    # +3 A for the named weapon: 4 attacks (all hit and wound on 6s; no save).
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: 6)
    bonus = {5: [WeaponBonus(attacks=3, melee_only=False, names=("Lance of Illumination",))]}
    result = _resolve(attacker, _target(save=7), in_engagement_range=True, weapon_bonuses=bonus)
    assert result.total_damage == 4
    # Not a weapon it doesn't name.
    other = {5: [WeaponBonus(attacks=3, names=("Fidelis",))]}
    result = _resolve(attacker, _target(save=7), in_engagement_range=True, weapon_bonuses=other)
    assert result.total_damage == 1


def test_devastating_and_mortal_wound_bonuses(monkeypatch):
    blade = _weapon(attacks="1", skill=2, strength=4, ap=0, weapon_type="melee", range=None,
                    damage="2")
    blade.id = 1
    attacker = _unit([_unit_model(_model(), [blade])])
    attacker.unit_models[0].id = 5
    target = _target(save=2)
    # Hit, wound on a 6: with [DEVASTATING WOUNDS], no save - 2 damage.
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: 6)
    devastating = {5: [WeaponBonus(devastating=True)]}
    result = _resolve(attacker, target, in_engagement_range=True, weapon_bonuses=devastating)
    assert (result.save_rolls, result.total_damage) == ([], 2)
    # Rapturous Blows: hit, wound (4), saved (a 6) - still 1 mortal wound.
    _rolls(monkeypatch, [4, 4, 6], default=6)
    mortal = {5: [WeaponBonus(mortal_on_wound=True)]}
    result = _resolve(attacker, _target(save=2), in_engagement_range=True, weapon_bonuses=mortal)
    assert result.total_damage == 1


# --- in a game ---


async def test_righteous_repugnance_discards_for_attacks(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, unit_abilities.RIGHTEOUS_REPUGNANCE)
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    _pool(game_id, values=[2, 5])
    # Not in the Movement phase.
    assert unit_abilities.discard_options(game, unit) == []
    game.phase = "shooting"
    assert unit_abilities.discard_options(game, unit) == [unit_abilities.RIGHTEOUS_REPUGNANCE]
    unit_abilities.use_discards(game, unit, {unit_abilities.RIGHTEOUS_REPUGNANCE: 2})
    assert _pool(game_id) == [5]
    bonuses = unit_abilities.weapon_bonuses(game, unit, casualties.wounds_remaining(game, unit))
    assert {b.attacks for bs in bonuses.values() for b in bs} == {3}
    # Once as it's selected.
    assert unit_abilities.discard_options(game, unit) == []


async def test_righteous_repugnance_gains_a_dice_for_a_kill(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, unit_abilities.RIGHTEOUS_REPUGNANCE)
    game = await _load_game(session, game_id)
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 4)
    enemy, unit = (deployment.find_unit(game, u["unit_id"]) for u in (a, d))
    casualties.mortal_wounds(game, enemy, 10, destroyed_by=unit)
    assert _pool(game_id) == [4]


async def test_judged_for_execution(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, unit_abilities.JUDGED_FOR_EXECUTION)
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    state = (await client.get(f"/games/{game_id}/judged-for-execution")).json()
    assert [t["name"] for t in state["units"][0]["targets"]] == ["A"]
    response = await client.post(
        f"/games/{game_id}/judged-for-execution",
        json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"]},
    )
    assert response.status_code == 200, response.text
    assert [j["name"] for j in response.json()["judged"]] == ["A"]
    game = await _load_game(session, game_id)
    unit, enemy = (deployment.find_unit(game, u["unit_id"]) for u in (d, a))
    assert unit_abilities.attack_rules(game, unit, enemy)
    # Not the enemy's attacks.
    assert unit_abilities.attack_rules(game, enemy, unit) == []
    # Through the opponent's turn; over at the start of their next Command
    # phase.
    await _advance_to(client, game_id, 1, 1, "fight")
    assert unit_abilities.attack_rules(game, unit, enemy)
    await _advance_to(client, game_id, 2, 2, "command")
    assert unit_abilities.attack_rules(game, unit, enemy) == []


async def test_righteous_denunciation_at_the_start_of_the_fight_phase(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, unit_abilities.RIGHTEOUS_DENUNCIATION)
    # A within 6" of D (at y 4): 4" away.
    await _place(session, a, [(20 + 1.5 * i, 4 + 1.26 + 4) for i in range(3)])
    game = await _load_game(session, game_id)
    game.phase = "fight"
    battle_shock.start_of_fight(game)
    [test] = battle_shock.pending(game)
    assert (test.unit_id, test.reason, test.modifier) == (
        a["unit_id"], unit_abilities.RIGHTEOUS_DENUNCIATION, -1
    )


async def _hospitaller(session, d):
    # D's first model becomes a Hospitaller (a CHARACTER with Sacred
    # Healing), leading the other two.
    unit_model = await session.get(UnitModel, d["models"][0]["unit_model_id"])
    old = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.keywords), selectinload(Model.base_size))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    character = (
        await session.execute(select(Keyword).where(Keyword.name == "CHARACTER"))
    ).scalar_one_or_none() or Keyword(name="CHARACTER")
    healer = Model(
        name="Hospitaller", faction_id=old.faction_id, save=3, toughness=3, oc=1, movement=6,
        wounds=3, leadership=7, base_size=old.base_size,
    )
    healer.keywords = [*old.keywords, character]
    healer.abilities = [DatasheetAbility(name=unit_abilities.SACRED_HEALING)]
    session.add(healer)
    await session.flush()
    unit_model.model_id = healer.id
    await session.commit()


async def test_sacred_healing_returns_destroyed_models(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _hospitaller(session, d)
    for m in d["models"][1:]:
        live_games.damage(game_id, m["unit_model_id"], wounds_lost=2, destroyed=True)
        live_games.remove_position(m["unit_model_id"], game_id)
    # Only in its own Command phase.
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    assert "Command phase" in unit_abilities.healing_reason(game, unit)
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[3])
    state = next(p for p in (await client.get(f"/games/{game_id}/miracle-dice")).json())
    assert [(h["unit_id"], h["destroyed"]) for h in state["sacred_healing"]] == [
        (d["unit_id"], 2)
    ]
    # Discarding: D3+1 (2+1) - both return, with full wounds, to be set up.
    _rolls(monkeypatch, [2])
    response = await client.post(
        f"/games/{game_id}/sacred-healing", json={"unit_id": d["unit_id"], "discard": 3}
    )
    assert response.status_code == 200, response.text
    assert _pool(game_id) == []
    reanimation = (await client.get(f"/games/{game_id}/reanimation")).json()
    assert reanimation["placing"]
    [returned] = reanimation["units"]
    assert (returned["unit_id"], returned["roll"], len(returned["to_place"])) == (
        d["unit_id"], None, 2
    )
    # Once a phase.
    response = await client.post(
        f"/games/{game_id}/sacred-healing", json={"unit_id": d["unit_id"]}
    )
    assert response.status_code == 400


async def test_sacred_command_discount(client: AsyncClient, session, tmp_path):
    assert ability_seeds.STRATAGEM_DISCOUNTS["Sacred Command"] == 1


def test_divine_deliverance_is_a_fight_ability():
    ability = ability_seeds.FIGHT_ABILITIES[unit_abilities.DIVINE_DELIVERANCE]
    assert ability.once_per_battle and ability.rules == ()


async def test_divine_deliverance_bonus_once_used(client: AsyncClient, session, tmp_path):
    from app.services.in_game import fight_abilities

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, unit_abilities.DIVINE_DELIVERANCE)
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    game.phase = "fight"
    wounds = casualties.wounds_remaining(game, unit)
    assert unit_abilities.weapon_bonuses(game, unit, wounds) == {}
    fight_abilities.use(game, unit, [unit_abilities.DIVINE_DELIVERANCE])
    # (Every model in this test unit has the ability.)
    assert unit_abilities.weapon_bonuses(game, unit, wounds) == {
        m["unit_model_id"]: [WeaponBonus(attacks=3, devastating=True)] for m in d["models"]
    }
    # Once a battle.
    assert fight_abilities.available(game, unit) == []


# --- the second batch ---


async def test_cherub_gains_a_dice_after_an_act_of_faith_once(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, "Cherub")
    _pool(game_id, values=[6])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 2)
    response = await client.post(
        f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"], "miracle_die": 6}
    )
    assert response.status_code == 200, response.text
    # The Miracle dice used; a Cherub's gained (a 2).
    assert _pool(game_id) == [2]
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    unit_abilities.act_of_faith_performed(game, unit)
    # Once a battle.
    assert _pool(game_id) == [2]


async def test_cherubs_twice(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, "Cherubs")
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 3)
    for _ in range(3):
        unit_abilities.act_of_faith_performed(game, unit)
    assert _pool(game_id) == [3, 3]


async def test_simulacrum_imperialis_on_a_held_objective(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    from app.models import Wargear
    from app.services.in_game import objectives

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    unit_model = await session.get(UnitModel, d["models"][0]["unit_model_id"])
    await session.refresh(unit_model, ["wargear"])
    unit_model.wargear.append(Wargear(name=unit_abilities.SIMULACRUM, model_id=unit_model.model_id))
    await session.commit()
    # D on the test layout's objective in the Medium ruin area (x 7-13, y 8-12).
    await _place(session, d, [(9 + 1.5 * i, 10) for i in range(3)])
    game = await _load_game(session, game_id)
    objectives.determine(game)
    _rolls(monkeypatch, [5])
    unit_abilities.simulacrum(game)
    assert _pool(game_id) == [5]
    # Once a turn.
    unit_abilities.simulacrum(game)
    assert _pool(game_id) == [5]


async def test_simulacrum_needs_a_4(client: AsyncClient, session, tmp_path, monkeypatch):
    from app.models import Wargear
    from app.services.in_game import objectives

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    unit_model = await session.get(UnitModel, d["models"][0]["unit_model_id"])
    await session.refresh(unit_model, ["wargear"])
    unit_model.wargear.append(Wargear(name=unit_abilities.SIMULACRUM, model_id=unit_model.model_id))
    await session.commit()
    await _place(session, d, [(9 + 1.5 * i, 10) for i in range(3)])
    game = await _load_game(session, game_id)
    objectives.determine(game)
    _rolls(monkeypatch, [3, 6])
    unit_abilities.simulacrum(game)
    unit_abilities.simulacrum(game)
    assert _pool(game_id) == []


async def test_storm_of_retribution_knows_who_killed_sisters(
    client: AsyncClient, session, tmp_path
):
    from app.routers.games import _attacker_positions
    from app.seeds.factions.adepta_sororitas.conditions import TARGET_KILLED_SORORITAS

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    unit, enemy = (deployment.find_unit(game, u["unit_id"]) for u in (d, a))
    assert TARGET_KILLED_SORORITAS not in _attacker_positions(game, unit, enemy)
    # (A stands in for another Sororitas unit of seat 2's: D itself is
    # destroyed by A - and then asked about from D's side.)
    casualties.mortal_wounds(game, unit, 10, destroyed_by=enemy)
    assert unit_abilities.killed_sororitas(game, enemy, 2)
    assert not unit_abilities.killed_sororitas(game, unit, 1)


def test_storm_of_retribution_in_combat(monkeypatch):
    rules = ability_seeds.RULES["Storm of Retribution"]
    from app.seeds.factions.adepta_sororitas.conditions import TARGET_KILLED_SORORITAS

    weapon = _weapon(attacks="1", skill=4, strength=4, ap=0, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    # A Hit roll of 1 re-rolled to a 3: misses (BS4) - unless +1 to hit.
    _rolls(monkeypatch, [1, 3, 4])
    assert _resolve(attacker, _target(), attacker_rules=rules).hits == 0
    _rolls(monkeypatch, [1, 3, 3])
    result = _resolve(
        attacker, _target(), attacker_rules=rules, attacker_positions={TARGET_KILLED_SORORITAS}
    )
    # Hits on the 3; wounds on a 3 (T4 S4 4+, with +1).
    assert (result.hits, result.total_damage) == (1, 1)


def test_sworn_protectors_and_smiting(monkeypatch):
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    led = _unit(
        [
            _unit_model(_model(keywords=[_keyword("CHARACTER")], save=7, wounds=3), []),
            _unit_model(_model(save=7, wounds=3), []),
        ]
    )
    # A Wound roll of 4 (S4 vs T4): -1 to wound makes it fail.
    _rolls(monkeypatch, [3, 4])
    assert _resolve(attacker, led).total_damage == 1
    _rolls(monkeypatch, [3, 4])
    assert (
        _resolve(attacker, led, defender_rules=ability_seeds.RULES["Sworn Protectors"])
        .total_damage == 0
    )
    # Righteous Smiting: +1 to wound for a led unit's melee attacks.
    blade = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="melee", range=None)
    _rolls(monkeypatch, [3, 3])
    result = _resolve(
        _led_unit(blade), _target(), attacker_rules=ability_seeds.RULES["Righteous Smiting"],
        in_engagement_range=True,
    )
    assert result.total_damage == 1


def test_anti_psyker(monkeypatch):
    from app.seeds import weapon_abilities

    _, _, conditions, effects = next(
        e for e in weapon_abilities.ENTRIES if e[0] == "Anti-Psyker 2+"
    )
    assert (conditions, effects) == (["anti_psyker_2"], ["force_critical_wound"])


def test_the_configs_are_combined():
    assert ability_seeds.SECURES_OBJECTIVES["Defenders of the Faith"] == "command"
    assert ability_seeds.REACTIVE_MOVES["Righteous Awareness"]["trigger_range"] == 8.0
    assert ability_seeds.AFTER_SHOOTING_EFFECTS["Rites of Castigation"].ranged_ap == 1
    assert "Devastating Refrain" in ability_seeds.AFTER_SHOOTING_BATTLE_SHOCK
    assert unit_abilities.ZEALOT in ability_seeds.FIGHT_ABILITIES


async def test_zealot_bonus_once_used(client: AsyncClient, session, tmp_path):
    from app.services.in_game import fight_abilities

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, unit_abilities.ZEALOT)
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    game.phase = "fight"
    fight_abilities.use(game, unit, [unit_abilities.ZEALOT])
    bonuses = unit_abilities.weapon_bonuses(game, unit, casualties.wounds_remaining(game, unit))
    assert {b for bs in bonuses.values() for b in bs} == {WeaponBonus(attacks=3, strength=3)}


# --- Devastating Refrain, Holy Mission, Holy Vanguard ---


def _refrain_combat(monkeypatch, rolls, refrain=True, indirect=True):
    from app.models import Effect, WeaponAbility

    abilities = [WeaponAbility(name="Indirect Fire")] if indirect else []
    gun = _weapon(attacks="1", skill=3, strength=10, ap=-5, damage="5", weapon_type="ranged")
    gun.id = 1
    gun.abilities = abilities
    shooter_abilities = [DatasheetAbility(name="Devastating Refrain")] if refrain else []
    attacker = _unit([_unit_model(_model(abilities=shooter_abilities), [gun])])
    demise = DatasheetAbility(name="Deadly Demise 1")
    demise.effects = [Effect(keyword="deadly_demise", name="Deadly Demise")]
    target = _unit([_unit_model(_model(wounds=5, save=7, abilities=[demise]), [])])
    _rolls(monkeypatch, rolls)
    return _resolve(attacker, target)


def test_devastating_refrain_counts_indirect_hits_and_demise_on_a_5(monkeypatch):
    # Hit, wound, a failed save, the model destroyed (5 damage), its Deadly
    # Demise roll a 5.
    result = _refrain_combat(monkeypatch, [3, 3, 1, 5])
    assert (result.indirect_hits, result.deadly_demise_explosions) == (1, 1)
    # Without Devastating Refrain, or with a weapon that isn't [INDIRECT FIRE]:
    # a 5 doesn't.
    assert _refrain_combat(monkeypatch, [3, 3, 1, 5], refrain=False).deadly_demise_explosions == 0
    result = _refrain_combat(monkeypatch, [3, 3, 1, 5], indirect=False)
    assert (result.indirect_hits, result.deadly_demise_explosions) == (0, 0)


async def test_devastating_refrain_tests_only_after_indirect_hits(
    client: AsyncClient, session, tmp_path
):
    from tests.test_shooting import _to_shooting

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, "Devastating Refrain")
    await _to_shooting(client, game_id)
    game = await _load_game(session, game_id)
    unit, enemy = (deployment.find_unit(game, u["unit_id"]) for u in (d, a))
    battle_shock.after_shooting(game, unit, enemy, hits=2, indirect_hits=0)
    assert battle_shock.pending(game) == []
    battle_shock.after_shooting(game, unit, enemy, hits=2, indirect_hits=1)
    [test] = battle_shock.pending(game)
    assert (test.unit_id, test.reason) == (a["unit_id"], "Devastating Refrain")


async def _keyworded_model(session, unit_model_id, name, keywords, abilities):
    # The unit model becomes a model of its own, with those keywords and
    # abilities.
    unit_model = await session.get(UnitModel, unit_model_id)
    old = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.keywords), selectinload(Model.base_size))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    rows = []
    for k in keywords:
        rows.append(
            (await session.execute(select(Keyword).where(Keyword.name == k))).scalar_one_or_none()
            or Keyword(name=k)
        )
    found = [
        (await session.execute(select(DatasheetAbility).where(DatasheetAbility.name == a)))
        .scalar_one_or_none() or DatasheetAbility(name=a)
        for a in abilities
    ]
    with session.no_autoflush:
        model = Model(
            name=name, faction_id=old.faction_id, save=3, toughness=3, oc=1, movement=6,
            wounds=3, leadership=7, base_size=old.base_size,
        )
        model.keywords = [*old.keywords, *rows]
        model.abilities = found
        session.add(model)
    await session.flush()
    unit_model.model_id = model.id
    await session.commit()


async def test_holy_mission_scouts_with_a_dominion_squad(client: AsyncClient, session, tmp_path):
    from app.services.in_game import scouts

    game_id, a, d = await _sororitas_game(
        client, session, tmp_path,
        d_kwargs={"keywords": ("ADEPTA SORORITAS", "DOMINION SQUAD")},
    )
    await _ability(session, d, 'Scouts 6"')
    # The first becomes a Priest (no Scouts of its own).
    await _keyworded_model(
        session, d["models"][0]["unit_model_id"], "Priest", ["CHARACTER"], ["Holy Mission"]
    )
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    assert scouts.distance(unit, game) == 6


async def test_holy_mission_infiltrates_with_novitiates(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _sororitas_game(
        client, session, tmp_path,
        d_kwargs={"keywords": ("ADEPTA SORORITAS", "SISTERS NOVITIATE SQUAD")},
    )
    await _ability(session, d, "Infiltrators")
    # A Priest without it would stop the unit infiltrating...
    await _keyworded_model(session, d["models"][0]["unit_model_id"], "Priest", ["CHARACTER"], [])
    game = await _load_game(session, game_id)
    assert not deployment.is_infiltrator(deployment.find_unit(game, d["unit_id"]))
    # ...one with Holy Mission doesn't.
    await _ability(session, d, "Holy Mission")
    game = await _load_game(session, game_id)
    assert deployment.is_infiltrator(deployment.find_unit(game, d["unit_id"]))


async def test_holy_vanguard_gives_the_leader_scouts_if_embarked(
    client: AsyncClient, session, tmp_path
):
    from app.services.in_game import scouts

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, 'Scouts 6"')
    await _ability(session, d, "Holy Vanguard")
    await _keyworded_model(
        session, d["models"][0]["unit_model_id"], "Palatine", ["CHARACTER"], []
    )
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    # On the battlefield: the leader has no Scouts.
    assert scouts.distance(unit, game) == 0
    # Started the battle embarked: it does.
    from app.engine.state import GameBattleFormation

    game.battle_formations.append(GameBattleFormation(unit_id=unit.id, place="embarked"))
    assert scouts.distance(unit, game) == 6


# --- Mortifiers ---


async def test_anguish_of_the_unredeemed_fights_on(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    from app.services.in_game import duty_in_death

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, "Anguish of the Unredeemed")
    game = await _load_game(session, game_id)
    unit, enemy = (deployment.find_unit(game, u["unit_id"]) for u in (d, a))
    first = d["models"][0]["unit_model_id"]
    # Not outside the Fight phase.
    _rolls(monkeypatch, [6], default=6)
    casualties.mortal_wounds(game, unit, 2, destroyed_by=enemy)
    assert not duty_in_death.lingering(game, first)
    game.phase = "fight"
    # A 2+: the next one lingers, to fight; a 1, it doesn't.
    second, third = (m["unit_model_id"] for m in d["models"][1:])
    _rolls(monkeypatch, [2], default=1)
    casualties.mortal_wounds(game, unit, 2, destroyed_by=enemy)
    assert duty_in_death.lingering(game, second)
    _rolls(monkeypatch, [1], default=1)
    casualties.mortal_wounds(game, unit, 2, destroyed_by=enemy)
    assert not duty_in_death.lingering(game, third)


async def test_anchorite_sarcophagus_sets_move_and_save(client: AsyncClient, session, tmp_path):
    from app.models import Wargear
    from app.services.in_game import movement

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    unit_model = await session.get(UnitModel, d["models"][0]["unit_model_id"])
    await session.refresh(unit_model, ["wargear"])
    unit_model.wargear.append(Wargear(name="Anchorite Sarcophagus", model_id=unit_model.model_id))
    await session.commit()
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    bearer, other = unit.unit_models[0], unit.unit_models[1]
    assert (bearer.movement, bearer.save) == (7, 3)
    # (The test models: M6, Sv3.)
    assert (other.movement, other.save) == (6, 3)
    assert movement.move_characteristic(game, unit, bearer) == 7


async def test_purge_and_cleanse_no_cover_until_the_end_of_the_phase(
    client: AsyncClient, session, tmp_path
):
    from app.combat_rules.effects import IGNORE_COVER
    from app.services.in_game import unit_effects

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _ability(session, d, "Purge and Cleanse")
    await _advance_to(client, game_id, 1, 2, "shooting")
    game = await _load_game(session, game_id)
    a_, d_ = (deployment.find_unit(game, u["unit_id"]) for u in (a, d))
    assert not unit_effects.no_cover(game, a_)
    # (No hits: nothing.)
    assert unit_effects.after_shooting(game, d_, a_, 0) == []
    [effect] = unit_effects.after_shooting(game, d_, a_, 1)
    assert "Benefit of Cover" in unit_effects.describe(effect)
    assert unit_effects.no_cover(game, a_)
    assert any(IGNORE_COVER in r.effects for r in unit_effects.attack_rules(game, d_, a_))
    await _advance_to(client, game_id, 1, 2, "charge")
    game = await _load_game(session, game_id)
    assert not unit_effects.no_cover(game, a_)


def test_the_immolator_datasheet():
    import json

    with open("app/data/factions/adepta_sororitas/datasheets.json") as f:
        sheets = {d["name"]: d for d in json.load(f)["datasheets"]}
    [immolator] = sheets["Immolator"]["models"]
    assert immolator["base_size"] == "155 x 90mm box"
    assert immolator["transport"]["capacity"] == 6
    assert "JUMP PACK" in immolator["transport"]["excluded_keywords"]
    assert "Purge and Cleanse" in immolator["abilities"]
    weapons = {w["name"]: w for w in immolator["weapons"]}
    assert weapons["Immolation flamers"].get("default") and not weapons["Twin multi-melta"].get(
        "default"
    )


def test_the_seraphim_squad_datasheet_and_angelic_ascent():
    import json

    with open("app/data/factions/adepta_sororitas/datasheets.json") as f:
        sheets = {d["name"]: d for d in json.load(f)["datasheets"]}
    superior, seraphim = sheets["Seraphim Squad"]["models"]
    assert (superior["name"], seraphim["name"]) == ("Seraphim Superior", "Seraphim")
    assert seraphim["invulnerable"] == 5 and "JUMP PACK" in seraphim["keywords"]
    defaults = [w["name"] for w in seraphim["weapons"] if w.get("default")]
    assert defaults == ["Bolt pistol", "Bolt pistol", "Close combat weapon"]
    # Angelic Ascent: a 6" Normal move after shooting, then no charge.
    assert ability_seeds.SHOOT_SCOOT["Angelic Ascent"] == {"reach": 6.0, "no_charge": True}
