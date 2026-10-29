from httpx import AsyncClient

from app.models import DetachmentRule, Enhancement, GameSelectedObjective, UnitModel
from app.models.model import TransportCapacity
from app.routers.games import _attacker_positions, _defender_positions, _load_game
from app.seeds import stratagems as stratagem_seeds
from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech
from app.seeds.factions.adeptus_mechanicus.conditions import ON_ACQUISITION, TARGET_ON_ACQUISITION
from app.services.in_game import (
    battle_formations,
    casualties,
    charging,
    deployment,
    objectives,
    selected_objectives,
    stratagem_actions,
)
from tests.test_casualties import _set_models
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named
from tests.test_fighting import BLADE, _check_consolidation, _done, _fight, _fight_state
from tests.test_movement import _battle
from tests.test_objectives import ON_THE_RUIN
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place
from tests.test_space_marine_detachments import (
    _keyword,
    _model,
    _space_marines,
    _stratagem,
    _take,
    _use,
)
from tests.test_space_marines import _applies

# The Explorator Maniple (Adeptus Mechanicus). Games on the test layout: the
# attacker (seat 1) deploys along y 32-44, the defender (seat 2) along y 0-12,
# and the defender goes first. Its one objective is the Medium ruin's area (x
# 7-13, y 8-12). Seat 1's list has taken the detachment, with its rule
# Acquisition At Any Cost.

RULE = "Acquisition At Any Cost"
ACQUISITION = "Acquisition"


# --- combat ---


def test_acquisition_at_any_cost_rerolls_wound_ones_on_or_against_the_marker():
    rules = admech.RULES[RULE]
    ones = {"step": "wound", "roll": 1}
    assert _applies(rules, {**ones, "attacker_positions": {ON_ACQUISITION}})
    assert _applies(rules, {**ones, "attacker_positions": {TARGET_ON_ACQUISITION}})
    assert not _applies(rules, {**ones, "attacker_positions": set()})
    # The defender's own marker doesn't count.
    assert not _applies(rules, {**ones, "defender_positions": {ON_ACQUISITION}})


def test_genetor_and_logis():
    [genetor] = admech.RULES["Genetor"]
    assert genetor.side == "defender"
    assert _applies([genetor], {"defender_positions": {ON_ACQUISITION}})
    assert not _applies([genetor], {"defender_positions": set()})
    logis = admech.RULES["Logis"]
    assert _applies(logis, {"step": "pre_hit", "attacker_positions": {TARGET_ON_ACQUISITION}})
    assert not _applies(logis, {"step": "pre_hit", "attacker_positions": {ON_ACQUISITION}})


def test_the_stratagems_are_seeded_with_their_game_actions():
    entries = {e["name"]: e for e in stratagem_seeds.load()}
    if "Cached Acquisition" not in entries:
        # (The local data files aren't there.)
        return
    assert entries["Cached Acquisition"]["game_action"] == "secure_on_destruction"
    assert entries["Priority Reclamation"]["game_action"] == "longer_consolidation"
    assert entries["Infoslave Skull"]["game_action"] == "extra_selected_objective"
    assert entries["Reactive Safeguard"]["game_action"] == "reactive_embark"
    assert entries["Auto-Oracular Retrieval"]["conditions"] == ["target_within_acquisition"]
    for name in ("Priority Reclamation", "Infoslave Skull", "Reactive Safeguard"):
        assert stratagem_seeds.action_config(name)


# --- games ---


