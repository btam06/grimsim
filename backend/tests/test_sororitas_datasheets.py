from app.models import Effect, WeaponAbility
from app.seeds import datasheet_abilities as ability_seeds
from app.seeds.factions.adepta_sororitas import conditions as sororitas_conditions
from tests.test_combat import _keyword, _model, _unit, _unit_model, _weapon
from tests.test_sororitas_units import _resolve, _rolls, _target

# The Adepta Sororitas datasheet abilities added from the 11th edition
# datasheets (see app/seeds/factions/adepta_sororitas/datasheet_abilities.py).


def _melee(**overrides):
    weapon = _weapon(**{"attacks": "1", "skill": 3, "strength": 4, "ap": 0, "weapon_type": "melee",
                        "range": None, "damage": "1", **overrides})
    weapon.id = 1
    return weapon


def _repentia(superior=True):
    models = [_unit_model(_model(name="Sister Repentia"), [_melee(name="Penitent eviscerator")])]
    if superior:
        models.append(_unit_model(_model(name="Repentia Superior"), []))
    return _unit(models)


def test_overseer_of_redemption_rerolls_while_a_superior_is_in_the_unit(monkeypatch):
    rules = ability_seeds.RULES["Overseer of Redemption"]
    # A failed Hit roll re-rolled to a 4, a failed Wound roll re-rolled to a 4.
    _rolls(monkeypatch, [1, 4, 1, 4])
    result = _resolve(_repentia(), _target(save=7), in_engagement_range=True, attacker_rules=rules)
    assert result.total_damage == 1
    # Without the Superior: no re-rolls.
    _rolls(monkeypatch, [1, 4, 1, 4])
    result = _resolve(
        _repentia(superior=False), _target(save=7), in_engagement_range=True, attacker_rules=rules
    )
    assert result.total_damage == 0


def test_lifewards_is_celestines_while_a_geminae_is_with_her():
    check = sororitas_conditions.celestine_with_geminae
    unit = ["Celestine", "Geminae Superia"]
    assert check({"target_model_name": "Celestine", "defender_unit_model_names": unit})
    assert not check({"target_model_name": "Geminae Superia", "defender_unit_model_names": unit})
    assert not check({"target_model_name": "Celestine", "defender_unit_model_names": ["Celestine"]})


def _led_target(save=7):
    return _unit(
        [
            _unit_model(_model(keywords=[_keyword("CHARACTER")], save=save, wounds=3), []),
            _unit_model(_model(save=save, wounds=3), []),
        ]
    )


def test_stanchion_of_holy_martyrs_gives_a_2_up_save_while_leading(monkeypatch):
    rules = ability_seeds.RULES["Stanchion of Holy Martyrs"]
    gun = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged", damage="1")
    gun.id = 1
    attacker = _unit([_unit_model(_model(), [gun])])
    # Hit, wound, then a save of 2: saved with Sv 2+.
    _rolls(monkeypatch, [3, 4, 2])
    assert _resolve(attacker, _led_target(), defender_rules=rules).total_damage == 0
    _rolls(monkeypatch, [3, 4, 2])
    assert _resolve(attacker, _led_target()).total_damage == 1


def _ability(name, effects=()):
    ability = WeaponAbility(name=name, description=None)
    ability.conditions = []
    ability.effects = [Effect(keyword=e, name=e, description=None) for e in effects]
    return ability


def test_rituale_nullificatus_feel_no_pain_against_psychic_attacks(monkeypatch):
    rules = ability_seeds.RULES["Rituale Nullificatus"]
    smite = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged", damage="1")
    smite.id = 1
    smite.abilities = [_ability("Psychic")]
    attacker = _unit([_unit_model(_model(), [smite])])
    # Hit, wound, a failed save (Sv 7+), then a 4: Feel No Pain against it.
    _rolls(monkeypatch, [3, 4, 1, 4])
    assert _resolve(attacker, _target(save=7), defender_rules=rules).total_damage == 0
    # Not against an attack that isn't psychic.
    plain = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged", damage="1")
    plain.id = 1
    _rolls(monkeypatch, [3, 4, 1, 4])
    result = _resolve(_unit([_unit_model(_model(), [plain])]), _target(save=7), defender_rules=rules)
    assert result.total_damage == 1


