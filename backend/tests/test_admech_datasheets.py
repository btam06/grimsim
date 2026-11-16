from app.models import DatasheetAbility
from app.seeds import datasheet_abilities as ability_seeds
from app.seeds.factions.adeptus_mechanicus import conditions as admech_conditions
from tests.test_combat import _keyword, _model, _unit, _unit_model, _weapon
from tests.test_sororitas_units import _resolve, _rolls, _target

# The Adeptus Mechanicus datasheet abilities added from the 11th edition
# datasheets that weren't modelled (see
# app/seeds/factions/adeptus_mechanicus/datasheet_abilities.py).


def _gun(**overrides):
    weapon = _weapon(
        **{"attacks": "1", "skill": 4, "strength": 4, "ap": 0, "weapon_type": "ranged",
           "damage": "1", **overrides}
    )
    weapon.id = 1
    return weapon


def _shooter(weapon, abilities=()):
    model = _model(abilities=[DatasheetAbility(name=n, description=None) for n in abilities])
    return _unit([_unit_model(model, [weapon])])


def test_strafing_run_adds_1_to_hit_against_units_that_cant_fly(monkeypatch):
    rules = ability_seeds.RULES["Strafing Run"]
    # A 3 to hit (BS 4+): hits with +1, then wounds and isn't saved (Sv 7+).
    _rolls(monkeypatch, [3, 4, 1])
    assert _resolve(_shooter(_gun()), _target(), attacker_rules=rules).total_damage == 1
    _rolls(monkeypatch, [3, 4, 1])
    flyer = _target(keywords=[_keyword("FLY")])
    assert _resolve(_shooter(_gun()), flyer, attacker_rules=rules).total_damage == 0


def test_broad_spectrum_augurs_sustained_hits_with_eradication_casters(monkeypatch):
    rules = ability_seeds.RULES["Broad-spectrum Targeting Augurs"]
    caster = _gun(name="Eradication caster – focused")
    # A 6 to hit: two hits, both wound, neither saved.
    _rolls(monkeypatch, [6, 4, 4, 1, 1])
    assert _resolve(_shooter(caster), _target(), attacker_rules=rules).total_damage == 2
    # Not against a VEHICLE, nor with another weapon.
    _rolls(monkeypatch, [6, 4, 4, 1, 1])
    tank = _target(keywords=[_keyword("VEHICLE")])
    assert _resolve(_shooter(caster), tank, attacker_rules=rules).total_damage == 1
    _rolls(monkeypatch, [6, 4, 4, 1, 1])
    assert _resolve(_shooter(_gun()), _target(), attacker_rules=rules).total_damage == 1


def test_searing_conflagration_rerolls_against_units_on_objectives(monkeypatch):
    ones, full = ability_seeds.RULES["Searing Conflagration"]
    torch = _gun(name="Phosphor torch", skill=3)
    on = {"defender_positions": {"in_range_of_objective"}}
    # A hit, a Wound roll of 1 re-rolled to a 4, not saved.
    _rolls(monkeypatch, [3, 1, 4, 1])
    assert _resolve(_shooter(torch), _target(), attacker_rules=[ones], **on).total_damage == 1
    # Not off an objective, nor with another weapon.
    _rolls(monkeypatch, [3, 1, 4, 1])
    assert _resolve(_shooter(torch), _target(), attacker_rules=[ones]).total_damage == 0
    _rolls(monkeypatch, [3, 1, 4, 1])
    plain = _shooter(_gun(skill=3))
    assert _resolve(plain, _target(), attacker_rules=[ones], **on).total_damage == 0
    # A failed 2 re-rolled only near a friendly BATTLELINE unit.
    near = {**on, "attacker_positions": {admech_conditions.NEAR_ADMECH_BATTLELINE}}
    _rolls(monkeypatch, [3, 2, 4, 1])
    assert _resolve(_shooter(torch), _target(), attacker_rules=[full], **on).total_damage == 0
    _rolls(monkeypatch, [3, 2, 4, 1])
    assert _resolve(_shooter(torch), _target(), attacker_rules=[full], **near).total_damage == 1


