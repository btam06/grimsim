from httpx import AsyncClient
from sqlalchemy import delete

from app.models import GameModelDamage, GameModelPosition, Stratagem, StratagemTiming
from tests.test_casualties import _set_models
from tests.test_deployment import _deployment, _unit_named
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. A (seat 1)
# and D (seat 2) have 4 models each, Leadership 6+ and OC 1. The objective
# is the Medium ruin's area (x 7-13, y 8-12).

UNITS = {1: [("A", 4, {})], 2: [("D", 4, {})]}


def _dice(monkeypatch, *rolls):
    # Battle-shock tests roll these, two at a time.
    values = iter(rolls)
    monkeypatch.setattr(
        "app.services.in_game.battle_shock.random.randint", lambda a, b: next(values)
    )


async def _insane_bravery(session):
    stratagem = Stratagem(name="Insane Bravery", cp=1, is_core=True)
    stratagem.timings = [StratagemTiming(phase="command", turn="either")]
    session.add(stratagem)
    await session.commit()


async def _destroy(session, game_id, unit, count):
    # Destroys the unit's first `count` models.
    for model in unit["models"][:count]:
        session.add(
            GameModelDamage(
                game_id=game_id,
                unit_model_id=model["unit_model_id"],
                wounds_lost=2,
                destroyed=True,
            )
        )
        await session.execute(
            delete(GameModelPosition).where(
                GameModelPosition.game_id == game_id,
                GameModelPosition.unit_model_id == model["unit_model_id"],
            )
        )
    await session.commit()


async def _battle_shock(client, game_id):
    response = await client.get(f"/games/{game_id}/battle-shock")
    assert response.status_code == 200, response.text
    return response.json()


async def _take(client, game_id, test, insane_bravery=False):
    return await client.post(
        f"/games/{game_id}/battle-shock/{test['id']}/take",
        json={"insane_bravery": insane_bravery},
    )


async def test_battle_shock_step_at_half_strength(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    a = _unit_named(deployment_, "A")
    await _destroy(session, game_id, a, 2)

    # Seat 1's Command phase: A (2 of 4 models) must test; nothing moves on
    # until it does.
    await _advance_to(client, game_id, 1, 1, "command")
    [test] = (await _battle_shock(client, game_id))["pending"]
    assert (test["unit_name"], test["reason"], test["leadership"]) == (
        "A", "battle_shock_step", 6
    )
    assert (test["starting_strength"], test["current_strength"]) == (4, 2)
    response = await client.post(f"/games/{game_id}/advance")
    assert "Battle-shock tests first" in response.json()["detail"]

    # 2 + 3 = 5: failed - Battle-shocked, and its models have 0 OC.
    _dice(monkeypatch, 2, 3, 3, 3)
    state = (await _take(client, game_id, test)).json()
    [taken] = state["taken"]
    assert (taken["dice"], taken["passed"]) == ([2, 3], False)
    assert [u["name"] for u in state["battle_shocked"]] == ["A"]
    a = _unit_named(await _deployment(client, game_id), "A")
    survivors = {**a, "models": [m for m in a["models"] if m["position"]]}
    await _place(session, survivors, [(9, 10), (11, 10)])
    deployment_ = await _deployment(client, game_id)
    assert _unit_named(deployment_, "A")["battle_shocked"]
    [objective] = deployment_["objectives"]
    assert (objective["oc"]["1"], objective["controller"]) == (0, None)

    # Its next Battle-shock step: it tests again - 3 + 3 = 6 passes.
    await _advance_to(client, game_id, 2, 1, "command")
    [test] = (await _battle_shock(client, game_id))["pending"]
    state = (await _take(client, game_id, test)).json()
    assert state["battle_shocked"] == []
    [objective] = (await _deployment(client, game_id))["objectives"]
    assert (objective["oc"]["1"], objective["controller"]) == (2, 1)


async def test_no_test_above_half_strength(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    await _destroy(session, game_id, _unit_named(deployment_, "A"), 1)
    await _advance_to(client, game_id, 1, 1, "command")
    assert (await _battle_shock(client, game_id))["pending"] == []


async def test_a_single_model_counts_its_wounds(client: AsyncClient, session, tmp_path):
    # One model of 4 wounds: at 2 wounds left, it's at half strength.
    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a = _unit_named(deployment_, "A")
    await _set_models(session, a, wounds=4)
    session.add(
        GameModelDamage(
            game_id=game_id, unit_model_id=a["models"][0]["unit_model_id"], wounds_lost=2
        )
    )
    await session.commit()
    await _advance_to(client, game_id, 1, 1, "command")
    [test] = (await _battle_shock(client, game_id))["pending"]
    assert (test["starting_strength"], test["current_strength"]) == (4, 2)


async def test_insane_bravery_once_per_battle(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    await _insane_bravery(session)
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    await _destroy(session, game_id, _unit_named(deployment_, "A"), 2)
    await _advance_to(client, game_id, 1, 1, "command")
    state = await _battle_shock(client, game_id)
    assert (state["insane_bravery_cp"], state["insane_bravery"]["1"]) == (1, None)
    players = (await client.get(f"/games/{game_id}")).json()["players"]
    cp = next(p["cp"] for p in players if p["seat"] == 1)
    state = (await _take(client, game_id, state["pending"][0], insane_bravery=True)).json()
    [taken] = state["taken"]
    assert (taken["insane_bravery"], taken["passed"], taken["dice"]) == (True, True, [])
    players = (await client.get(f"/games/{game_id}")).json()["players"]
    assert next(p["cp"] for p in players if p["seat"] == 1) == cp - 1

    # Seat 1's next Command phase: still at half strength, so it tests again
    # - but Insane Bravery is spent.
    await _advance_to(client, game_id, 2, 1, "command")
    state = await _battle_shock(client, game_id)
    assert state["insane_bravery"]["1"] == "it has already been used this battle"
    response = await _take(client, game_id, state["pending"][0], insane_bravery=True)
    assert "already been used this battle" in response.json()["detail"]


async def test_a_rule_can_make_a_unit_test(client: AsyncClient, session, tmp_path, monkeypatch):
    # E.g. a stratagem in seat 2's movement phase: D tests at -1.
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    d = _unit_named(deployment_, "D")
    response = await client.post(
        f"/games/{game_id}/battle-shock/test",
        json={"unit_id": d["unit_id"], "reason": "Molecular Erosion", "modifier": -1},
    )
    assert response.status_code == 200, response.text
    [test] = response.json()["pending"]
    assert (test["reason"], test["modifier"]) == ("Molecular Erosion", -1)
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 400

    # 3 + 3 - 1 = 5: failed.
    _dice(monkeypatch, 3, 3)
    state = (await _take(client, game_id, test)).json()
    assert [u["name"] for u in state["battle_shocked"]] == ["D"]
    # Already Battle-shocked: no more tests from rules.
    response = await client.post(
        f"/games/{game_id}/battle-shock/test",
        json={"unit_id": d["unit_id"], "reason": "Molecular Erosion"},
    )
    assert "already Battle-shocked" in response.json()["detail"]
