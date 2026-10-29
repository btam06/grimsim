from httpx import AsyncClient

from app.models import GameStratagemTarget, GameStratagemUse, Stratagem
from app.routers.games import _load_game
from app.services.in_game import battle_shock, deployment
from app.services.in_game import game as game_service
from tests.test_deployment import _unit_named
from tests.test_movement import _battle

# 15.01: a player can't target the same unit with more than one stratagem in
# a phase; 01.07: nor one of theirs that's Battle-shocked. Seat 2's movement
# phase.


async def test_one_stratagem_per_unit_per_phase(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path)
    d = _unit_named(deployment_, "D")
    stratagem = Stratagem(name="Some Stratagem", cp=1, is_core=True)
    session.add(stratagem)
    await session.commit()
    game_ = await _load_game(session, game["id"])
    player = game_service.player_at(game_, 2)
    unit = deployment.find_unit(game_, d["unit_id"])
    assert game_service.unit_target_reason(game_, player, unit) is None
    use = GameStratagemUse(
        stratagem_id=stratagem.id, battle_round=game_.battle_round, turn_seat=game_.turn_seat,
        phase=game_.phase, cp=1,
    )
    use.target_link = GameStratagemTarget(unit_id=unit.id)
    player.stratagem_uses.append(use)
    assert "already targeted it this phase" in game_service.unit_target_reason(
        game_, player, unit
    )


async def test_battle_shocked_units_cant_be_targeted(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path)
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, _unit_named(deployment_, "D")["unit_id"])
    battle_shock.battle_shock_outright(game_, unit, "test", 1)
    player = game_service.player_at(game_, 2)
    assert game_service.unit_target_reason(game_, player, unit) == "it's Battle-shocked"


# --- the core stratagems' game actions (see app/services/in_game/core_stratagems.py) ---


async def _core(session, name, action, phase=None, turn="your_turn"):
    # A core stratagem (1CP) with that game action - any phase without one.
    from app.models import StratagemTiming

    stratagem = Stratagem(name=name, cp=1, is_core=True)
    stratagem.game_action = action
    if phase:
        stratagem.timings = [StratagemTiming(phase=phase, turn=turn)]
    session.add(stratagem)
    await session.commit()
    return stratagem.id


async def _cp(session, game_id, cp=5):
    from sqlalchemy import update

    from app.models import GamePlayer

    await session.execute(update(GamePlayer).where(GamePlayer.game_id == game_id).values(cp=cp))
    await session.commit()


async def _use(client, game_id, stratagem_id, unit, seat=2, choice=None):
    return await client.post(
        f"/games/{game_id}/stratagems",
        json={"seat": seat, "stratagem_id": stratagem_id, "target_unit_id": unit["unit_id"],
              "target_choice_id": choice},
    )


def _uses(game, seat):
    return next(p for p in game["players"] if p["seat"] == seat)["stratagem_uses"]


