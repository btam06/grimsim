from types import SimpleNamespace

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.combat_rules.positions import POSITIONS
from app.models import (
    ArmyList,
    Detachment,
    DetachmentRule,
    Enhancement,
    Faction,
    Keyword,
    Model,
    Stratagem,
    StratagemTiming,
    Unit,
    UnitModel,
)
from app.routers.games import _attacker_positions, _load_game
from app.seeds import stratagems as stratagem_seeds
from app.seeds import weapon_abilities as weapon_ability_seeds
from app.seeds.factions.space_marines import conditions as sm_conditions
from app.seeds.factions.space_marines import datasheet_abilities as sm_datasheets
from app.services.in_game import casualties, charging, deployment, duty_in_death
from app.services.in_game import reinforcements
from app.services.list_building import enhancements as enhancement_rules
from tests.test_combat_doctrines import ASSAULT, _choose, _command, _doctrines_game
from tests.test_deployment import _declare, _deploy, _deployment, _game, _row, _set, _unit_named
from tests.test_reinforcements import EDGE, _advance_to, _at, _bring_in, _rapid_ingress

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Seat 1's
# faction is the Space Marines, and its list has taken the detachment each
# test gives it.


async def _model(session, unit) -> Model:
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    return (
        await session.execute(
            select(Model)
            .options(selectinload(Model.keywords), selectinload(Model.abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()


async def _seat_1_list(session, game_id) -> ArmyList:
    game = await _load_game(session, game_id)
    list_id = next(p for p in game.players if p.seat == 1).army_list.id
    return (
        await session.execute(
            select(ArmyList).options(selectinload(ArmyList.detachments)).where(ArmyList.id == list_id)
        )
    ).scalar_one()


async def _take(session, game_id, name, faction_id) -> Detachment:
    # Seat 1's list takes a detachment of that name.
    detachment = Detachment(name=name, faction_id=faction_id, dp=1)
    session.add(detachment)
    army_list = await _seat_1_list(session, game_id)
    army_list.detachments.append(detachment)
    await session.commit()
    return detachment


async def _space_marines(session, unit) -> int:
    # Renames the unit's faction the Space Marines; its id.
    model = await _model(session, unit)
    faction = await session.get(Faction, model.faction_id)
    faction.name = "Space Marines"
    await session.commit()
    return faction.id


async def _keyword(session, name) -> Keyword:
    found = (await session.execute(select(Keyword).where(Keyword.name == name))).scalar_one_or_none()
    return found or Keyword(name=name)


def _stratagem(name, detachment, phase, turn, game_action=None, keywords=()) -> Stratagem:
    stratagem = Stratagem(name=name, cp=1, is_core=False, detachments=[detachment])
    stratagem.timings = [StratagemTiming(phase=phase, turn=turn)]
    stratagem.keywords = list(keywords)
    stratagem.game_action = game_action
    return stratagem


# --- combat ---


def test_hellfire_rounds_anti_non_vehicle_4():
    check = sm_conditions.hellfire_anti_non_vehicle_4
    wound = {"step": "wound", "is_ranged": True, "roll": 4, "defender_keywords": {"INFANTRY"}}
    assert check(wound)
    assert not check({**wound, "roll": 3})
    assert not check({**wound, "defender_keywords": {"VEHICLE"}})
    assert not check({**wound, "is_ranged": False})
    # Excluding [DEVASTATING WOUNDS] attacks.
    assert not check({**wound, "weapon_ability_names": {"Devastating Wounds"}})
    assert check({**wound, "weapon_ability_names": {"Lethal Hits"}})


def test_mission_tactics_follow_the_doctrine():
    crit = {"step": "hit", "roll": 6}
    devastator = {"attacker_options": {"Devastator Doctrine"}}
    tactical = {"attacker_options": {"Tactical Doctrine"}}
    assault = {"attacker_options": {"Assault Doctrine"}}
    assert sm_conditions.devastator_doctrine_critical_hit({**crit, **devastator})
    assert not sm_conditions.devastator_doctrine_critical_hit({**crit, **tactical})
    assert not sm_conditions.devastator_doctrine_critical_hit({**devastator, "step": "hit"})
    assert sm_conditions.tactical_doctrine_critical_hit({**crit, **tactical})
    assert not sm_conditions.tactical_doctrine_critical_hit({**crit, **assault})
    # Purgatus Tactics: the target within 9" too (Positioning).
    near = {"attacker_positions": {sm_conditions.TARGET_WITHIN_9}}
    assert sm_conditions.assault_doctrine_target_within_9({**assault, **near})
    assert not sm_conditions.assault_doctrine_target_within_9(assault)
    assert not sm_conditions.assault_doctrine_target_within_9({**tactical, **near})
    assert sm_conditions.TARGET_WITHIN_9 in POSITIONS
    for name in ("Furor Tactics", "Malleus Tactics", "Purgatus Tactics"):
        assert name in {entry[0] for entry in sm_datasheets.ENTRIES}
        assert sm_datasheets.RULES[name]


def test_gene_wrought_might_improves_ap_with_the_assault_doctrine():
    [rule] = stratagem_seeds.rules("Gene-Wrought Might")
    assert rule.effects == ("improve_ap",)
    assert sm_conditions.assault_doctrine_active({"attacker_options": {"Assault Doctrine"}})
    assert not sm_conditions.assault_doctrine_active({"attacker_options": set()})


def test_sustained_1_against_non_monster_vehicle():
    names = {entry[0]: entry for entry in weapon_ability_seeds.ENTRIES}
    _, _, conditions, effects = names["Sustained 1: non-Monster/Vehicle"]
    assert conditions == ["critical_hit_not_monster_or_vehicle"]
    assert effects == ["add_extra_hit"]


async def test_purgatus_tactics_target_within_9_in_a_game(
    client: AsyncClient, session, tmp_path
):
    units = {1: [("A", 1, {"weapon_range": 24})], 2: [("D", 1, {"weapon_range": 24})]}
    game = await _game(client, session, tmp_path, units=units)
    deployment_ = await _deployment(client, game["id"])
    a, d = (_unit_named(deployment_, n) for n in "AD")
    for unit, (x, y) in ((a, (20, 34)), (d, (20, 10))):
        response = await _deploy(client, game["id"], unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    game_ = await _load_game(session, game["id"])
    a_, d_ = (deployment.find_unit(game_, u["unit_id"]) for u in (a, d))
    assert sm_conditions.TARGET_WITHIN_9 not in _attacker_positions(game_, a_, d_)
    for m in d_.unit_models:
        deployment.positions(game_)[m.id].y = 27
    assert sm_conditions.TARGET_WITHIN_9 in _attacker_positions(game_, a_, d_)
    assert "remained_stationary" in _attacker_positions(game_, a_, d_, stationary=True)


# --- Assault Mastery ---


async def test_assault_mastery_selects_the_assault_doctrine_twice(
    client: AsyncClient, session, tmp_path
):
    game_id, ability_id, named = await _doctrines_game(client, session, tmp_path)
    faction_id = (await _model(session, named["A"])).faction_id
    await _take(session, game_id, "Assault Brethren", faction_id)
    spots = {"A": (20, 38), "D": (20, 4), "B": (30, 38), "C": (40, 38)}
    for name, (x, y) in spots.items():
        response = await _deploy(client, game_id, named[name], _row(named[name], x, y))
        assert response.status_code == 200, response.text
    for battle_round in (1, 2):
        await _advance_to(client, game_id, battle_round, 1, "command")
        assert ASSAULT in (await _command(client, game_id))["options"]
        response = await _choose(client, game_id, ability_id, ASSAULT)
        assert response.status_code == 200, response.text
    # Used twice: no more.
    await _advance_to(client, game_id, 3, 1, "command")
    assert ASSAULT not in (await _command(client, game_id))["options"]


# --- Death Blow ---


async def test_death_blow_adds_one_to_terminator_charge_rolls(
    client: AsyncClient, session, tmp_path
):
    units = {
        1: [
            ("T", 1, {"keywords": ("ADEPTUS ASTARTES", "TERMINATOR")}),
            ("A", 1, {"keywords": ("ADEPTUS ASTARTES",)}),
        ],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    t, a, d = (_unit_named(deployment_, n) for n in "TAD")
    faction_id = await _space_marines(session, t)
    detachment = await _take(session, game_id, "Terminator Storm Force", faction_id)
    rule = DetachmentRule(detachment_id=detachment.id, name="Death Blow")
    rule.keyword_options = [
        [await _keyword(session, "ADEPTUS ASTARTES"), await _keyword(session, "TERMINATOR")]
    ]
    rule.weapon_ability_grants = []
    rule.datasheet_ability_grants = []
    session.add(rule)
    await session.commit()
    # (Deploying alternately.)
    for unit, (x, y) in ((t, (20, 34)), (d, (20, 10)), (a, (30, 34))):
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text

    await _advance_to(client, game_id, 1, 1, "charge")
    for unit in (t, a):
        response = await client.post(
            f"/games/{game_id}/charge/roll", json={"unit_id": unit["unit_id"]}
        )
        assert response.status_code == 200, response.text
    charges = {u["name"]: u for u in response.json()["units"]}
    assert charges["T"]["bonus"] == 1 and charges["T"]["roll"] == sum(charges["T"]["dice"]) + 1
    assert charges["A"]["bonus"] == 0 and charges["A"]["roll"] == sum(charges["A"]["dice"])
    game_ = await _load_game(session, game_id)
    assert charging.charge_bonus(game_, deployment.find_unit(game_, t["unit_id"])) == 1


# --- Gunship Extraction ---


async def _extraction_game(client, session, tmp_path):
    units = {
        1: [
            ("T", 1, {"keywords": ("ADEPTUS ASTARTES", "TERMINATOR")}),
            ("A", 1, {"keywords": ("ADEPTUS ASTARTES",)}),
        ],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    t, a, d = (_unit_named(deployment_, n) for n in "TAD")
    faction_id = await _space_marines(session, t)
    detachment = await _take(session, game_id, "Terminator Storm Force", faction_id)
    stratagem = _stratagem(
        "Gunship Extraction", detachment, "fight", "opponent_turn", "strategic_reserves",
        [await _keyword(session, "ADEPTUS ASTARTES"), await _keyword(session, "TERMINATOR")],
    )
    session.add(stratagem)
    await session.commit()
    # (Deploying alternately.)
    for unit, (x, y) in ((t, (20, 34)), (d, (20, 10)), (a, (30, 34))):
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    return game_id, stratagem.id, t, a


async def _use(client, game_id, stratagem_id, unit, seat=1):
    return await client.post(
        f"/games/{game_id}/stratagems",
        json={"seat": seat, "stratagem_id": stratagem_id, "target_unit_id": unit["unit_id"]},
    )


async def test_gunship_extraction_places_a_terminator_unit_in_reserves(
    client: AsyncClient, session, tmp_path
):
    game_id, stratagem_id, t, a = await _extraction_game(client, session, tmp_path)
    # Seat 2 goes first: the end of their fight phase is seat 1's chance.
    await _advance_to(client, game_id, 1, 2, "fight")
    targets = await client.get(
        f"/games/{game_id}/stratagems/{stratagem_id}/targets", params={"seat": 1}
    )
    assert targets.json() == [{"unit_id": t["unit_id"], "name": "T"}]
    response = await _use(client, game_id, stratagem_id, a)
    assert "keywords" in response.json()["detail"]
    cp = next(p["cp"] for p in (await client.get(f"/games/{game_id}")).json()["players"]
              if p["seat"] == 1)
    response = await _use(client, game_id, stratagem_id, t)
    assert response.status_code == 200, response.text
    player = next(p for p in response.json()["players"] if p["seat"] == 1)
    assert player["cp"] == cp - 1
    assert player["stratagem_uses"][-1]["target_unit_id"] == t["unit_id"]
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, t["unit_id"])
    assert reinforcements.in_reserves(game_, unit)
    assert not deployment.models_on_battlefield(game_, unit)
    # It arrives from Reserves as usual.
    assert unit.id in {u.id for u in reinforcements.reserve_units(game_, 1)}


async def test_gunship_extraction_only_at_the_end_of_the_opponents_fight_phase(
    client: AsyncClient, session, tmp_path
):
    game_id, stratagem_id, t, _ = await _extraction_game(client, session, tmp_path)
    await _advance_to(client, game_id, 1, 2, "charge")
    response = await _use(client, game_id, stratagem_id, t)
    assert response.status_code == 400
    # Not on an engaged unit.
    await _advance_to(client, game_id, 1, 2, "fight")
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, t["unit_id"])
    d = next(u for u in deployment.deployable_units(game_.players[1]) if u.id != unit.id)
    positions = deployment.positions(game_)
    for m in d.unit_models:
        positions[m.id].x, positions[m.id].y = 21, 31.5
    from app.services.in_game import fighting

    assert fighting.engaged(game_, unit)
    assert "Engagement Range" in reinforcements.extraction_reason(game_, 1, unit)


# --- Corporeum Reliquary, Beacon Angelis ---


async def _reserves_with(client, session, tmp_path, enhancement, keywords):
    await _rapid_ingress(session)
    units = {
        1: [("A", 1, {}), ("R", 1, {"keywords": keywords}), ("B", 1, {})],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    a, r, b, d = (_unit_named(deployment_, n) for n in "ARBD")
    faction_id = await _space_marines(session, r)
    detachment = await _take(session, game_id, "Some Detachment", faction_id)
    unit_model = await session.get(UnitModel, r["models"][0]["unit_model_id"])
    await session.refresh(unit_model, ["enhancement"])
    unit_model.enhancement = Enhancement(
        name=enhancement, detachment_id=detachment.id, kind="enhancement", points=25
    )
    await session.commit()
    response = await _set(client, game_id, 1, r, "reserves")
    assert response.status_code == 200, response.text
    for seat in (1, 2):
        await _declare(client, game_id, seat)
    for unit, (x, y) in ((a, (20, 40)), (d, (20, 4)), (b, (30, 40))):
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    return game_id, r


async def test_corporeum_reliquary_arrives_in_the_first_battle_round(
    client: AsyncClient, session, tmp_path
):
    game_id, r = await _reserves_with(
        client, session, tmp_path, "Corporeum Reliquary", ("ADEPTUS ASTARTES", "TERMINATOR")
    )
    # Not by Rapid Ingress (which can't be used in the first battle round).
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, r["unit_id"])
    assert reinforcements.arrival_round(game_, unit)
    assert not reinforcements.arrival_round(game_, unit, rapid_ingress=True)
    # In its own first movement phase: an ingress move.
    await _advance_to(client, game_id, 1, 1, "movement")
    reserves = (await client.get(f"/games/{game_id}/reserves")).json()
    assert reserves["seat"] == 1 and [u["unit_id"] for u in reserves["units"]] == [r["unit_id"]]
    response = await _bring_in(client, game_id, r, _at(r, *EDGE))
    assert response.status_code == 200, response.text


async def test_beacon_angelis_gives_a_kill_team_deep_strike_and_cheaper_rapid_ingress(
    client: AsyncClient, session, tmp_path
):
    game_id, r = await _reserves_with(
        client, session, tmp_path, "Beacon Angelis", ("ADEPTUS ASTARTES", "KILL TEAM")
    )
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, r["unit_id"])
    assert reinforcements.has_deep_strike(unit)
    assert reinforcements.rapid_ingress_discount(unit) == 1
    # Only for a KILL TEAM unit.
    model = unit.unit_models[0].model
    model.keywords = [k for k in model.keywords if k.name != "KILL TEAM"]
    assert not reinforcements.has_deep_strike(unit)
    assert reinforcements.rapid_ingress_discount(unit) == 0


# --- Duty in Death ---


async def _duty_game(client, session, tmp_path):
    units = {1: [("A", 3, {"keywords": ("ADEPTUS ASTARTES",)})], 2: [("D", 1, {"melee": True})]}
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    a, d = (_unit_named(deployment_, n) for n in "AD")
    faction_id = await _space_marines(session, a)
    detachment = await _take(session, game_id, "Assault Brethren", faction_id)
    stratagem = _stratagem(
        "Duty in Death", detachment, "fight", "either", "duty_in_death",
        [await _keyword(session, "ADEPTUS ASTARTES")],
    )
    session.add(stratagem)
    await session.commit()
    for unit, (x, y) in ((a, (20, 34)), (d, (20, 10))):
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    await _advance_to(client, game_id, 1, 2, "fight")
    response = await _use(client, game_id, stratagem.id, a)
    assert response.status_code == 200, response.text
    return game_id, a, d


async def _kill_one(session, game_id, a, d):
    game_ = await _load_game(session, game_id)
    a_, d_ = (deployment.find_unit(game_, u["unit_id"]) for u in (a, d))
    before = casualties.wounds_remaining(game_, a_)
    first = min(before)
    casualties.apply_attack(game_, d_, a_, before, {**before, first: 0}, {})
    return game_, a_, first


async def test_duty_in_death_leaves_a_destroyed_model_until_its_unit_fights(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _duty_game(client, session, tmp_path)
    monkeypatch.setattr(duty_in_death.random, "randint", lambda lo, hi: 4)
    game_, a_, first = await _kill_one(session, game_id, a, d)
    # Destroyed (no wounds left, not attacked again), but still there.
    assert first in deployment.positions(game_)
    assert first not in casualties.wounds_remaining(game_, a_)
    assert duty_in_death.lingering(game_, first)
    assert not game_.models_destroyed
    # Removed once its unit has fought - and its destruction recorded then.
    duty_in_death.remove(game_, a_)
    assert first not in deployment.positions(game_)
    assert [m.unit_model_id for m in game_.models_destroyed] == [first]


async def test_duty_in_death_failed_roll_removes_the_model(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _duty_game(client, session, tmp_path)
    monkeypatch.setattr(duty_in_death.random, "randint", lambda lo, hi: 3)
    game_, _, first = await _kill_one(session, game_id, a, d)
    assert first not in deployment.positions(game_)
    # +1 with the Assault Doctrine active.
    monkeypatch.setattr(duty_in_death, "_assault_doctrine", lambda game, unit: True)
    game_, _, second = await _kill_one(session, game_id, a, d)
    assert second in deployment.positions(game_) and duty_in_death.lingering(game_, second)


async def test_duty_in_death_models_go_at_the_end_of_the_phase(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _duty_game(client, session, tmp_path)
    monkeypatch.setattr(duty_in_death.random, "randint", lambda lo, hi: 6)
    _, _, first = await _kill_one(session, game_id, a, d)
    await session.commit()
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 200, response.text
    session.expire_all()
    game_ = await _load_game(session, game_id)
    assert first not in deployment.positions(game_)
    assert not game_.lingering_models


# --- Deathwatch Allies ---


async def _deathwatch_list(client, session, tmp_path):
    units = {
        1: [
            ("A", 1, {"keywords": ("ADEPTUS ASTARTES",)}),
            # (Its new keywords first: the test helper adds them as it goes.)
            ("W", 1, {"keywords": ("DEATHWATCH", "CHARACTER", "ADEPTUS ASTARTES")}),
        ],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units)
    deployment_ = await _deployment(client, game["id"])
    a, w = (_unit_named(deployment_, n) for n in "AW")
    faction_id = await _space_marines(session, a)
    army_list = await _seat_1_list(session, game["id"])
    return game["id"], army_list.id, faction_id, a, w


async def _list_payload(client, list_id, **changes):
    current = next(item for item in (await client.get("/lists")).json() if item["id"] == list_id)
    keys = ("name", "points_limit", "faction_id", "detachment_ids", "user_id", "subfaction")
    return {**{k: current[k] for k in keys}, **changes}


async def _put_list(client, list_id, **changes):
    return await client.put(f"/lists/{list_id}", json=await _list_payload(client, list_id, **changes))


async def _add_unit(client, session, list_id, unit, points):
    # Another unit in the list, of the same models as `unit`.
    existing = await session.get(Unit, unit["unit_id"])
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    return await client.post(
        "/units",
        json={
            "faction_unit_id": existing.faction_unit_id,
            "points": points,
            "list_id": list_id,
            "unit_models": [
                {"model_id": unit_model.model_id, "weapon_ids": [], "wargear_ids": []}
            ],
        },
    )


async def test_deathwatch_units_need_deathwatch_support_in_another_chapters_list(
    client: AsyncClient, session, tmp_path
):
    game_id, list_id, faction_id, a, w = await _deathwatch_list(client, session, tmp_path)
    # Deathwatch is a Chapter: its units can't join an Ultramarines list...
    response = await _put_list(client, list_id, subfaction="Ultramarines")
    assert response.status_code == 400
    assert "can only be included in a Deathwatch list" in response.json()["detail"]
    # ...unless it takes Deathwatch Support.
    support = Detachment(name="Deathwatch Support", faction_id=faction_id, dp=1)
    session.add(support)
    await session.commit()
    response = await _put_list(
        client, list_id, subfaction="Ultramarines", detachment_ids=[support.id]
    )
    assert response.status_code == 200, response.text
    # Up to 500 pts of DEATHWATCH units (W counts for its points).
    w_points = (await session.get(Unit, w["unit_id"])).points
    response = await _add_unit(client, session, list_id, w, 500 - w_points + 1)
    assert response.status_code == 400 and "500 pts" in response.json()["detail"]
    response = await _add_unit(client, session, list_id, w, 500 - w_points)
    assert response.status_code == 201, response.text
    # Not the Warlord.
    response = await _put_list(client, list_id, warlord_unit_id=w["unit_id"])
    assert response.status_code == 400 and "Warlord" in response.json()["detail"]
    # Its models keep DEATHWATCH, without the list's Chapter keyword.
    session.expire_all()
    from app.routers import combat as combat_router

    for unit, has_ultramarines in ((a, True), (w, False)):
        loaded = await combat_router._load_unit(session, unit["unit_id"])
        keywords = enhancement_rules.model_keywords(loaded, loaded.unit_models[0])
        assert ("ULTRAMARINES" in keywords) == has_ultramarines


def test_kill_team_units_only_take_deathwatch_support_enhancements():
    support = SimpleNamespace(id=1, name="Deathwatch Support")
    other = SimpleNamespace(id=2, name="Assault Brethren")
    exclusive = enhancement_rules.exclusive_detachments([support, other])
    assert "KILL TEAM" in exclusive[1] and 2 not in exclusive
    model = Model(
        name="M", faction_id=1, save=3, toughness=4, oc=1, movement=6, wounds=2, leadership=6
    )
    model.keywords = [Keyword(name=k) for k in ("CHARACTER", "ADEPTUS ASTARTES", "KILL TEAM")]
    theirs = Enhancement(name="Beacon Angelis", detachment_id=1, kind="enhancement", points=25)
    theirs.keywords, theirs.excluded_keywords = [], []
    another = Enhancement(name="Imperium's Sword", detachment_id=2, kind="enhancement", points=20)
    another.keywords, another.excluded_keywords = [], []
    reason = enhancement_rules.model_unavailable_reason
    assert reason(theirs, model, {1, 2}, exclusive=exclusive) is None
    assert "KILL TEAM" in reason(another, model, {1, 2}, exclusive=exclusive)
    # Other units can still take any.
    model.keywords = [Keyword(name=k) for k in ("CHARACTER", "ADEPTUS ASTARTES")]
    assert reason(another, model, {1, 2}, exclusive=exclusive) is None