def test_auto_tapestry_devastating_wounds_while_aestred_leads(monkeypatch):
    rules = ability_seeds.RULES["Auto-Tapestry of the Emperor's Judgement"]
    blade = _melee(name="Blade of Vigil")
    attacker = _unit(
        [
            _unit_model(_model(name="Aestred Thurga", keywords=[_keyword("CHARACTER")]), [blade]),
            _unit_model(_model(name="Battle Sister"), []),
        ]
    )
    # A hit, then a 6 to wound: no save (Sv 2+ would have saved a 6).
    _rolls(monkeypatch, [3, 6, 6])
    result = _resolve(attacker, _target(save=2), in_engagement_range=True, attacker_rules=rules)
    assert result.total_damage == 1
    _rolls(monkeypatch, [3, 6, 6])
    result = _resolve(attacker, _target(save=2), in_engagement_range=True)
    assert result.total_damage == 0


def test_embodied_prophecy_options_are_one_or_the_other():
    options = {
        name: config
        for name, config in ability_seeds.FIGHT_ABILITIES.items()
        if config.ability == "Embodied Prophecy"
    }
    assert set(options) == {"Embodied Prophecy: Sustained Hits", "Embodied Prophecy: Lethal Hits"}
    assert {c.group for c in options.values()} == {"Embodied Prophecy"}
    assert not any(c.once_per_battle for c in options.values())


def test_the_new_abilities_are_wired_up():
    assert ability_seeds.ELIGIBLE_AFTER["Endless Suffering"] == {"advanced": ("charge",)}
    assert "Sacred Banner" in ability_seeds.CHARGE_REROLLS & ability_seeds.ADVANCE_REROLLS
    assert ability_seeds.COMMAND_HEALS["Self Repair"] == 1
    assert ability_seeds.STRATAGEM_COSTS["Mysterious Saviours"]["Heroic Intervention"] == (0, True)
    assert ability_seeds.BATTLE_SHOCK_AURAS["Executioner of Heretics (Aura)"]["modifier"] == -1
    grace = ability_seeds.PHASE_START_ABILITIES["The Emperor's Grace"]
    assert grace.either_player and grace.model_only and grace.once_per_battle
    assert ability_seeds.RALLIES["Laud Hailer"]["range"] == 12.0


# --- returning models: Healing Tears (and Sacred Healing's table) ---


async def _celestine(session, d):
    # D's first model becomes Celestine (with Healing Tears), the other two
    # Geminae Superia.
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import DatasheetAbility, Model, UnitModel

    ability = (
        await session.execute(select(DatasheetAbility).where(DatasheetAbility.name == "Healing Tears"))
    ).scalar_one_or_none() or DatasheetAbility(name="Healing Tears")
    for i, m in enumerate(d["models"]):
        unit_model = await session.get(UnitModel, m["unit_model_id"])
        old = (
            await session.execute(
                select(Model)
                .options(selectinload(Model.keywords), selectinload(Model.base_size))
                .where(Model.id == unit_model.model_id)
            )
        ).scalar_one()
        model = Model(
            name="Celestine" if i == 0 else "Geminae Superia", faction_id=old.faction_id,
            save=2, toughness=3, oc=1, movement=12, wounds=2, leadership=7,
            base_size=old.base_size,
        )
        model.keywords = list(old.keywords)
        model.abilities = [ability]
        session.add(model)
        await session.flush()
        unit_model.model_id = model.id
    await session.commit()


