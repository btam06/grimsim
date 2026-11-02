from httpx import AsyncClient

from app.routers.games import _load_game
from app.services.in_game import deployment, unit_effects
from tests.test_command_phase import _give
from tests.test_deployment import _unit_named
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place, _shoot, _shooting_game, _to_shooting

# What abilities do to units for a while (see
# app/services/in_game/unit_effects.py) - Electro-shock: the enemy unit this
# unit shoots and hits in its Shooting phase (not a MONSTER or VEHICLE) is
# shocked until the end of its next turn: -2" Move, -2 to Advance and Charge
# rolls. Seat 2's D (Electro-shock) goes first; seat 1's A is shot.


async def _shocked_game(client, session, tmp_path, monkeypatch, a_keywords=()):
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: 6)
    game, deployment_ = await _shooting_game(
        client, session, tmp_path, d=1, a=1, a_kwargs={"keywords": a_keywords}
    )
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _give(session, d, ["Electro-shock"])
    await _place(session, a, [(20, 22)])
    await _to_shooting(client, game_id)
    response = await _shoot(client, game_id, d, a)
    assert response.status_code == 200, response.text
    return game_id, d, a


async def test_electro_shock(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, d, a = await _shocked_game(client, session, tmp_path, monkeypatch)
    # Seat 1's turn: A's models move 2" less (M6: 4"), its Advance roll is 2
    # less (6: 4).
    await _advance_to(client, game_id, 1, 1, "movement")
    movement = (await client.get(f"/games/{game_id}/movement")).json()
    [unit] = [u for u in movement["units"] if u["unit_id"] == a["unit_id"]]
    assert [m["movement"] for m in unit["models"]] == [4]
    assert unit["effects"] == ['Electro-shock: -2" Move, -2 to Advance and Charge rolls']
    response = await client.post(f"/games/{game_id}/movement/advance", json={"unit_id": a["unit_id"]})
    assert response.status_code == 200, response.text
    movement = (await client.get(f"/games/{game_id}/movement")).json()
    [unit] = [u for u in movement["units"] if u["unit_id"] == a["unit_id"]]
    assert unit["advance_roll"] == 4
    # Until the end of seat 1's turn: gone in seat 2's next one.
    await _advance_to(client, game_id, 2, 2, "movement")
    game = await _load_game(session, game_id)
    assert unit_effects.active(game, deployment.find_unit(game, a["unit_id"])) == []


async def test_electro_shock_doesnt_shock_vehicles(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, d, a = await _shocked_game(
        client, session, tmp_path, monkeypatch, a_keywords=("VEHICLE",)
    )
    game = await _load_game(session, game_id)
    assert unit_effects.active(game, deployment.find_unit(game, a["unit_id"])) == []


async def _give_sm(session, unit, names):
    # Gives the unit's models (they share one Model) those Space Marines
    # datasheet abilities.
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import DatasheetAbility, Model, UnitModel
    from app.seeds.factions.space_marines import datasheet_abilities as sm

    text = {entry[0]: entry[1] for entry in sm.ENTRIES}
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    model = (
        await session.execute(
            select(Model).options(selectinload(Model.abilities)).where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    for name in names:
        model.abilities.append(DatasheetAbility(name=name, description=text[name]))
    await session.commit()


async def test_glory_of_ultramar_surges_after_losing_a_model(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Seat 1's A (2 models, one with a wound left) has Glory of Ultramar: D's
    # shot destroys that model - A's surge move (D6": a 4) starts.
    from tests import live_games

    game, deployment_ = await _shooting_game(client, session, tmp_path, d=1, a=2)
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _give_sm(session, a, ["Glory of Ultramar"])
    await _place(session, a, [(20, 22), (21.5, 22)])
    live_games.damage(game_id, a["models"][0]["unit_model_id"], wounds_lost=1)
    await _to_shooting(client, game_id)
    rolls = iter([6, 6, 1, 4])  # hit, wound, save, the surge's D6
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: next(rolls, 1))
    response = await _shoot(client, game_id, d, a)
    assert response.status_code == 200, response.text
    assert response.json()["combat"]["models_destroyed"] == 1
    surges = (await client.get(f"/games/{game_id}/surge-moves")).json()
    assert [(s["unit_id"], s["distance"]) for s in surges] == [(a["unit_id"], 4)]


async def test_shattered_defences(client: AsyncClient, session, tmp_path, monkeypatch):
    # Seat 2's S (Shattered Defences) shoots and hits seat 1's VEHICLE A: for
    # the rest of the turn, seat 2's ADEPTUS ASTARTES units' ranged attacks
    # against A have +1 AP - B's do, C's (not ADEPTUS ASTARTES) don't.
    from tests.test_movement import _battle

    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 6)
    astartes = {"weapon_range": 24, "keywords": ("ADEPTUS ASTARTES",)}
    units = {
        1: [("A", 1, {"weapon_range": 24, "keywords": ("VEHICLE",)})],
        2: [("S", 1, astartes), ("B", 1, astartes), ("C", 1, {"weapon_range": 24})],
    }
    spots = {"A": (20, 38), "S": (20, 4), "B": (26, 4), "C": (32, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    a, s, b, c = (_unit_named(deployment_, n) for n in "ASBC")
    await _give_sm(session, s, ["Shattered Defences"])
    await _place(session, a, [(20, 22)])
    await _to_shooting(client, game_id)
    response = await _shoot(client, game_id, s, a)
    assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    unit = {n: deployment.find_unit(game, u["unit_id"]) for n, u in (("A", a), ("B", b), ("C", c))}
    assert len(unit_effects.attack_rules(game, unit["B"], unit["A"])) == 1
    assert unit_effects.attack_rules(game, unit["C"], unit["A"]) == []
    # Seat 1's turn: over.
    await _advance_to(client, game_id, 1, 1, "movement")
    game = await _load_game(session, game_id)
    unit = {n: deployment.find_unit(game, u["unit_id"]) for n, u in (("A", a), ("B", b))}
    assert unit_effects.attack_rules(game, unit["B"], unit["A"]) == []
