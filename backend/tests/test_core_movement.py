from httpx import AsyncClient

from app.models import DatasheetAbility
from app.routers.games import _load_game
from app.services.in_game import battle_shock, casualties, deployment, movement
from tests.test_casualties import _set_models
from tests.test_deployment import R32
from tests.test_movement import _battle, _check
from tests.test_shooting import _place
from tests.test_space_marine_units import _model_of

# The Core Rules' movement: going round enemy models (03.01, 17.01),
# Desperate Escape (09.07) and taking to the skies (21.03). Games on the test
# layout, seat 2 moving first.


async def _game(client, session, tmp_path, d_kwargs=None):
    units = {1: [("A", 1, {})], 2: [("D", 1, d_kwargs or {})]}
    game, deployment_ = await _battle(
        client, session, tmp_path, units=units, spots={"A": (20, 38), "D": (20, 4)}
    )
    u = {x["name"]: x for x in deployment_["units"]}
    # A stands in D's way; D (M10) heads 10" straight past it.
    await _place(session, u["A"], [(20, 7.6)])
    await _set_models(session, u["D"], movement=10)
    return game["id"], u


def _to(unit, x, y):
    return [{"unit_model_id": unit["models"][0]["unit_model_id"], "x": x, "y": y}]


async def test_models_go_round_enemy_models(client: AsyncClient, session, tmp_path):
    game_id, u = await _game(client, session, tmp_path)
    check = await _check(client, game_id, u["D"], "normal", _to(u["D"], 20, 14))
    assert not check["valid"]
    assert any("enemy models" in p for p in check["problems"])


async def test_vehicles_go_through_other_models(client: AsyncClient, session, tmp_path):
    game_id, u = await _game(client, session, tmp_path, {"keywords": ("VEHICLE",)})
    check = await _check(client, game_id, u["D"], "normal", _to(u["D"], 20, 14))
    assert check["valid"], check


async def test_taking_to_the_skies(client: AsyncClient, session, tmp_path):
    game_id, u = await _game(client, session, tmp_path, {"keywords": ("FLY",)})
    payload = {"unit_id": u["D"]["unit_id"], "kind": "normal",
               "positions": _to(u["D"], 20, 14), "take_to_skies": True}
    # Over A - but 2" less: 8".
    check = (await client.post(f"/games/{game_id}/movement/check", json=payload)).json()
    assert any('it can move 8"' in p for p in check["problems"])
    payload["positions"] = _to(u["D"], 20, 12)
    check = (await client.post(f"/games/{game_id}/movement/check", json=payload)).json()
    assert check["valid"], check
    # With Hover, no less.
    model = await _model_of(session, u["D"])
    model.abilities.append(DatasheetAbility(name="Hover", description="Hover"))
    await session.commit()
    payload["positions"] = _to(u["D"], 20, 14)
    check = (await client.post(f"/games/{game_id}/movement/check", json=payload)).json()
    assert check["valid"], check


async def test_battle_shocked_units_fall_back_with_a_desperate_escape(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, u = await _game(client, session, tmp_path)
    await _set_models(session, u["D"], wounds=3)
    # D engaged with A, and Battle-shocked.
    await _place(session, u["D"], [(20, 7.6 - 2 * R32 - 1)])
    game = await _load_game(session, game_id)
    d = deployment.find_unit(game, u["D"]["unit_id"])
    battle_shock.battle_shock_outright(game, d, "test", 1)
    await session.commit()
    assert movement.through(game, d, "fall_back") == "enemies"
    monkeypatch.setattr(movement.random, "randint", lambda lo, hi: 1)
    response = await client.post(
        f"/games/{game_id}/movement",
        json={"unit_id": u["D"]["unit_id"], "kind": "fall_back", "positions": _to(u["D"], 20, 1)},
    )
    assert response.status_code == 200, response.text
    session.expire_all()
    game = await _load_game(session, game_id)
    d = deployment.find_unit(game, u["D"]["unit_id"])
    # The hazard roll failed: 1 mortal wound.
    assert casualties.wounds_remaining(game, d) == {d.unit_models[0].id: 2}


def test_regaining_coherency_removes_the_stragglers():
    from app.services.in_game import coherency
    from app.services.in_game.deployment import Base

    def bases(*xs):
        return {i: Base(x, 10, 32, 32) for i, x in enumerate(xs, 1)}

    # 1-3 within 2" of each other; 4 off on its own.
    assert coherency.next_to_remove(bases(10, 11.5, 13, 20)) == 4
    assert coherency.next_to_remove(bases(10, 11.5, 13)) is None
    # A chain more than 9" long: an end goes.
    chain = bases(10, 11.5, 13, 14.5, 16, 17.5, 19, 20.5, 22)
    assert coherency.next_to_remove(chain) in (1, 9)