def test_sentinel_directives_overwatch_hits_on_5s(monkeypatch):
    # A 5 to hit Firing Overwatch: a hit only with Sentinel Directives.
    _rolls(monkeypatch, [5, 4, 1])
    unit = _shooter(_gun(), ["Sentinel Directives"])
    assert _resolve(unit, _target(), snap_shots=True).total_damage == 1
    _rolls(monkeypatch, [5, 4, 1])
    assert _resolve(_shooter(_gun()), _target(), snap_shots=True).total_damage == 0


def test_the_new_abilities_are_wired_up():
    assert "Aerial Deployment" in ability_seeds.FIRST_ROUND_INGRESS
    assert ability_seeds.REINFORCEMENT_DENIAL["Cogitative Instincts"] == 12.0
    assert ability_seeds.UNIT_REQUIRES["Network Override"] == "TECH-PRIEST"
    assert "advanced" in ability_seeds.ACTION_AFTER["Network Override"]
    assert "Network Override" in ability_seeds.ACTION_SHOOTS
    assert ability_seeds.QUARRIES["Focused Hunters"]["again_with"] is None
    assert ability_seeds.END_OF_PHASE_MORTALS["Bomb Rack"]["dice"] == 6


# --- in a game ---


async def _with(session, unit, name, keywords=()):
    # The unit's (first) model gets the ability - and keywords.
    from sqlalchemy import select

    from app.models import Keyword
    from tests.test_space_marine_units import _model_of

    model = await _model_of(session, unit)
    found = (
        await session.execute(select(DatasheetAbility).where(DatasheetAbility.name == name))
    ).scalar_one_or_none() or DatasheetAbility(name=name, description=name)
    if found not in model.abilities:
        model.abilities.append(found)
    if keywords:
        from sqlalchemy.orm import selectinload

        from app.models import Model

        model = (
            await session.execute(
                select(Model).options(selectinload(Model.keywords)).where(Model.id == model.id)
            )
        ).scalar_one()
        for k in keywords:
            found = await session.execute(select(Keyword).where(Keyword.name == k))
            model.keywords.append(found.scalar_one_or_none() or Keyword(name=k))
    await session.commit()


async def test_bomb_rack_at_the_end_of_the_opponents_fight_phase(
    client, session, tmp_path, monkeypatch
):
    from app.routers.games import _load_game
    from app.services.in_game import casualties, phase_end
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle

    units = {1: [("A", 1, {})], 2: [("D", 5, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, a, "Bomb Rack")
    from tests.test_shooting import _place

    # D within 24" of (and visible to) A, at (20, 38).
    await _place(session, d, [(20 + 2 * n, 20) for n in range(5)])
    game_ = await _load_game(session, game["id"])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 4)

    def lost():
        damage = casualties.damage(game_)
        return sum(
            damage[m["unit_model_id"]].wounds_lost
            for m in d["models"]
            if m["unit_model_id"] in damage
        )

    # Its own Fight phase (A is seat 1's): nothing.
    game_.phase, game_.turn_seat = "fight", 1
    phase_end.mortals(game_)
    assert lost() == 0
    # Its opponent's: six 4s, 6 mortal wounds.
    game_.phase, game_.turn_seat = "fight", 2
    phase_end.mortals(game_)
    assert lost() == 6
    # Once a phase.
    phase_end.mortals(game_)
    assert lost() == 6


async def test_cogitative_instincts_keeps_reinforcements_12_away(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import deployment, reinforcements
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle

    game, deployment_ = await _battle(client, session, tmp_path)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, a, "Cogitative Instincts")
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, d["unit_id"])
    ids = [m["unit_model_id"] for m in d["models"]]
    # A is at (20, 38): 10" away - too close; 14" is fine (and 8" from others).
    near = {i: (20 + 2 * n, 28, 0) for n, i in enumerate(ids)}
    far = {i: (40 + 2 * n, 24, 0) for n, i in enumerate(ids)}
    problems = reinforcements.check_arrival(game_, unit, near).problems
    assert any("stops reinforcements" in p for p in problems)
    problems = reinforcements.check_arrival(game_, unit, far).problems
    assert not any("stops reinforcements" in p for p in problems)


