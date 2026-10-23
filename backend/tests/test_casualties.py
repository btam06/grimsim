from httpx import AsyncClient
from sqlalchemy import select

from app.models import GameModelDamage, GameModelPosition, Model, Unit, UnitModel
from tests.test_deployment import _deployment, _unit_named
from tests.test_movement import _battle, _move, _shifted
from tests.test_shooting import _place, _shoot, _shooting, _to_shooting

# Every die rolls a 6 and targets save on a 7+: every attack hits, wounds and
# gets through, for its 1 damage. The defender (seat 2) shoots first; each
# of its models has a 24" gun with 1 attack.


async def _set_models(session, unit, **fields):
    # Sets the unit's models' characteristics (they share one Model).
    unit_model = (
        await session.execute(
            select(UnitModel).where(UnitModel.id == unit["models"][0]["unit_model_id"])
        )
    ).scalar_one()
    model = await session.get(Model, unit_model.model_id)
    for name, value in fields.items():
        setattr(model, name, value)
    await session.commit()


async def _game(client, session, tmp_path, monkeypatch, units, wounds=1):
    # In the defender's movement phase; the attacker's models have `wounds`
    # and no save.
    monkeypatch.setattr("app.services.combat.random.randint", lambda a, b: 6)
    spots = {"A": (20, 38), "D": (20, 4), "E": (32, 4)}
    game, deployment = await _battle(client, session, tmp_path, units=units, spots=spots)
    a = _unit_named(deployment, "A")
    await _set_models(session, a, wounds=wounds, save=7)
    await _place(session, a, [(20 + i * 1.5, 22) for i in range(len(a["models"]))])
    return game, await _deployment(client, game["id"])


def _gun(count):
    return (count, {"weapon_range": 24})


async def test_shooting_destroys_models(client: AsyncClient, session, tmp_path, monkeypatch):
    units = {1: [("A", 2, {})], 2: [("D", *_gun(3))]}
    game, deployment = await _game(client, session, tmp_path, monkeypatch, units)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _to_shooting(client, game_id)

    body = (await _shoot(client, game_id, d, a)).json()
    # 3 attacks at 2 one-wound models: both destroyed (the third is wasted).
    assert body["combat"]["models_destroyed"] == 2
    assert sorted(body["destroyed_unit_model_ids"]) == sorted(
        m["unit_model_id"] for m in a["models"]
    )

    a = _unit_named(await _deployment(client, game_id), "A")
    assert a["destroyed"]
    assert all(m["destroyed"] and m["position"] is None for m in a["models"])
    assert all(m["wounds_remaining"] == 0 for m in a["models"])
    # Only in this game: the unit's still in its list.
    unit = await session.get(Unit, a["unit_id"])
    await session.refresh(unit, ["unit_models"])
    assert len(unit.unit_models) == 2


async def test_wounds_carry_over_between_shots(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    units = {1: [("A", 1, {})], 2: [("D", *_gun(2)), ("E", *_gun(1))]}
    game, deployment = await _game(client, session, tmp_path, monkeypatch, units, wounds=3)
    game_id = game["id"]
    d, e, a = (_unit_named(deployment, n) for n in ("D", "E", "A"))
    await _to_shooting(client, game_id)

    body = (await _shoot(client, game_id, d, a)).json()
    assert body["destroyed_unit_model_ids"] == []
    [model] = _unit_named(await _deployment(client, game_id), "A")["models"]
    assert (model["wounds"], model["wounds_remaining"], model["destroyed"]) == (3, 1, False)

    body = (await _shoot(client, game_id, e, a)).json()
    assert body["combat"]["models_destroyed"] == 1
    [model] = _unit_named(await _deployment(client, game_id), "A")["models"]
    assert (model["wounds_remaining"], model["destroyed"]) == (0, True)


async def test_wounded_model_is_attacked_first(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    units = {1: [("A", 2, {})], 2: [("D", *_gun(1))]}
    game, deployment = await _game(client, session, tmp_path, monkeypatch, units, wounds=2)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    second = a["models"][1]["unit_model_id"]
    session.add(GameModelDamage(game_id=game_id, unit_model_id=second, wounds_lost=1))
    await session.commit()
    await _to_shooting(client, game_id)

    body = (await _shoot(client, game_id, d, a)).json()
    assert body["destroyed_unit_model_ids"] == [second]
    first, second_model = _unit_named(await _deployment(client, game_id), "A")["models"]
    assert (first["wounds_remaining"], first["destroyed"]) == (2, False)
    assert second_model["destroyed"]


async def _destroy(session, game_id, unit_model_id, wounds=1):
    session.add(
        GameModelDamage(
            game_id=game_id, unit_model_id=unit_model_id, wounds_lost=wounds, destroyed=True
        )
    )
    position = (
        await session.execute(
            select(GameModelPosition).where(GameModelPosition.unit_model_id == unit_model_id)
        )
    ).scalar_one()
    await session.delete(position)
    await session.commit()


async def test_destroyed_models_are_left_out_of_moves(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    units = {1: [("A", 1, {})], 2: [("D", *_gun(3))]}
    game, deployment = await _game(client, session, tmp_path, monkeypatch, units)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    await _destroy(session, game_id, d["models"][0]["unit_model_id"])

    # Moving it: its destroyed model can't be placed, and isn't needed for
    # coherency.
    response = await _move(client, game_id, d, "normal", _shifted(d, dy=1))
    assert response.status_code == 400
    assert "every model" in response.json()["detail"]
    alive = _shifted(d, dy=1)[1:]
    assert (await _move(client, game_id, d, "normal", alive)).status_code == 200


async def test_a_unit_with_every_model_destroyed_is_gone(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    units = {1: [("A", 1, {})], 2: [("D", *_gun(1)), ("E", *_gun(1))]}
    game, deployment = await _game(client, session, tmp_path, monkeypatch, units)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    await _destroy(session, game_id, d["models"][0]["unit_model_id"])

    movement = (await client.get(f"/games/{game_id}/movement")).json()
    assert [u["name"] for u in movement["units"]] == ["E"]
    await _to_shooting(client, game_id)
    assert [u["name"] for u in (await _shooting(client, game_id))["units"]] == ["E"]
    assert _unit_named(await _deployment(client, game_id), "D")["destroyed"]


async def test_destroyed_models_cant_be_targeted(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    units = {1: [("A", 2, {})], 2: [("D", *_gun(2))]}
    game, deployment = await _game(client, session, tmp_path, monkeypatch, units)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _destroy(session, game_id, a["models"][0]["unit_model_id"])
    await _to_shooting(client, game_id)

    body = (await _shoot(client, game_id, d, a)).json()
    # Only the one left is attacked.
    assert body["combat"]["models_destroyed"] == 1
    assert body["destroyed_unit_model_ids"] == [a["models"][1]["unit_model_id"]]