async def test_healing_tears_returns_one_geminae_in_the_command_phase(
    client, session, tmp_path
):
    from app.routers.games import _load_game
    from app.seeds.factions.adepta_sororitas import unit_abilities
    from app.services.in_game import deployment
    from tests import live_games
    from tests.test_acts_of_faith import _sororitas_game
    from tests.test_reinforcements import _advance_to

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _celestine(session, d)
    for m in d["models"][1:]:
        live_games.damage(game_id, m["unit_model_id"], wounds_lost=2, destroyed=True)
        live_games.remove_position(m["unit_model_id"], game_id)
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    assert "Command phase" in unit_abilities.healing_reason(game, unit, "Healing Tears")
    await _advance_to(client, game_id, 2, 2, "command")
    state = next(p for p in (await client.get(f"/games/{game_id}/miracle-dice")).json())
    [offer] = [h for h in state["sacred_healing"] if h["ability"] == "Healing Tears"]
    assert (offer["destroyed"], offer["count"], offer["discard_count"]) == (2, "1", None)
    # No Miracle dice to discard for more.
    response = await client.post(
        f"/games/{game_id}/sacred-healing",
        json={"unit_id": d["unit_id"], "ability": "Healing Tears", "discard": 3},
    )
    assert response.status_code == 400
    response = await client.post(
        f"/games/{game_id}/sacred-healing",
        json={"unit_id": d["unit_id"], "ability": "Healing Tears"},
    )
    assert response.status_code == 200, response.text
    reanimation = (await client.get(f"/games/{game_id}/reanimation")).json()
    [returned] = reanimation["units"]
    assert len(returned["to_place"]) == 1
    # Once a phase.
    response = await client.post(
        f"/games/{game_id}/sacred-healing",
        json={"unit_id": d["unit_id"], "ability": "Healing Tears"},
    )
    assert response.status_code == 400


def test_the_salvationist_medikit_returns_up_to_d3_non_characters():
    from app.seeds.factions.adepta_sororitas import unit_abilities

    medikit = unit_abilities.RETURNS["Salvationist Medikit"]
    assert (medikit.count, medikit.discard_count, medikit.no_characters) == ("D3", None, True)
    assert medikit.wargear == "Salvationist medikit"


# --- Holy Judgement: a Battle-shock test at the start of the Shooting phase ---


