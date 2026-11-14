import json

from httpx import AsyncClient

from app.engine.state import GameSecuredObjective
from app.models import ArmyList, Detachment, DetachmentRule
from app.models.army_list import ListWarlord
from app.routers.games import _load_game
from app.seeds.factions.chaos_knights import dread, scenting_fear
from app.services.in_game import deployment, objectives, shooting
from app.services.in_game import game as game_service
from tests import live_games
from tests.test_deployment import _unit_named
from tests.test_dread import _dice, _dread_game, _rule_test
from tests.test_movement import _battle
from tests.test_objectives import ON_THE_RUIN
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place
from tests.test_space_marine_detachments import _keyword, _stratagem

# Chaos Knights detachment rules in a game (see
# app/seeds/factions/chaos_knights/detachment_rules.py, scenting_fear.py).
# Games on the test layout: seat 1 deploys along y 32-44, seat 2 along y
# 0-12, and seat 2 goes first. Its one objective is the Medium ruin's area
# (x 7-13, y 8-12).

DETACHMENTS = "app/data/factions/chaos_knights/detachments.json"


def _text(rule_name: str) -> str:
    with open(DETACHMENTS) as f:
        data = json.load(f)
    return next(
        r["description"] for d in data["detachments"] for r in d["rules"] if r["name"] == rule_name
    )


async def _detachment(session, game_id, seat, name, rule_name) -> Detachment:
    # The seat's list takes a detachment `name` with its rule `rule_name`.
    army_list = await session.get(ArmyList, live_games.player(game_id, seat).list_id)
    await session.refresh(army_list, ["detachments"])
    detachment = Detachment(name=name, faction_id=army_list.faction_id, dp=1)
    session.add(detachment)
    await session.flush()
    rule = DetachmentRule(detachment_id=detachment.id, name=rule_name, description=_text(rule_name))
    rule.keyword_options = []
    rule.weapon_ability_grants = []
    rule.datasheet_ability_grants = []
    session.add(rule)
    army_list.detachments.append(detachment)
    await session.commit()
    return detachment


# --- Paragons of Terror ---


