from httpx import AsyncClient

from app.engine.state import GameModelDamage
from app.models import Stratagem, StratagemTiming, UnitModel, Wargear
from app.routers.games import _load_game
from app.services.in_game import casualties, charging, deployment, fight_abilities, movement, shooting
from tests.test_admech_characters import _give
from tests.test_deployment import _unit_named
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place, _shoot, _shooting_game, _to_shooting

# Necrons units' abilities in a game: Technomancer's repair, Wraith Form,
# Crimson Harvest, My Will Be Done, [ONE SHOT] and Plasmacyte. Seat 2 goes
# first; each battle starts in its movement phase.

NECRONS = {"keywords": ("NECRONS",)}


async def test_technomancer_repairs_in_the_movement_phase(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("T", 1, NECRONS), ("N", 1, NECRONS), ("F", 1, NECRONS)]}
    spots = {"A": (20, 38), "T": (20, 4), "N": (24, 4), "F": (40, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    t, n = _unit_named(deployment_, "T"), _unit_named(deployment_, "N")
    await _give(session, t, "Technomancer")
    game_ = await _load_game(session, game_id)
    n_model = n["models"][0]["unit_model_id"]
    game_.model_damage.append(GameModelDamage(unit_model_id=n_model, wounds_lost=1, destroyed=False))
    await session.commit()
    [technomancer] = (await client.get(f"/games/{game_id}/repairs")).json()
    # NECRONS models within 6": T's own and N's - not F's.
    assert n_model in [x["unit_model_id"] for x in technomancer["targets"]]
    assert _unit_named(deployment_, "F")["models"][0]["unit_model_id"] not in [
        x["unit_model_id"] for x in technomancer["targets"]
    ]
    response = await client.post(
        f"/games/{game_id}/repairs",
        json={"unit_id": t["unit_id"], "ability": "Technomancer", "unit_model_id": n_model},
    )
    assert response.status_code == 200, response.text
    game_ = await _load_game(session, game_id)
    assert casualties.damage(game_)[n_model].wounds_lost == 0
    assert (await client.get(f"/games/{game_id}/repairs")).json() == []


async def test_wraith_form(client: AsyncClient, session, tmp_path, monkeypatch):
    # W moves over A (at (20, 16)): a D6 per model, each 4+ a mortal wound to
    # A - once a phase.
    units = {1: [("A", 2, {}), ("B", 1, {})], 2: [("W", 2, {"keywords": ("NECRONS", "FLY")})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units,
                                      spots={"A": (20, 38), "B": (40, 38), "W": (20, 4)})
    game_id = game["id"]
    w, a, b = (_unit_named(deployment_, x) for x in "WAB")
    await _give(session, w, "Wraith Form")
    await _place(session, a, [(20, 16), (21.5, 16)])
    await _place(session, w, [(20, 12), (21.5, 12)])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 5)
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, w["unit_id"])
    start = {m["unit_model_id"]: (x, 12.0, 0.0) for m, x in zip(w["models"], (20, 21.5))}
    end = {m["unit_model_id"]: (x, 20.0, 0.0) for m, x in zip(w["models"], (20, 21.5))}
    assert movement.moved_over(game_, unit, start, end) == {a["unit_id"]: 2}
    movement._moved_over_mortals(game_, unit, "normal", start, end)
    a_unit = deployment.find_unit(game_, a["unit_id"])
    assert sum(casualties.wounds_remaining(game_, a_unit).values()) == 2  # 4 - 2 mortal wounds
    movement._moved_over_mortals(game_, unit, "normal", start, end)
    assert sum(casualties.wounds_remaining(game_, a_unit).values()) == 2
    b_unit = deployment.find_unit(game_, b["unit_id"])
    assert sum(casualties.wounds_remaining(game_, b_unit).values()) == 2


async def test_crimson_harvest(client: AsyncClient, session, tmp_path, monkeypatch):
    # L ends its charge within Engagement Range of A: a 6 - D3+3 (6) mortal
    # wounds, destroying A's 2 models (2 wounds each) and 2 of... all of it.
    units = {1: [("A", 3, {})], 2: [("L", 1, NECRONS)]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units,
                                      spots={"A": (20, 38), "L": (20, 4)})
    game_id = game["id"]
    lord, a = _unit_named(deployment_, "L"), _unit_named(deployment_, "A")
    await _give(session, lord, "Crimson Harvest")
    await _place(session, a, [(20, 16), (21.5, 16), (23, 16)])
    await _place(session, lord, [(20, 14.4)])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: hi)
    game_ = await _load_game(session, game_id)
    charging._charge_mortals(game_, deployment.find_unit(game_, lord["unit_id"]))
    assert casualties.wounds_remaining(game_, deployment.find_unit(game_, a["unit_id"])) == {}