async def test_holy_judgement_battle_shocks_and_wounds_a_chaos_unit(
    client, session, tmp_path, monkeypatch
):
    from app.models import DatasheetAbility
    from app.routers.games import _load_game
    from app.services.in_game import casualties
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle
    from tests.test_shooting import _place
    from tests.test_space_marine_units import _model_of

    units = {1: [("V", 1, {"keywords": ("CHAOS",)}), ("A", 1, {})], 2: [("T", 1, {})]}
    spots = {"V": (20, 38), "A": (40, 38), "T": (20, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    t, v, a = (_unit_named(deployment_, n) for n in "TVA")
    model = await _model_of(session, t)
    model.abilities.append(DatasheetAbility(name="Holy Judgement", description="Judgement"))
    await session.commit()
    # V within 12" of (and visible to) Ephrael; A isn't.
    await _place(session, v, [(20, 14)])
    await client.post(f"/games/{game_id}/advance")
    [ability] = (await client.get(f"/games/{game_id}/shooting-start")).json()
    assert [x["unit_id"] for x in ability["targets"]] == [v["unit_id"]]
    response = await client.post(
        f"/games/{game_id}/shooting-start",
        json={"unit_id": t["unit_id"], "ability": "Holy Judgement", "target_unit_id": v["unit_id"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["wounds"] == 0
    # A test to take, -2 for a CHAOS unit.
    [test] = (await client.get(f"/games/{game_id}/battle-shock")).json()["pending"]
    assert (test["unit_id"], test["reason"], test["modifier"]) == (
        v["unit_id"], "Holy Judgement", -2
    )
    # Failed (1 + 1 - 2): 3 mortal wounds.
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 1)
    response = await client.post(f"/games/{game_id}/battle-shock/{test['id']}/take", json={})
    assert response.status_code == 200, response.text
    game_ = await _load_game(session, game_id)
    lost = casualties.damage(game_)[v["models"][0]["unit_model_id"]]
    assert lost.destroyed or lost.wounds_lost == 3


# --- Miracle dice: Solemn Procession, Stirring Rhetoric, Recount the Deeds ---


async def _leading(session, d, name, ability):
    # D's first model becomes a CHARACTER `name` with `ability`, in a leader
    # unit attached to the other two (as test_sororitas_units' Hospitaller).
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import DatasheetAbility, Keyword, Model, Unit, UnitModel

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
    found = (
        await session.execute(select(DatasheetAbility).where(DatasheetAbility.name == ability))
    ).scalar_one_or_none() or DatasheetAbility(name=ability)
    leader_model = Model(
        name=name, faction_id=old.faction_id, save=3, toughness=3, oc=1, movement=6, wounds=3,
        leadership=7, base_size=old.base_size,
    )
    leader_model.keywords = [*old.keywords, character]
    leader_model.abilities = [found]
    session.add(leader_model)
    await session.flush()
    unit = await session.get(Unit, unit_model.unit_id)
    leader = Unit(
        faction_unit_id=unit.faction_unit_id, points=0, list_id=unit.list_id,
        attached_to_id=unit.id,
    )
    session.add(leader)
    await session.flush()
    unit_model.model_id = leader_model.id
    unit_model.unit_id = leader.id
    await session.commit()


async def test_solemn_procession_makes_the_start_of_turn_dice_a_6(
    client, session, tmp_path, monkeypatch
):
    from app.routers.games import _load_game
    from app.seeds.factions.adepta_sororitas import acts_of_faith
    from tests.test_acts_of_faith import _sororitas_game

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _leading(session, d, "Triumph of Saint Katherine", "Solemn Procession")
    game = await _load_game(session, game_id)
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 2)
    acts_of_faith.start_of_turn(game)
    sisters = next(p for p in game.players if p.seat == 2)
    assert sisters.miracle_dice == [6]


async def test_stirring_rhetoric_makes_an_acts_dice_a_6_while_leading(
    client, session, tmp_path
):
    from app.routers.games import _load_game
    from app.seeds.factions.adepta_sororitas import acts_of_faith
    from app.services.in_game import deployment
    from tests.test_acts_of_faith import _sororitas_game

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _leading(session, d, "Dialogus", "Stirring Rhetoric")
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    sisters = next(p for p in game.players if p.seat == 2)
    sisters.miracle_dice[:] = [2]
    assert acts_of_faith.perform(game, unit, acts_of_faith.CHARGE, 2) == 6
    assert sisters.miracle_dice == []


async def test_recount_the_deeds_gains_a_dice_when_its_unit_destroys_one(
    client, session, tmp_path, monkeypatch
):
    from app.routers.games import _load_game
    from app.seeds.factions.adepta_sororitas import acts_of_faith
    from app.services.in_game import deployment
    from tests.test_acts_of_faith import _sororitas_game

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _leading(session, d, "Agathae Dolan", "Recount the Deeds of the Saints")
    game = await _load_game(session, game_id)
    sisters_unit = deployment.find_unit(game, d["unit_id"])
    enemy = deployment.find_unit(game, a["unit_id"])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 4)
    acts_of_faith.enemy_unit_destroyed(game, enemy, sisters_unit)
    sisters = next(p for p in game.players if p.seat == 2)
    assert sisters.miracle_dice == [4]
    # Not for a unit of its own army.
    acts_of_faith.enemy_unit_destroyed(game, sisters_unit, sisters_unit)
    assert sisters.miracle_dice == [4]


async def test_miraculous_intervention_sets_celestine_up_again_once(
    client, session, tmp_path, monkeypatch
):
    from app.routers.games import _load_game
    from app.seeds.factions.adepta_sororitas import unit_abilities
    from app.services.in_game import casualties, deployment
    from tests.test_acts_of_faith import _sororitas_game

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _celestine(session, d)
    from sqlalchemy import select

    from app.models import DatasheetAbility, Model, UnitModel

    celestine = await session.get(UnitModel, d["models"][0]["unit_model_id"])
    model = await session.get(Model, celestine.model_id)
    miraculous = DatasheetAbility(name="Miraculous Intervention")
    await session.refresh(model, ["abilities"])
    model.abilities.append(miraculous)
    await session.commit()
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    her = next(m for m in unit.unit_models if m.model.name == "Celestine")
    # She's destroyed (2 W); on a 2, she's back with her full wounds.
    casualties._lose(game, her, 2)
    assert casualties.damage(game)[her.id].destroyed
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 2)
    assert unit_abilities.miraculous_end_of_phase(game) == [(her.id, 2, True)]
    record = casualties.damage(game)[her.id]
    assert (record.destroyed, record.wounds_lost) == (False, 0)
    assert her.id in deployment.positions(game)
    # Only the first time.
    casualties._lose(game, her, 2)
    assert unit_abilities.miraculous_end_of_phase(game) == []
    assert casualties.damage(game)[her.id].destroyed


async def test_virtue_of_intolerance_quarry(client, session, tmp_path):
    from sqlalchemy import select

    from app.models import DatasheetAbility, Model, UnitModel
    from app.routers.games import _load_game
    from app.seeds.factions.adepta_sororitas import unit_abilities
    from app.services.in_game import deployment
    from tests.test_acts_of_faith import _sororitas_game

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    for m in d["models"]:
        unit_model = await session.get(UnitModel, m["unit_model_id"])
        model = await session.get(Model, unit_model.model_id)
        await session.refresh(model, ["abilities"])
        found = (
            await session.execute(
                select(DatasheetAbility).where(DatasheetAbility.name == "Virtue of Intolerance")
            )
        ).scalar_one_or_none() or DatasheetAbility(name="Virtue of Intolerance")
        if found not in model.abilities:
            model.abilities.append(found)
    await session.commit()
    [unit] = (await client.get(f"/games/{game_id}/quarry")).json()["units"]
    assert unit["quarry"] is None and [t["unit_id"] for t in unit["targets"]] == [a["unit_id"]]
    response = await client.post(
        f"/games/{game_id}/quarry", json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"]}
    )
    assert response.status_code == 200, response.text
    [unit] = response.json()["units"]
    assert unit["quarry"]["unit_id"] == a["unit_id"] and unit["targets"] == []
    # Its attacks against its quarry: [PRECISION] and re-roll the Hit roll.
    game = await _load_game(session, game_id)
    sisters = deployment.find_unit(game, d["unit_id"])
    enemy = deployment.find_unit(game, a["unit_id"])
    from app.services.in_game import quarry

    [rule] = quarry.rules(game, sisters, enemy)
    assert set(rule.effects) == {"precision", "reroll_failed_hits"}
    # Not another while it lives.
    response = await client.post(
        f"/games/{game_id}/quarry", json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"]}
    )
    assert response.status_code == 400


async def test_fiery_conviction_cp_for_a_dice_or_a_leadership_test(
    client, session, tmp_path, monkeypatch
):
    from tests.test_acts_of_faith import _pool, _sororitas_game
    from tests.test_reinforcements import _advance_to

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _leading(session, d, "Junith Eruita", "Fiery Conviction")
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[2])
    state = next(p for p in (await client.get(f"/games/{game_id}/miracle-dice")).json())
    assert list(state["fiery_conviction"]) == [str(d["unit_id"])]
    before = (await client.get(f"/games/{game_id}")).json()
    cp = next(p["cp"] for p in before["players"] if p["seat"] == 2)
    response = await client.post(
        f"/games/{game_id}/fiery-conviction", json={"unit_id": d["unit_id"], "discard": 2}
    )
    assert response.status_code == 200, response.text
    assert _pool(game_id) == []
    after = (await client.get(f"/games/{game_id}")).json()
    assert next(p["cp"] for p in after["players"] if p["seat"] == 2) == cp + 1
    # Once a phase.
    response = await client.post(f"/games/{game_id}/fiery-conviction", json={"unit_id": d["unit_id"]})
    assert response.status_code == 400