async def test_paragons_of_terror_selects_one_more_dread_ability(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d, ability_id = await _dread_game(client, session, tmp_path)
    await _detachment(session, game_id, 2, "Traitoris Lance", "Paragons of Terror")
    # (As if it's the start of the first battle round.)
    game = live_games.game(game_id)
    game.battle_round, game.phase = 1, "start_of_round"

    async def rules():
        start = (await client.get(f"/games/{game_id}/round-start")).json()
        found = {r["name"]: r for p in start["players"] if p["seat"] == 2 for r in p["rules"]}
        return found["Harbingers of Dread"], found["Paragons of Terror"]

    async def choose(option, rule=None):
        return await client.post(
            f"/games/{game_id}/round-start/choice",
            json={"seat": 2, "faction_ability_id": ability_id, "option": option, "rule": rule},
        )

    own, paragons = await rules()
    assert paragons["choice_rule"] == "Paragons of Terror"
    assert paragons["faction_ability_id"] == ability_id
    # Not randomly selected.
    assert "Roll two D6" not in paragons["options"] and "Doom" in paragons["options"]
    # After the army rule's own.
    assert (await choose("Doom", "Paragons of Terror")).status_code == 400
    assert (await choose("Despair")).status_code == 200
    own, paragons = await rules()
    assert "Despair" not in paragons["options"]
    response = await choose("Doom", "Paragons of Terror")
    assert response.status_code == 200, response.text
    own, paragons = await rules()
    assert (own["chosen"], paragons["chosen"]) == ("Despair", "Doom")
    assert {"Despair", "Doom"} <= dread.active(live_games.game(game_id), 2)
    # The army rule's chosen again: the extra one's made again too.
    assert (await choose("Dismay")).status_code == 200
    own, paragons = await rules()
    assert (own["chosen"], paragons["chosen"]) == ("Dismay", None)
    assert "Doom" not in dread.active(live_games.game(game_id), 2)


# --- Tyrannical Court ---


async def _court_game(client, session, tmp_path, keywords=("CHAOS KNIGHTS", "CHARACTER")):
    units = {1: [("A", 2, {"keywords": keywords})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    detachment = await _detachment(session, game_id, 1, "Lords of Dread", "Tyrannical Court")
    return game_id, a, d, detachment


async def test_tyrannical_court_improves_chaos_knights_characters_oc(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d, _ = await _court_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    a_ = deployment.find_unit(game, a["unit_id"])
    d_ = deployment.find_unit(game, d["unit_id"])
    m = a_.unit_models[0]
    assert objectives.model_oc(game, m) == m.model.oc + 2
    # Not the other army's, nor other models.
    n = d_.unit_models[0]
    assert objectives.model_oc(game, n) == n.model.oc


async def test_tyrannical_court_without_character_keyword(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d, _ = await _court_game(client, session, tmp_path, keywords=("CHAOS KNIGHTS",))
    game = await _load_game(session, game_id)
    m = deployment.find_unit(game, a["unit_id"]).unit_models[0]
    assert objectives.model_oc(game, m) == m.model.oc


async def test_claimed_for_the_dark_gods_for_0cp_once_a_round(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d, detachment = await _court_game(client, session, tmp_path)
    stratagem = _stratagem(
        "Claimed for the Dark Gods", detachment, "command", "your_turn", "claim_objective",
        [await _keyword(session, "CHAOS KNIGHTS"), await _keyword(session, "CHARACTER")],
    )
    session.add(stratagem)
    army_list = await session.get(ArmyList, live_games.player(game_id, 1).list_id)
    army_list.warlord_link = ListWarlord(list_id=army_list.id, unit_id=a["unit_id"])
    await session.commit()
    stratagem_id = stratagem.id
    await _place(session, a, ON_THE_RUIN)
    await _advance_to(client, game_id, 1, 1, "command")
    game = await _load_game(session, game_id)
    [ruin] = objectives.objectives(game)
    assert objectives.controlled_by(game, 1)
    targets = (
        await client.get(f"/games/{game_id}/stratagems/{stratagem_id}/targets", params={"seat": 1})
    ).json()
    assert [(t["name"], t["cp"], [c["id"] for c in t["choices"]]) for t in targets] == [
        ("A", 0, [ruin.id])
    ]
    cp = live_games.player(game_id, 1).cp
    response = await client.post(
        f"/games/{game_id}/stratagems",
        json={"seat": 1, "stratagem_id": stratagem_id, "target_unit_id": a["unit_id"],
              "target_choice_id": ruin.id},
    )
    assert response.status_code == 200, response.text
    game = live_games.game(game_id)
    assert live_games.player(game_id, 1).cp == cp
    [secured] = game.secured_objectives
    assert (secured.objective_id, secured.seat, secured.level) == (ruin.id, 1, 5)
    # Once a battle round.
    assert game_service.free_rule(game, live_games.player(game_id, 1), stratagem) is None


async def test_claimed_for_the_dark_gods_costs_cp_without_the_warlord(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d, detachment = await _court_game(client, session, tmp_path)
    stratagem = _stratagem("Claimed for the Dark Gods", detachment, "command", "your_turn")
    session.add(stratagem)
    await session.commit()
    game = await _load_game(session, game_id)
    # No WARLORD.
    assert game_service.free_rule(game, live_games.player(game_id, 1), stratagem) is None


async def test_a_level_of_control_holds_against_less(client: AsyncClient, session, tmp_path):
    game_id, a, d, _ = await _court_game(client, session, tmp_path)
    await _place(session, d, ON_THE_RUIN[:1])
    game = await _load_game(session, game_id)
    [ruin] = objectives.objectives(game)
    game.secured_objectives.append(GameSecuredObjective(objective_id=ruin.id, seat=1, level=5))
    objectives.refresh_secured(game)
    # Seat 2's OC there is more than seat 1's 0, but not more than 5.
    assert objectives.secured_by(game, ruin.id) == 1
    game.secured_objectives[0].level = None
    objectives.refresh_secured(game)
    assert objectives.secured_by(game, ruin.id) is None


# --- Scenting Fear ---


async def test_scenting_fear_adds_6_to_detection_range_once_a_round(
    client: AsyncClient, session, tmp_path
):
    units = {1: [("A", 1, {"keywords": ("WAR DOG",)})], 2: [("D", 1, {}), ("E", 1, {})]}
    game, deployment_ = await _battle(
        client, session, tmp_path, units=units, spots={"A": (20, 38), "D": (20, 4), "E": (40, 4)}
    )
    game_id = game["id"]
    a, d, e = (_unit_named(deployment_, n) for n in "ADE")
    await _detachment(session, game_id, 1, "Hunting Warpack", "Scenting Fear")
    await _place(session, a, [(20, 20)])
    await _place(session, d, [(20, 26)])
    await _place(session, e, [(40, 4)])
    await _advance_to(client, game_id, 1, 1, "shooting")
    state = (await client.get(f"/games/{game_id}/scenting-fear")).json()
    assert state["seat"] == 1 and state["reason"] is None
    # Within 12" of A: D, not E.
    assert [t["unit_id"] for t in state["targets"]] == [d["unit_id"]]
    response = await client.post(
        f"/games/{game_id}/scenting-fear", json={"seat": 1, "target_unit_id": e["unit_id"]}
    )
    assert response.status_code == 400
    response = await client.post(
        f"/games/{game_id}/scenting-fear", json={"seat": 1, "target_unit_id": d["unit_id"]}
    )
    assert response.status_code == 200, response.text
    assert [u["unit_id"] for u in response.json()["scented"]] == [d["unit_id"]]
    game_ = live_games.game(game_id)
    d_ = deployment.find_unit(game_, d["unit_id"])
    assert shooting.detection_range(game_, d_) == shooting.DETECTION_RANGE + 6
    # Once a battle round.
    assert response.json()["reason"] is not None
    assert scenting_fear.cant_reason(game_, live_games.player(game_id, 1)) is not None
    # Until the end of the phase.
    await _advance_to(client, game_id, 1, 1, "charge")
    game_ = live_games.game(game_id)
    assert shooting.detection_range(game_, d_) == shooting.DETECTION_RANGE


# --- Wretched Thralls ---


async def _thralls_game(client, session, tmp_path, keywords):
    units = {1: [("A", 3, {"keywords": keywords})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    await _detachment(session, game_id, 1, "Iconoclast Fiefdom", "Wretched Thralls")
    return game_id, _unit_named(deployment_, "A")


async def test_wretched_thralls_damned_units_reroll_a_failed_test(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a = await _thralls_game(client, session, tmp_path, ("DAMNED",))
    test = await _rule_test(client, game_id, a)
    _dice(monkeypatch, 1, 1, 6, 6)
    state = (
        await client.post(f"/games/{game_id}/battle-shock/{test['id']}/take", json={})
    ).json()
    [taken] = state["taken"]
    assert (taken["passed"], taken["dice"], taken["rerolled"]) == (True, [6, 6], [1, 1])


async def test_wretched_thralls_only_damned_units(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a = await _thralls_game(client, session, tmp_path, ())
    test = await _rule_test(client, game_id, a)
    _dice(monkeypatch, 1, 1, 6, 6)
    state = (
        await client.post(f"/games/{game_id}/battle-shock/{test['id']}/take", json={})
    ).json()
    [taken] = state["taken"]
    assert (taken["passed"], taken["rerolled"]) == (False, [])


async def test_the_agent_can_use_scenting_fear(client: AsyncClient, session, tmp_path):
    from tests.test_agent import _decision
    from tests.test_agent_sororitas import _apply

    units = {1: [("A", 1, {"keywords": ("WAR DOG",)})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _detachment(session, game_id, 1, "Hunting Warpack", "Scenting Fear")
    await _place(session, a, [(20, 20)])
    await _place(session, d, [(20, 26)])
    await _advance_to(client, game_id, 1, 1, "shooting")
    decision = await _decision(client, game_id)
    [action] = [x for x in decision["actions"] if x["type"] == "scenting_fear"]
    assert action["params"] == {"seat": 1, "target_unit_id": d["unit_id"]}
    result = await _apply(client, game_id, action)
    assert result["log"]["ok"], result["log"]
    assert not [x for x in result["decision"]["actions"] if x["type"] == "scenting_fear"]


async def test_the_agent_makes_the_paragons_choice_after_its_own(
    client: AsyncClient, session, tmp_path
):
    from tests.test_agent import _decision
    from tests.test_agent_sororitas import _apply

    game_id, a, d, ability_id = await _dread_game(client, session, tmp_path)
    await _detachment(session, game_id, 2, "Traitoris Lance", "Paragons of Terror")
    game = live_games.game(game_id)
    game.battle_round, game.phase = 1, "start_of_round"
    decision = await _decision(client, game_id)
    choices = [x for x in decision["actions"] if x["type"] == "round_start_choice"]
    assert choices and not any(x["params"].get("rule") for x in choices)
    own = next(x for x in choices if x["params"]["option"] == "Despair")
    assert (await _apply(client, game_id, own))["log"]["ok"]
    decision = await _decision(client, game_id)
    extra = [x for x in decision["actions"] if x["params"].get("rule") == "Paragons of Terror"]
    assert extra and "Despair" not in [x["params"]["option"] for x in extra]
    result = await _apply(client, game_id, extra[0])
    assert result["log"]["ok"], result["log"]