async def _explorator(client, session, tmp_path, units, spots, stratagems=()):
    # Seat 1's list takes the Explorator Maniple, with its rule and the
    # stratagems given ((name, phase, turn, game action, keywords)); the units
    # deployed at `spots` ({name: (x, y)}), seat 1 first. Returns the game's
    # id, the units by name, and the stratagems' ids by name.
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    first = _unit_named(deployment_, units[1][0][0])
    faction_id = await _space_marines(session, first)
    detachment = await _take(session, game_id, "Explorator Maniple", faction_id)
    rule = DetachmentRule(detachment_id=detachment.id, name=RULE)
    rule.keyword_options = []
    rule.weapon_ability_grants = []
    rule.datasheet_ability_grants = []
    session.add(rule)
    ids = {}
    for name, phase, turn, action, keywords in stratagems:
        stratagem = _stratagem(
            name, detachment, phase, turn, action, [await _keyword(session, k) for k in keywords]
        )
        session.add(stratagem)
        await session.flush()
        ids[name] = stratagem.id
    await session.commit()
    seat_1 = [n for n, _, _ in units[1]]
    seat_2 = [n for n, _, _ in units[2]]
    order = [n for pair in zip(seat_1, seat_2) for n in pair]
    order += seat_1[len(seat_2):] + seat_2[len(seat_1):]
    for name in order:
        unit = _unit_named(deployment_, name)
        response = await _deploy(client, game_id, unit, _row(unit, *spots[name]))
        assert response.status_code == 200, response.text
    deployment_ = await _deployment(client, game_id)
    return game_id, {u["name"]: u for u in deployment_["units"]}, ids


async def _ruin_id(session, game_id) -> int:
    game_ = await _load_game(session, game_id)
    [objective] = objectives.objectives(game_)
    return objective.id


async def _select(client, game_id, objective_id, seat=1):
    return await client.post(
        f"/games/{game_id}/command/objective",
        json={"seat": seat, "name": ACQUISITION, "objective_id": objective_id},
    )


def _cp(game, seat):
    return next(p["cp"] for p in game["players"] if p["seat"] == seat)


async def test_the_acquisition_objective_is_selected_in_the_command_phase(
    client: AsyncClient, session, tmp_path
):
    units = {1: [("A", 2, {})], 2: [("D", 2, {})]}
    game_id, by_name, _ = await _explorator(
        client, session, tmp_path, units, {"A": (20, 34), "D": (20, 4)}
    )
    a, d = by_name["A"], by_name["D"]
    ruin = await _ruin_id(session, game_id)
    # Seat 2 (no such rule) needn't select one.
    command = (await client.get(f"/games/{game_id}/command")).json()
    assert command["objective_selections"] == []
    await _advance_to(client, game_id, 1, 1, "command")
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 400
    assert "Acquisition objective marker" in response.json()["detail"]
    [selection] = (await client.get(f"/games/{game_id}/command")).json()["objective_selections"]
    assert (selection["name"], selection["rule"], selection["objective_id"]) == (
        ACQUISITION, RULE, None
    )
    assert [o["id"] for o in selection["options"]] == [ruin]
    assert selection["options"][0]["name"].startswith("Objective 1")
    # Only its own player, in their Command phase.
    assert (await _select(client, game_id, ruin, seat=2)).status_code == 400
    response = await _select(client, game_id, ruin)
    assert response.status_code == 200, response.text
    assert response.json()["objective_selections"][0]["objective_id"] == ruin

    # A on it: A's attacks are made within range of it, and attacks on A are
    # against a unit within range of its own (not seat 2's).
    await _place(session, a, ON_THE_RUIN)
    game_ = await _load_game(session, game_id)
    a_, d_ = (deployment.find_unit(game_, u["unit_id"]) for u in (a, d))
    assert ON_ACQUISITION in _attacker_positions(game_, a_, d_)
    assert TARGET_ON_ACQUISITION not in _attacker_positions(game_, a_, d_)
    assert ON_ACQUISITION in _defender_positions(game_, a_)
    assert TARGET_ON_ACQUISITION not in _attacker_positions(game_, d_, a_)
    # D on it instead: A's attacks target a unit within range of it.
    await _place(session, a, [(20, 34), (21.5, 34)])
    await _place(session, d, ON_THE_RUIN)
    session.expire_all()
    game_ = await _load_game(session, game_id)
    a_, d_ = (deployment.find_unit(game_, u["unit_id"]) for u in (a, d))
    assert TARGET_ON_ACQUISITION in _attacker_positions(game_, a_, d_)
    assert ON_ACQUISITION not in _attacker_positions(game_, a_, d_)
    assert ON_ACQUISITION not in _defender_positions(game_, d_)

    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 200, response.text
    # It lasts until the start of their next Command phase.
    await _advance_to(client, game_id, 2, 2, "command")
    session.expire_all()
    game_ = await _load_game(session, game_id)
    assert selected_objectives.objective_ids(game_, 1, ACQUISITION) == {ruin}
    await _advance_to(client, game_id, 2, 1, "command")
    session.expire_all()
    game_ = await _load_game(session, game_id)
    assert selected_objectives.objective_ids(game_, 1, ACQUISITION) == set()
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 400