async def test_relics_of_the_matriarchs_auras_chosen_each_round(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.seeds.factions.adepta_sororitas import acts_of_faith, unit_abilities
    from app.services.in_game import auras, battle_round, deployment, movement
    from tests.test_acts_of_faith import _sororitas_game

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _leading(session, d, "Triumph of Saint Katherine", "Relics of the Matriarchs")
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    # Only at the start of the battle round.
    assert "start of the battle round" in unit_abilities.relics_reason(game, unit)
    game.phase = battle_round.START_OF_ROUND
    assert unit_abilities.relics_allowed(game, unit) == 2
    try:
        unit_abilities.choose_relics(game, unit, unit_abilities.relic_options()[:3])
        raise AssertionError("three relics chosen")
    except Exception as err:  # (an HTTPException)
        assert "up to 2" in str(getattr(err, "detail", err))
    unit_abilities.choose_relics(
        game, unit, [unit_abilities.FIERY_HEART, unit_abilities.EBON_CHALICE]
    )
    # Its own unit is within 6" of it: the auras reach it.
    sister = deployment.models_on_battlefield(game, unit)[-1]
    assert movement.move_characteristic(game, unit, sister) == sister.model.movement + 2
    assert movement.roll_bonus(game, unit, "charge") >= 1
    player = deployment.owner(game, unit)
    assert acts_of_faith.acts_per_phase(player, game, unit) == 2
    # Chosen again: replaced.
    unit_abilities.choose_relics(game, unit, ["Icon of the Valorous Heart (Aura)"])
    assert unit_abilities.chosen_relics(game, unit) == ["Icon of the Valorous Heart (Aura)"]
    assert "Icon of the Valorous Heart (Aura)" in auras.aura_options(game, unit)
    assert acts_of_faith.acts_per_phase(player, game, unit) == 1


def test_the_triumphs_damaged_profile_halves_its_attacks(monkeypatch):
    from tests.test_sororitas_units import _resolve

    rules = ability_seeds.RULES["Damaged: 1-6 Wounds Remaining"]
    relic = _melee(name="Relic weapons", attacks="6")
    triumph = _model(
        name="Triumph of Saint Katherine", abilities=[_ability_named("Damaged: 1-6 Wounds Remaining")]
    )
    attacker = _unit([_unit_model(triumph, [relic])])
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: 6)
    whole = _resolve(attacker, _target(save=7), in_engagement_range=True)
    damaged = _resolve(
        attacker, _target(save=7), in_engagement_range=True, attacker_rules=rules,
        attacker_damaged=True,
    )
    assert (whole.total_damage, damaged.total_damage) == (6, 3)