async def test_aerial_deployment_is_an_ingress_move(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import deployment, reinforcements
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle

    game, deployment_ = await _battle(client, session, tmp_path)
    a = _unit_named(deployment_, "A")
    game_ = await _load_game(session, game["id"])
    assert not reinforcements.ingress_move(deployment.find_unit(game_, a["unit_id"]))
    await _with(session, a, "Aerial Deployment")
    game_ = await _load_game(session, game["id"])
    assert reinforcements.ingress_move(deployment.find_unit(game_, a["unit_id"]))


async def test_network_override_needs_a_tech_priest(client, session, tmp_path):
    from app.engine.state import GameAction
    from app.routers.games import _load_game
    from app.services.in_game import actions, deployment
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle

    game, deployment_ = await _battle(client, session, tmp_path)
    d = _unit_named(deployment_, "D")
    await _with(session, d, "Network Override")

    async def blocked():
        game_ = await _load_game(session, game["id"])
        unit = deployment.find_unit(game_, d["unit_id"])
        game_.actions.append(
            GameAction(
                unit_id=unit.id, battle_round=game_.battle_round, turn_seat=game_.turn_seat,
                action="Test", status="started",
            )
        )
        return actions.blocks(game_, unit, "shoot"), actions._act_after(unit, game_)

    reason, after = await blocked()
    assert reason is not None and after == set()
    await _with(session, d, "Network Override", keywords=("TECH-PRIEST",))
    reason, after = await blocked()
    assert reason is None and after == {"advanced"}


async def test_focused_hunters_selects_a_quarry(client, session, tmp_path):
    from app.routers.games import _load_game
    from app.services.in_game import deployment, quarry
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle

    game, deployment_ = await _battle(client, session, tmp_path)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, d, "Focused Hunters")
    game_id = game["id"]
    [unit] = (await client.get(f"/games/{game_id}/quarry")).json()["units"]
    assert unit["ability"] == "Focused Hunters" and unit["quarry"] is None
    assert [t["unit_id"] for t in unit["targets"]] == [a["unit_id"]]
    response = await client.post(
        f"/games/{game_id}/quarry", json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"]}
    )
    assert response.status_code == 200, response.text
    [unit] = response.json()["units"]
    assert unit["quarry"]["unit_id"] == a["unit_id"] and unit["targets"] == []
    game_ = await _load_game(session, game_id)
    hunters, prey = (deployment.find_unit(game_, u["unit_id"]) for u in (d, a))
    [rule] = quarry.rules(game_, hunters, prey)
    assert rule.effects == ("reroll_failed_hits",)
    assert quarry.rules(game_, prey, hunters) == []


async def test_line_breakers_rolls_per_engaged_model(client, session, tmp_path, monkeypatch):
    from app.routers.games import _load_game
    from app.services.in_game import casualties, charging, deployment
    from tests.test_deployment import _unit_named
    from tests.test_movement import _battle
    from tests.test_shooting import _place

    units = {1: [("A", 1, {})], 2: [("D", 2, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, d, "Line-breakers")
    # D's first model (with it) engaged with A.
    await _place(session, a, [(20, 20)])
    await _place(session, d, [(20, 21.5), (30, 30)])
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, d["unit_id"])
    # A 2: no wound - unless +2, for starting near BATTLELINE.
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 2)
    charging._charge_model_mortals(game_, unit, set())
    assert a["models"][0]["unit_model_id"] not in casualties.damage(game_)
    charging._charge_model_mortals(game_, unit, {"Line-breakers"})
    assert casualties.damage(game_)[a["models"][0]["unit_model_id"]].wounds_lost == 1