async def test_magos_gains_cp_at_the_end_of_the_command_phase(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    units = {1: [("A", 2, {})], 2: [("D", 2, {})]}
    game_id, by_name, _ = await _explorator(
        client, session, tmp_path, units, {"A": (20, 34), "D": (20, 4)}
    )
    a = by_name["A"]
    game_ = await _load_game(session, game_id)
    detachment = next(p for p in game_.players if p.seat == 1).army_list.detachments[0]
    unit_model = await session.get(UnitModel, a["models"][0]["unit_model_id"])
    await session.refresh(unit_model, ["enhancement"])
    unit_model.enhancement = Enhancement(
        name="Magos", detachment_id=detachment.id, kind="enhancement", points=10
    )
    await session.commit()
    monkeypatch.setattr(selected_objectives.random, "randint", lambda lo, hi: 4)
    ruin = await _ruin_id(session, game_id)

    await _advance_to(client, game_id, 1, 1, "command")
    await _select(client, game_id, ruin)
    # Off the marker: no roll.
    cp = _cp((await client.get(f"/games/{game_id}")).json(), 1)
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "movement" and _cp(game, 1) == cp

    # On it, rolling a 4: +1CP.
    await _place(session, a, ON_THE_RUIN)
    await _advance_to(client, game_id, 2, 1, "command")
    await _select(client, game_id, ruin)
    cp = _cp((await client.get(f"/games/{game_id}")).json(), 1)
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "movement" and _cp(game, 1) == cp + 1


async def test_infoslave_skull_adds_an_acquisition_objective(
    client: AsyncClient, session, tmp_path
):
    units = {1: [("A", 1, {"keywords": ("TECH-PRIEST",)}), ("B", 1, {})], 2: [("D", 1, {})]}
    skull = ("Infoslave Skull", "command", "your_turn", "extra_selected_objective", ("TECH-PRIEST",))
    game_id, by_name, ids = await _explorator(
        client, session, tmp_path, units, {"A": (10, 33), "B": (30, 34), "D": (20, 4)}, [skull]
    )
    a = by_name["A"]
    ruin = await _ruin_id(session, game_id)
    await _advance_to(client, game_id, 1, 1, "command")
    stratagem_id = ids["Infoslave Skull"]
    targets = (
        await client.get(f"/games/{game_id}/stratagems/{stratagem_id}/targets", params={"seat": 1})
    ).json()
    assert [(t["name"], [c["id"] for c in t["choices"]]) for t in targets] == [("A", [ruin])]
    response = await _use(client, game_id, stratagem_id, a)
    assert response.status_code == 200, response.text
    [selection] = (await client.get(f"/games/{game_id}/command")).json()["objective_selections"]
    assert selection["extra_objective_ids"] == [ruin] and selection["objective_id"] is None
    # It's one of their Acquisition objective markers - but not the rule's
    # own selection, which they still make.
    session.expire_all()
    game_ = await _load_game(session, game_id)
    assert selected_objectives.objective_ids(game_, 1, ACQUISITION) == {ruin}
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 400
    assert (await _select(client, game_id, ruin)).status_code == 200
    # Their Acquisition objective markers can't be its target.
    session.expire_all()
    game_ = await _load_game(session, game_id)
    player = next(p for p in game_.players if p.seat == 1)
    stratagem = next(u.stratagem for u in player.stratagem_uses)
    a_ = deployment.find_unit(game_, a["unit_id"])
    assert stratagem_actions.choices(game_, player, stratagem, a_) == []


async def test_cached_acquisition_secures_where_the_unit_died(
    client: AsyncClient, session, tmp_path
):
    units = {1: [("A", 2, {"keywords": ("ADEPTUS MECHANICUS",)})], 2: [("D", 1, {})]}
    cached = ("Cached Acquisition", "shooting", "either", "secure_on_destruction",
              ("ADEPTUS MECHANICUS",))
    game_id, by_name, ids = await _explorator(
        client, session, tmp_path, units, {"A": (20, 34), "D": (20, 4)}, [cached]
    )
    a, d = by_name["A"], by_name["D"]
    ruin = await _ruin_id(session, game_id)
    await _advance_to(client, game_id, 1, 2, "shooting")
    stratagem_id = ids["Cached Acquisition"]
    usable = (await client.get(f"/games/{game_id}/stratagems", params={"seat": 1})).json()
    assert stratagem_id not in [s["id"] for s in usable]

    # A, controlling the ruin (as determined at the end of the last phase),
    # is destroyed.
    from app.services.in_game import objectives

    await _place(session, a, ON_THE_RUIN)
    game_ = await _load_game(session, game_id)
    objectives.determine(game_)
    a_, d_ = (deployment.find_unit(game_, u["unit_id"]) for u in (a, d))
    before = casualties.wounds_remaining(game_, a_)
    casualties.apply_attack(game_, d_, a_, before, {i: 0 for i in before}, {})
    await session.commit()
    targets = (
        await client.get(f"/games/{game_id}/stratagems/{stratagem_id}/targets", params={"seat": 1})
    ).json()
    assert [(t["name"], [c["id"] for c in t["choices"]]) for t in targets] == [("A", [ruin])]
    response = await _use(client, game_id, stratagem_id, a)
    assert response.status_code == 200, response.text
    session.expire_all()
    game_ = await _load_game(session, game_id)
    assert objectives.secured_by(game_, ruin) == 1
    # Still seat 1's, with none of their models there.
    [current] = objectives.control(game_)
    assert current.controller == 1


async def test_priority_reclamation_consolidates_6_onto_the_acquisition_marker(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    monkeypatch.setattr("app.services.combat.random.randint", lambda lo, hi: 6)
    units = {1: [("A", 1, {**BLADE, "keywords": ("ADEPTUS MECHANICUS",)})], 2: [("D", 1, BLADE)]}
    game, deployment_ = await _battle(
        client, session, tmp_path, units=units, spots={"A": (20, 38), "D": (20, 4)}
    )
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    faction_id = await _space_marines(session, a)
    detachment = await _take(session, game_id, "Explorator Maniple", faction_id)
    stratagem = _stratagem(
        "Priority Reclamation", detachment, "fight", "either", "longer_consolidation",
        [await _keyword(session, "ADEPTUS MECHANICUS")],
    )
    session.add(stratagem)
    rule = DetachmentRule(detachment_id=detachment.id, name=RULE)
    rule.keyword_options = []
    rule.weapon_ability_grants = []
    rule.datasheet_ability_grants = []
    session.add(rule)
    await session.commit()
    ruin = await _ruin_id(session, game_id)
    # Seat 1's Acquisition objective marker is the ruin (as if selected in
    # their Command phase); A stands 3.9" from it, engaged with D.
    game_ = await _load_game(session, game_id)
    game_.selected_objectives.append(
        GameSelectedObjective(seat=1, name=ACQUISITION, objective_id=ruin, battle_round=1)
    )
    await session.commit()
    await _place(session, a, [(17.5, 10)])
    await _place(session, d, [(19.5, 10)])
    await _set_models(session, d, wounds=1, save=7)
    await _set_models(session, a, wounds=10, save=2)
    for phase in ("shooting", "charge", "fight"):
        game = (await client.post(f"/games/{game_id}/advance")).json()
        assert game["phase"] == phase
    for seat in (2, 1):
        game = (await _done(client, game_id, seat)).json()

    # D picks first (its turn), then A.
    assert (await _fight(client, game_id, d, a)).status_code == 200
    response = await _fight(client, game_id, a, d, skip=False)
    assert response.status_code == 200, response.text
    assert response.json()["combat"]["models_destroyed"] == 1
    # Too far to consolidate onto the ruin with 3".
    assert (await _fight_state(client, game_id))["step"] != "consolidate"
    response = await _use(client, game_id, stratagem.id, a)
    assert response.status_code == 200, response.text
    assert (await _fight_state(client, game_id))["step"] == "consolidate"
    a = _unit_named(await _deployment(client, game_id), "A")
    model_id = a["models"][0]["unit_model_id"]
    # 3.5" towards it but not onto it: further than 3" needs ending on it.
    check = await _check_consolidation(
        client, game_id, a, [{"unit_model_id": model_id, "x": 14.0, "y": 10}]
    )
    assert any("Acquisition objective marker" in p for p in check["problems"])
    positions = [{"unit_model_id": model_id, "x": 13.3, "y": 10}]
    assert (await _check_consolidation(client, game_id, a, positions))["valid"]
    response = await client.post(
        f"/games/{game_id}/fight/consolidate",
        json={"unit_id": a["unit_id"], "positions": positions},
    )
    assert response.status_code == 200, response.text


async def test_reactive_safeguard_embarks_a_charged_unit(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    infantry = ("ADEPTUS MECHANICUS", "INFANTRY")
    units = {
        1: [
            ("A", 2, {"keywords": infantry}),
            ("T", 1, {"keywords": ("ADEPTUS MECHANICUS", "TRANSPORT")}),
        ],
        2: [("D", 1, {})],
    }
    safeguard = ("Reactive Safeguard", "charge", "opponent_turn", "reactive_embark", infantry)
    game_id, by_name, ids = await _explorator(
        client, session, tmp_path, units, {"A": (20, 34), "T": (30, 34), "D": (20, 4)},
        [safeguard],
    )
    a, t, d = by_name["A"], by_name["T"], by_name["D"]
    model = await _model(session, t)
    model.transport = TransportCapacity(capacity=7, keywords=("INFANTRY",))
    await session.commit()
    ruin = await _ruin_id(session, game_id)
    await _advance_to(client, game_id, 1, 1, "command")
    assert (await _select(client, game_id, ruin)).status_code == 200
    await _place(session, a, ON_THE_RUIN)
    await _place(session, t, [(10, 14)])
    await _place(session, d, [(20, 10)])

    await _advance_to(client, game_id, 2, 2, "charge")
    stratagem_id = ids["Reactive Safeguard"]
    usable = (await client.get(f"/games/{game_id}/stratagems", params={"seat": 1})).json()
    # No charge declared yet.
    assert stratagem_id not in [s["id"] for s in usable]
    monkeypatch.setattr(charging.random, "randint", lambda lo, hi: 6)
    response = await client.post(f"/games/{game_id}/charge/roll", json={"unit_id": d["unit_id"]})
    assert response.status_code == 200, response.text
    targets = (
        await client.get(f"/games/{game_id}/stratagems/{stratagem_id}/targets", params={"seat": 1})
    ).json()
    assert [(x["name"], [c["id"] for c in x["choices"]]) for x in targets] == [
        ("A", [t["unit_id"]])
    ]
    response = await _use(client, game_id, stratagem_id, a)
    assert response.status_code == 200, response.text
    session.expire_all()
    game_ = await _load_game(session, game_id)
    a_ = deployment.find_unit(game_, a["unit_id"])
    assert not deployment.models_on_battlefield(game_, a_)
    assert any(
        f.unit_id == a_.id and f.place == "embarked" and f.transport_unit_id == t["unit_id"]
        for f in game_.battle_formations
    )
    assert battle_formations.is_transport(deployment.find_unit(game_, t["unit_id"]))