def test_melee_sustained_and_lethal_hits_trigger_on_critical_hits(monkeypatch):
    # (MELEE_WEAPON holds at every step - MELEE_ATTACK only at the pre-hit
    # check, so it could never meet CRITICAL_HIT.)
    priest = _model(name="Ministorum Priest", keywords=[_keyword("MINISTORUM PRIEST")])
    unit = _unit([_unit_model(priest, [_melee()])])
    sermon = ability_seeds.RULES["Ministorum Sermon"]
    # A 6 to hit: two hits, both wound, neither saved.
    _rolls(monkeypatch, [6, 4, 4])
    result = _resolve(unit, _target(), in_engagement_range=True, attacker_rules=sermon)
    assert result.total_damage == 2
    lethal = ability_seeds.FIGHT_ABILITIES["Embodied Prophecy: Lethal Hits"].rules
    # A 6 to hit, then a failed Wound roll: wounds anyway.
    _rolls(monkeypatch, [6, 1])
    result = _resolve(
        _unit([_unit_model(_model(), [_melee()])]), _target(), in_engagement_range=True,
        attacker_rules=list(lethal),
    )
    assert result.total_damage == 1


def test_damaged_conditions_check_the_models_own_profile():
    from app.combat_rules import CONDITIONS
    from app.combat_rules.conditions import DAMAGED_4, DAMAGED_6
    from app.services.combat import _damaged_bracket

    six, four = CONDITIONS[DAMAGED_6], CONDITIONS[DAMAGED_4]
    assert six({"attacker_damaged_bracket": 6}) and not four({"attacker_damaged_bracket": 6})
    assert not six({})
    damaged = _unit_model(_model(wounds=12, abilities=[_ability_named("Damaged: 1-6 Wounds Remaining")]), [])
    damaged.id = 1
    plain = _unit_model(_model(wounds=5), [])
    plain.id = 2
    # In a game: by its wounds left - and only a model with the profile.
    assert _damaged_bracket(damaged, {1: 6}, False) == 6
    assert _damaged_bracket(damaged, {1: 7}, False) is None
    assert _damaged_bracket(plain, {2: 3}, True) is None
    # In the calculator: the "Attacking model is Damaged" tick.
    assert _damaged_bracket(damaged, None, True) == 6


def _ability_named(name):
    from app.models import DatasheetAbility

    return DatasheetAbility(name=name, description=None)