async def test_explosives(client: AsyncClient, session, tmp_path, monkeypatch):
    from tests.test_casualties import _set_models
    from tests.test_reinforcements import _advance_to
    from tests.test_shooting import _place

    monkeypatch.setattr("app.services.in_game.core_stratagems.random.randint", lambda a, b: 4)
    stratagem_id = await _core(session, "Explosives", "explosives", "shooting")
    units = {1: [("A", 5, {})], 2: [("D", 1, {"keywords": ("GRENADES",)})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _set_models(session, a, wounds=1)
    await _place(session, a, [(20 + i * 1.5, 12) for i in range(5)])
    await _cp(session, game["id"])
    await _advance_to(client, game["id"], 1, 2, "shooting")
    response = await _use(client, game["id"], stratagem_id, d, choice=a["unit_id"])
    assert response.status_code == 200, response.text
    [use] = _uses(response.json(), 2)
    # Six 4s: six mortal wounds - A's five 1-wound models.
    assert "6 mortal wounds on A" in use["outcome"]
    left = [m for m in _unit_named(
        (await client.get(f"/games/{game['id']}/deployment")).json(), "A"
    )["models"] if m["position"]]
    assert left == []


async def test_command_reroll_rerolls_a_charge(client: AsyncClient, session, tmp_path, monkeypatch):
    from tests.test_reinforcements import _advance_to
    from tests.test_shooting import _place

    stratagem_id = await _core(session, "Command Re-roll", "command_reroll")
    game, deployment_ = await _battle(client, session, tmp_path)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _place(session, a, [(20 + i * 1.5, 14) for i in range(5)])
    await _cp(session, game["id"])
    await _advance_to(client, game["id"], 1, 2, "charge")
    monkeypatch.setattr("app.services.in_game.charging.random.randint", lambda a_, b: 1)
    await client.post(f"/games/{game['id']}/charge/roll", json={"unit_id": d["unit_id"]})
    monkeypatch.setattr("app.services.in_game.core_stratagems.random.randint", lambda a_, b: 6)
    from app.services.in_game.core_stratagems import CHARGE_ROLL

    response = await _use(client, game["id"], stratagem_id, d, choice=CHARGE_ROLL)
    assert response.status_code == 200, response.text
    assert _uses(response.json(), 2)[0]["outcome"] == "Charge roll 2 re-rolled: 12"


async def test_heroic_intervention(client: AsyncClient, session, tmp_path, monkeypatch):
    # The end of seat 2's charge phase: seat 1's A (within 12" of D) can
    # intervene - Into the Fray for 1CP more - and charge D in seat 2's turn.
    from tests.test_reinforcements import _advance_to
    from tests.test_shooting import _place

    from app.services.in_game.core_stratagems import INTO_THE_FRAY

    stratagem_id = await _core(
        session, "Heroic Intervention", "heroic_intervention", "charge", "opponent_turn"
    )
    game, deployment_ = await _battle(client, session, tmp_path)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _place(session, a, [(20 + i * 1.5, 10) for i in range(5)])
    await _cp(session, game_id, 2)
    await _advance_to(client, game_id, 1, 2, "charge")
    response = await _use(client, game_id, stratagem_id, a, seat=1, choice=INTO_THE_FRAY)
    # (Not yet: it's the end of the opponent's Charge phase.)
    assert "no unit it can be used on now" in response.json()["detail"]
    # Advancing pauses at the end of the phase, for seat 1.
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "charge"
    response = await client.post(f"/games/{game_id}/charge/roll", json={"unit_id": d["unit_id"]})
    assert "finished charging" in response.json()["detail"]
    response = await _use(client, game_id, stratagem_id, a, seat=1, choice=INTO_THE_FRAY)
    assert response.status_code == 200, response.text
    seat_1 = next(p for p in response.json()["players"] if p["seat"] == 1)
    assert (seat_1["cp"], seat_1["stratagem_uses"][0]["cp"]) == (0, 2)
    # It charges: a roll of 12 is at most 6, Into the Fray.
    monkeypatch.setattr("app.services.in_game.charging.random.randint", lambda a_, b: 6)
    response = await client.post(f"/games/{game_id}/charge/roll", json={"unit_id": a["unit_id"]})
    assert response.status_code == 200, response.text
    [unit] = [u for u in response.json()["units"] if u["unit_id"] == a["unit_id"]]
    assert unit["roll"] == 6
    # Then the phase ends.
    assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == "fight"


async def test_counteroffensive(client: AsyncClient, session, tmp_path, monkeypatch):
    from tests.test_fighting import BLADE, _fight, _fight_state, _to_fight

    units = {1: [("A", 1, BLADE), ("B", 1, BLADE)], 2: [("D", 1, BLADE), ("E", 1, BLADE)]}
    places = {"D": [(20, 4)], "A": [(20, 6)], "E": [(40, 4)], "B": [(40, 6)]}
    stratagem_id = await _core(
        session, "Counteroffensive", "counteroffensive", "fight", "opponent_turn"
    )
    game_id, deployment_ = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    await _cp(session, game_id)
    d, e, a, b = (_unit_named(deployment_, n) for n in "DEAB")
    # Not before an enemy unit has fought.
    response = await _use(client, game_id, stratagem_id, b, seat=1)
    assert "no unit it can be used on now" in response.json()["detail"]
    assert (await _fight(client, game_id, d, a, skip=False)).status_code == 200
    response = await _use(client, game_id, stratagem_id, b, seat=1)
    assert response.status_code == 200, response.text
    # B has Fights First, and is the only unit seat 1 can pick now.
    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"]) == ("fights_first", 1)
    can = {u["name"]: u["can_fight"] for u in state["units"] if u["seat"] == 1}
    assert can == {"A": False, "B": True}


async def test_smokescreen(client: AsyncClient, session, tmp_path):
    from app.services.in_game import shooting
    from tests.test_reinforcements import _advance_to

    stratagem_id = await _core(session, "Smokescreen", "smokescreen", "shooting", "opponent_turn")
    game, deployment_ = await _battle(client, session, tmp_path)
    a = _unit_named(deployment_, "A")
    await _cp(session, game["id"])
    await _advance_to(client, game["id"], 1, 2, "shooting")
    response = await _use(client, game["id"], stratagem_id, a, seat=1)
    assert response.status_code == 200, response.text
    session.expire_all()
    game_ = await _load_game(session, game["id"])
    assert shooting.in_cover(game_, deployment.find_unit(game_, a["unit_id"]))


async def test_epic_challenge(client: AsyncClient, session, tmp_path, monkeypatch):
    from app.services.in_game import core_stratagems
    from tests.test_fighting import _to_fight

    units = {1: [("A", 1, {"melee": True})], 2: [("D", 1, {"melee": True, "keywords": ("CHARACTER",)})]}
    stratagem_id = await _core(session, "Epic Challenge", "epic_challenge", "fight", "either")
    game_id, deployment_ = await _to_fight(
        client, session, tmp_path, monkeypatch, units, {"D": [(20, 4)], "A": [(20, 6)]}
    )
    await _cp(session, game_id)
    d = _unit_named(deployment_, "D")
    model = d["models"][0]["unit_model_id"]
    response = await _use(client, game_id, stratagem_id, d, choice=model)
    assert response.status_code == 200, response.text
    session.expire_all()
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, d["unit_id"])
    assert core_stratagems.precision_models(game_, unit) == {model}