async def test_my_will_be_done(client: AsyncClient, session, tmp_path):
    # Two 1CP Stratagems on seat 2's O (My Will Be Done) in a battle round -
    # in its Movement phase, then its Shooting phase: the first costs
    # nothing, the second 1CP.
    for name, phase in (("First", "movement"), ("Second", "shooting")):
        stratagem = Stratagem(name=name, cp=1, is_core=True)
        stratagem.timings = [StratagemTiming(phase=phase, turn="your_turn")]
        session.add(stratagem)
    await session.commit()
    game, deployment_ = await _battle(client, session, tmp_path, units={
        1: [("A", 1, {})], 2: [("O", 1, NECRONS)]
    }, spots={"A": (20, 38), "O": (20, 4)})
    game_id = game["id"]
    o = _unit_named(deployment_, "O")
    await _give(session, o, "My Will Be Done")
    game_ = await _load_game(session, game_id)
    player = next(p for p in game_.players if p.seat == 2)
    player.cp = 3
    ids = {s["name"]: s["id"] for s in (await client.get("/stratagems")).json()}
    for name, cp_after in (("First", 3), ("Second", 2)):
        if name == "Second":
            await _to_shooting(client, game_id)
        response = await client.post(f"/games/{game_id}/stratagems", json={
            "seat": 2, "stratagem_id": ids[name], "target_unit_id": o["unit_id"],
        })
        assert response.status_code == 200, response.text
        assert next(p["cp"] for p in response.json()["players"] if p["seat"] == 2) == cp_after


async def test_one_shot(client: AsyncClient, session, tmp_path, monkeypatch):
    # D's gun is [ONE SHOT]: fired in round 1, not again in round 2.
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 1)
    game, deployment_ = await _shooting_game(
        client, session, tmp_path, d_kwargs={"gun_abilities": (("One Shot", None),)}
    )
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _place(session, a, [(20, 22)])
    await _to_shooting(client, game_id)
    assert (await _shoot(client, game_id, d, a)).status_code == 200
    await _advance_to(client, game_id, 2, 2, "shooting")
    game_ = await _load_game(session, game_id)
    reach = shooting.reach(game_, deployment.find_unit(game_, d["unit_id"]),
                           deployment.find_unit(game_, a["unit_id"]))
    assert reach.firing == {}
    assert all(w.in_range == 0 for w in reach.weapons)


async def test_plasmacyte_once_for_each(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path, units={
        1: [("A", 1, {})], 2: [("S", 3, NECRONS)]
    }, spots={"A": (20, 38), "S": (20, 4)})
    game_id = game["id"]
    s = _unit_named(deployment_, "S")
    await _give(session, s, "Plasmacyte")
    unit_model = await session.get(UnitModel, s["models"][0]["unit_model_id"])
    await session.refresh(unit_model, ["wargear"])
    unit_model.wargear.append(Wargear(name="Plasmacyte", model_id=unit_model.model_id))
    await session.commit()
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, s["unit_id"])
    assert fight_abilities.available(game_, unit) == ["Plasmacyte"]
    assert fight_abilities.use(game_, unit, ["Plasmacyte"])
    # One Plasmacyte: used up.
    assert fight_abilities.available(game_, unit) == []


async def test_nanoscarab_reanimation_beam(client: AsyncClient, session, tmp_path, monkeypatch):
    # Seat 1's N (Reanimation Protocols) within 3" of R (the beam): at the end
    # of seat 1's Command phase it heals D3 + D3 (1s: 2) - N's two wounded
    # models each regain a wound.
    from tests.test_reanimation import _hurt, _necrons

    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 1)
    units = {1: [("N", 2, {}), ("R", 1, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units,
                                      spots={"N": (20, 38), "R": (25, 38), "D": (20, 4)})
    game_id = game["id"]
    n, r = _unit_named(deployment_, "N"), _unit_named(deployment_, "R")
    await _necrons(session, n)
    await _give(session, r, "Nanoscarab Reanimation Beam (Aura)")
    for model in n["models"]:
        await _hurt(session, game_id, model["unit_model_id"], 1)
    await _advance_to(client, game_id, 1, 1, "command")
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 200, response.text
    game_ = await _load_game(session, game_id)
    [record] = [r for r in game_.reanimations if r.unit_id == n["unit_id"]]
    assert (record.roll, record.healed) == (2, 2)


async def test_tunnelling_horrors(client: AsyncClient, session, tmp_path):
    # In seat 2's turn (round 1), seat 1 declares it for O: at the end of the
    # turn O goes into Strategic Reserves - and must arrive in seat 1's
    # Movement phase, though it's the first battle round.
    from tests.test_reinforcements import EDGE, _at, _bring_in

    units = {1: [("O", 1, {}), ("B", 1, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units,
                                      spots={"O": (20, 38), "B": (30, 38), "D": (20, 4)})
    game_id = game["id"]
    o = _unit_named(deployment_, "O")
    await _give(session, o, "Tunnelling Horrors")
    state = (await client.get(f"/games/{game_id}/turn-end-reserves")).json()
    assert [(u["name"], u["seat"]) for u in state["units"]] == [("O", 1)]
    response = await client.post(
        f"/games/{game_id}/turn-end-reserves", json={"seat": 1, "unit_id": o["unit_id"]}
    )
    assert response.status_code == 200, response.text
    await _advance_to(client, game_id, 1, 1, "movement")
    game_ = await _load_game(session, game_id)
    unit = deployment.find_unit(game_, o["unit_id"])
    assert not deployment.models_on_battlefield(game_, unit)
    reserves = (await client.get(f"/games/{game_id}/reserves")).json()
    assert [u["name"] for u in reserves["units"]] == ["O"]
    response = await client.post(f"/games/{game_id}/advance")
    assert "bring in O" in response.json()["detail"]
    response = await _bring_in(client, game_id, o, _at(o, *EDGE))
    assert response.status_code == 200, response.text
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 200
