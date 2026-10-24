from httpx import AsyncClient

from tests.test_deployment import R32, _deployment, _unit_named
from tests.test_movement import _battle, _shifted
from tests.test_shooting import _place

# Games on the test layout, in the defender's (seat 2's) turn: it piles in
# first. D's first model is at (20, 4); A's models stand `gap` inches from it,
# base to base, straight down the board. 32mm bases; Engagement Range is 2".


async def _fight_game(client, session, tmp_path, d=1, a=1, gap=1.5):
    units = {1: [("A", a, {})], 2: [("D", d, {})]}
    game, deployment = await _battle(client, session, tmp_path, units=units)
    a_unit = _unit_named(deployment, "A")
    await _place(session, a_unit, [(20 + i * 1.5, 4 + 2 * R32 + gap) for i in range(a)])
    game_id = game["id"]
    for phase in ("shooting", "charge", "fight"):
        game = (await client.post(f"/games/{game_id}/advance")).json()
        assert game["phase"] == phase
    deployment = await _deployment(client, game_id)
    return game, _unit_named(deployment, "D"), _unit_named(deployment, "A")


async def _pile_in_state(client, game_id):
    return (await client.get(f"/games/{game_id}/pile-in")).json()


async def _check(client, game_id, unit, positions):
    response = await client.post(
        f"/games/{game_id}/pile-in/check",
        json={"unit_id": unit["unit_id"], "positions": positions},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _pile_in(client, game_id, unit, positions):
    return await client.post(
        f"/games/{game_id}/pile-in", json={"unit_id": unit["unit_id"], "positions": positions}
    )


async def _done(client, game_id, seat):
    return await client.post(f"/games/{game_id}/pile-in/done", json={"seat": seat})


async def test_pile_in_starts_the_fight_phase(client: AsyncClient, session, tmp_path):
    game, d, a = await _fight_game(client, session, tmp_path)
    # The player whose turn it is piles in first.
    assert game["piling_in_seat"] == 2
    state = await _pile_in_state(client, game["id"])
    [unit] = state["units"]
    assert (state["seat"], unit["name"], unit["engaged"], unit["can_pile_in"]) == (
        2, "D", True, True
    )
    assert unit["locked_unit_model_ids"] == []


async def test_no_pile_in_with_nothing_engaged(client: AsyncClient, session, tmp_path):
    # Nobody's within Engagement Range: piling in is skipped altogether.
    game, d, a = await _fight_game(client, session, tmp_path, gap=5)
    assert game["piling_in_seat"] is None
    assert (await _pile_in_state(client, game["id"])) == {"seat": None, "units": []}
    assert (await _fight_state(client, game["id"]))["step"] != "pile_in"
    response = await _pile_in(client, game["id"], d, _shifted(d, dy=1))
    assert response.status_code == 400


async def test_only_engaged_units_pile_in(client: AsyncClient, session, tmp_path):
    # D (engaged) can; E (nowhere near) can't.
    units = {1: [("A", 1, {})], 2: [("D", 1, {}), ("E", 1, {})]}
    game, deployment = await _battle(
        client, session, tmp_path, units=units,
        spots={"A": (20, 38), "D": (20, 4), "E": (40, 4)},
    )
    a = _unit_named(deployment, "A")
    await _place(session, a, [(20, 4 + 2 * R32 + 1.5)])
    for _ in ("shooting", "charge", "fight"):
        await client.post(f"/games/{game['id']}/advance")
    state = await _pile_in_state(client, game["id"])
    units = {u["name"]: (u["engaged"], u["can_pile_in"]) for u in state["units"]}
    assert units == {"D": (True, True), "E": (False, False)}


async def test_pile_in(client: AsyncClient, session, tmp_path):
    game, d, a = await _fight_game(client, session, tmp_path)
    game_id = game["id"]
    # 1" closer: fine.
    assert (await _check(client, game_id, d, _shifted(d, dy=1)))["valid"]
    response = await _pile_in(client, game_id, d, _shifted(d, dy=1))
    assert response.status_code == 200, response.text
    model = _unit_named(await _deployment(client, game_id), "D")["models"][0]
    assert model["position"]["y"] == d["models"][0]["position"]["y"] + 1
    # D was its only unit to pile in: on to the other player.
    state = await _pile_in_state(client, game_id)
    assert (state["seat"], [u["name"] for u in state["units"]]) == (1, ["A"])


async def test_pile_in_limits(client: AsyncClient, session, tmp_path):
    game, d, a = await _fight_game(client, session, tmp_path, gap=1.8)
    game_id = game["id"]
    # Away from the enemy.
    check = await _check(client, game_id, d, _shifted(d, dx=-0.5, dy=-0.5))
    assert "D must end closer to the nearest enemy model" in check["problems"]
    # More than 3" (sideways, round A, still closer).
    check = await _check(client, game_id, d, _shifted(d, dx=3.2, dy=1.7))
    assert 'D would move 3.6" (it can move 3")' in check["problems"]
    # Not moving at all is fine.
    assert (await _check(client, game_id, d, _shifted(d)))["valid"]


async def test_models_in_base_contact_cant_move(client: AsyncClient, session, tmp_path):
    # D's first model touches A's one model; its second (1.5" along) doesn't.
    game, d, a = await _fight_game(client, session, tmp_path, d=2, a=1, gap=0)
    game_id = game["id"]
    [unit] = (await _pile_in_state(client, game_id))["units"]
    assert unit["locked_unit_model_ids"] == [d["models"][0]["unit_model_id"]]
    check = await _check(client, game_id, d, _shifted(d, dx=-0.3, only={0}))
    assert check["problems"] == ["D is in base contact with an enemy model: it can't move"]


async def test_players_take_turns_to_pile_in(client: AsyncClient, session, tmp_path):
    game, d, a = await _fight_game(client, session, tmp_path)
    game_id = game["id"]
    # Not seat 1's turn yet.
    response = await _pile_in(client, game_id, a, _shifted(a, dy=-0.5))
    assert response.status_code == 400
    assert "turn to pile in" in response.json()["detail"]
    assert (await _done(client, game_id, 1)).status_code == 400

    game = (await _done(client, game_id, 2)).json()
    assert game["piling_in_seat"] == 1
    [unit] = (await _pile_in_state(client, game_id))["units"]
    assert (unit["name"], unit["can_pile_in"]) == ("A", True)
    # A was its only unit to pile in: piling in's over, no "done" needed.
    game = (await _pile_in(client, game_id, a, _shifted(a, dy=-0.5))).json()
    assert game["piling_in_seat"] is None
    assert (await _pile_in_state(client, game_id)) == {"seat": None, "units": []}


# --- fighting ---
#
# Every die rolls a 6 and models save on a 7+ (none), so every melee attack
# hits, wounds and does its 1 damage; models have 2 wounds. Seat 2 (D, E) is
# the player whose turn it is; seat 1 (A, B) is defending.

BLADE = {"melee": True}
FF = {"melee": True, "fights_first": True}


async def _to_fight(client, session, tmp_path, monkeypatch, units, places):
    # Every unit in `units` ({seat: [(name, count, kwargs)]}) set where `places`
    # says ({name: [(x, y)]}), in the fight phase, both players done piling in.
    from tests.test_casualties import _set_models

    monkeypatch.setattr("app.services.combat.random.randint", lambda a, b: 6)
    spots = {name: (10 + 8 * i, 4 if seat == 2 else 38)
             for seat, specs in units.items() for i, (name, _, _) in enumerate(specs)}
    game, deployment = await _battle(client, session, tmp_path, units=units, spots=spots)
    for name, xy in places.items():
        unit = _unit_named(deployment, name)
        await _place(session, unit, xy)
        await _set_models(session, unit, wounds=2, save=7)
    game_id = game["id"]
    for phase in ("shooting", "charge", "fight"):
        game = (await client.post(f"/games/{game_id}/advance")).json()
    for seat in (2, 1):
        game = (await _done(client, game_id, seat)).json()
    assert game["piling_in_seat"] is None
    return game_id, await _deployment(client, game_id)


async def _fight_state(client, game_id):
    return (await client.get(f"/games/{game_id}/fight")).json()


async def _fight(client, game_id, unit, target, weapon_ids=None, skip=True):
    # The unit fights the target - then doesn't consolidate, unless `skip` is
    # False (it's left to consolidate).
    if weapon_ids is None:
        response = await client.get(f"/games/{game_id}/fight/targets?unit_id={unit['unit_id']}")
        assert response.status_code == 200, response.text
        [entry] = [t for t in response.json() if t["unit_id"] == target["unit_id"]]
        weapon_ids = [w["id"] for w in entry["weapons"] if w["default"]]
    response = await client.post(
        f"/games/{game_id}/fight",
        json={"unit_id": unit["unit_id"], "target_unit_id": target["unit_id"],
              "weapon_ids": weapon_ids},
    )
    if skip and response.status_code == 200:
        state = (await client.get(f"/games/{game_id}/fight")).json()
        if state["step"] == "consolidate":
            skipped = await client.post(
                f"/games/{game_id}/fight/consolidate/skip", json={"unit_id": unit["unit_id"]}
            )
            assert skipped.status_code == 200, skipped.text
    return response


def _row_at(x, y, count):
    return [(x + i * 1.5, y) for i in range(count)]


async def test_cant_fight_while_piling_in(client: AsyncClient, session, tmp_path):
    game, d, a = await _fight_game(client, session, tmp_path)
    state = await _fight_state(client, game["id"])
    assert state["step"] == "pile_in"
    response = await _fight(client, game["id"], d, a, weapon_ids=[1])
    assert "piling in" in response.json()["detail"]


async def test_units_fight_in_turn(client: AsyncClient, session, tmp_path, monkeypatch):
    # No Fights First: the player whose turn it is picks first, then the other.
    units = {1: [("A", 1, BLADE)], 2: [("D", 1, BLADE)]}
    game_id, deployment = await _to_fight(
        client, session, tmp_path, monkeypatch, units, {"D": [(20, 4)], "A": [(20, 6)]}
    )
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"]) == ("remaining", 2)
    # Not A's turn yet.
    response = await _fight(client, game_id, a, d, weapon_ids=[1])
    assert "other player's turn" in response.json()["detail"]

    body = (await _fight(client, game_id, d, a)).json()
    assert (body["combat"]["total_damage"], body["charged"]) == (1, False)
    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"]) == ("remaining", 1)
    assert (await _fight(client, game_id, a, d)).status_code == 200
    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"]) == ("done", None)
    assert [(f["unit_name"], f["target_name"]) for f in state["fights"]] == [("D", "A"), ("A", "D")]


async def test_fights_first_then_the_defender_picks(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # The active player has two Fights First units and the defender none:
    # both fight first, one after the other; then the defender picks first.
    units = {1: [("A", 1, BLADE), ("B", 1, BLADE)], 2: [("D", 1, FF), ("E", 1, FF)]}
    places = {"D": [(20, 4)], "A": [(20, 6)], "E": [(40, 4)], "B": [(40, 6)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, e, a, b = (_unit_named(deployment, n) for n in "DEAB")

    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"]) == ("fights_first", 2)
    ff = {u["name"]: u["fights_first"] for u in state["units"]}
    assert ff == {"D": True, "E": True, "A": False, "B": False}
    # A has to wait for the Fights First units.
    assert "Fights First" in [u for u in state["units"] if u["name"] == "A"][0]["reason"]

    assert (await _fight(client, game_id, d, a)).status_code == 200
    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"]) == ("fights_first", 2)
    assert (await _fight(client, game_id, e, b)).status_code == 200
    # The active player picked last: the defender picks first now.
    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"]) == ("remaining", 1)
    assert (await _fight(client, game_id, a, d)).status_code == 200
    assert (await _fight(client, game_id, b, e)).status_code == 200
    state = await _fight_state(client, game_id)
    assert state["step"] == "done"
    assert [f["unit_name"] for f in state["fights"]] == ["D", "E", "A", "B"]


async def test_fights_first_alternates(client: AsyncClient, session, tmp_path, monkeypatch):
    units = {1: [("A", 1, FF)], 2: [("D", 1, FF), ("E", 1, FF)]}
    places = {"D": [(20, 4)], "A": [(20, 6)], "E": [(21.5, 7.5)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, e, a = (_unit_named(deployment, n) for n in "DEA")
    seats = []
    for unit, target in ((d, a), (a, d), (e, a)):
        seats.append((await _fight_state(client, game_id))["seat"])
        assert (await _fight(client, game_id, unit, target)).status_code == 200
    assert seats == [2, 1, 2]


async def test_only_models_within_engagement_range_fight(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D's three models in a row 1.5" apart; only the first two are within 2"
    # of A.
    units = {1: [("A", 1, BLADE)], 2: [("D", 3, BLADE)]}
    places = {"D": _row_at(20, 4, 3), "A": [(20.5, 4 + 2 * R32 + 1)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    targets = (await client.get(f"/games/{game_id}/fight/targets?unit_id={d['unit_id']}")).json()
    [blade] = targets[0]["weapons"]
    assert (blade["carried_by"], blade["in_range"], blade["default"]) == (3, 2, True)
    body = (await _fight(client, game_id, d, a)).json()
    assert len(body["combat"]["attack_rolls"]) == 2
    # Two 1-damage attacks on A's 2-wound model: destroyed.
    assert body["destroyed_unit_model_ids"] == [a["models"][0]["unit_model_id"]]


async def test_destroyed_units_dont_fight_back(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    units = {1: [("A", 1, BLADE)], 2: [("D", 2, BLADE)]}
    places = {"D": _row_at(20, 4, 2), "A": [(20.75, 4 + 2 * R32 + 0.5)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    assert (await _fight(client, game_id, d, a)).json()["combat"]["models_destroyed"] == 1
    # A's gone: nothing's left to fight.
    assert (await _fight_state(client, game_id))["step"] == "done"


async def test_a_charging_unit_fights_first(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    monkeypatch.setattr("app.services.in_game.charging.random.randint", lambda a, b: 4)
    monkeypatch.setattr("app.services.combat.random.randint", lambda a, b: 6)
    units = {1: [("A", 1, BLADE)], 2: [("D", 1, BLADE)]}
    game, deployment = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, a, [(20, 4 + 2 * R32 + 4)])
    for _ in ("shooting", "charge"):
        await client.post(f"/games/{game_id}/advance")
    await client.post(f"/games/{game_id}/charge/roll", json={"unit_id": d["unit_id"]})
    response = await client.post(
        f"/games/{game_id}/charge",
        json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"],
              "positions": _shifted(d, dy=3)},
    )
    assert response.status_code == 200, response.text
    await client.post(f"/games/{game_id}/advance")
    for seat in (2, 1):
        await _done(client, game_id, seat)

    state = await _fight_state(client, game_id)
    unit = next(u for u in state["units"] if u["name"] == "D")
    assert (unit["fights_first"], unit["charged"]) == (True, True)
    assert (state["step"], state["seat"]) == ("fights_first", 2)
    d = _unit_named(await _deployment(client, game_id), "D")
    body = (await _fight(client, game_id, d, a)).json()
    assert (body["charged"], body["fights_first"]) == (True, True)


# --- consolidating ---


async def _consolidate_state(client, game_id):
    return (await client.get(f"/games/{game_id}/fight")).json()


async def _check_consolidation(client, game_id, unit, positions):
    response = await client.post(
        f"/games/{game_id}/fight/consolidate/check",
        json={"unit_id": unit["unit_id"], "positions": positions},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_unit_consolidates_after_fighting(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    units = {1: [("A", 1, BLADE)], 2: [("D", 1, BLADE)]}
    game_id, deployment = await _to_fight(
        client, session, tmp_path, monkeypatch, units, {"D": [(20, 4)], "A": [(20, 7)]}
    )
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    assert (await _fight(client, game_id, d, a, skip=False)).status_code == 200
    state = await _consolidate_state(client, game_id)
    assert (state["step"], state["seat"]) == ("consolidate", 2)
    assert state["consolidating"] == {
        "unit_id": d["unit_id"], "unit_name": "D", "target_name": "A", "target_destroyed": False
    }
    # A has to wait.
    assert "consolidate" in [u for u in state["units"] if u["name"] == "A"][0]["reason"]

    # Towards A (still there), up to 3".
    d = _unit_named(await _deployment(client, game_id), "D")
    assert (await _check_consolidation(client, game_id, d, _shifted(d, dy=0.5)))["valid"]
    check = await _check_consolidation(client, game_id, d, _shifted(d, dx=0.5, dy=-0.5))
    assert "D must end closer to A" in check["problems"]
    response = await client.post(
        f"/games/{game_id}/fight/consolidate",
        json={"unit_id": d["unit_id"], "positions": _shifted(d, dy=0.5)},
    )
    assert response.status_code == 200, response.text
    moved = _unit_named(await _deployment(client, game_id), "D")["models"][0]
    assert moved["position"]["y"] == 4.5
    # Then A can fight.
    state = await _consolidate_state(client, game_id)
    assert (state["step"], state["seat"]) == ("remaining", 1)


async def test_consolidating_into_another_unit_lets_it_fight(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D destroys A, then consolidates 2" into Engagement Range of B - which
    # hadn't been in a fight, and now gets to fight.
    units = {1: [("A", 1, BLADE), ("B", 1, BLADE)], 2: [("D", 2, BLADE)]}
    places = {"D": _row_at(20, 4, 2), "A": [(20.75, 4 + 2 * R32 + 0.5)], "B": [(26, 4)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    state = await _consolidate_state(client, game_id)
    assert [u["name"] for u in state["units"] if u["can_fight"]] == ["D"]
    body = (await _fight(client, game_id, d, a, skip=False)).json()
    assert body["combat"]["models_destroyed"] == 1
    state = await _consolidate_state(client, game_id)
    assert state["consolidating"]["target_destroyed"]

    d = _unit_named(await _deployment(client, game_id), "D")
    # Nowhere near anything else: it has to end engaged.
    check = await _check_consolidation(client, game_id, d, _shifted(d, dx=-1))
    assert "The unit must end within Engagement Range of an enemy unit" in check["problems"]
    assert "D must end closer to the nearest enemy model (x2)" in check["problems"]
    # 2" towards B: its second model ends 1.24" from it.
    positions = _shifted(d, dx=2)
    assert (await _check_consolidation(client, game_id, d, positions))["valid"]
    response = await client.post(
        f"/games/{game_id}/fight/consolidate",
        json={"unit_id": d["unit_id"], "positions": positions},
    )
    assert response.status_code == 200, response.text

    state = await _consolidate_state(client, game_id)
    assert (state["step"], state["seat"]) == ("remaining", 1)
    b_unit = [u for u in state["units"] if u["name"] == "B"][0]
    assert b_unit["can_fight"]


async def test_consolidation_can_be_skipped(client: AsyncClient, session, tmp_path, monkeypatch):
    units = {1: [("A", 1, BLADE)], 2: [("D", 1, BLADE)]}
    game_id, deployment = await _to_fight(
        client, session, tmp_path, monkeypatch, units, {"D": [(20, 4)], "A": [(20, 7)]}
    )
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _fight(client, game_id, d, a, skip=False)
    # Only the unit that just fought.
    response = await client.post(
        f"/games/{game_id}/fight/consolidate/skip", json={"unit_id": a["unit_id"]}
    )
    assert response.status_code == 400
    response = await client.post(
        f"/games/{game_id}/fight/consolidate/skip", json={"unit_id": d["unit_id"]}
    )
    assert response.status_code == 200
    assert (await _consolidate_state(client, game_id))["step"] == "remaining"


async def test_consolidating_onto_an_objective(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # The test layout's objective is the Medium ruin's area (x 7-13, y 8-12).
    # D destroys A, with no other enemy near: it can consolidate onto the
    # objective instead.
    units = {1: [("A", 1, BLADE)], 2: [("D", 1, BLADE)]}
    places = {"D": [(15, 6)], "A": [(15, 6 + 2 * R32 + 0.5)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    # A has 1 wound: D's one attack destroys it.
    from tests.test_casualties import _set_models

    await _set_models(session, a, wounds=1)
    body = (await _fight(client, game_id, d, a, skip=False)).json()
    assert body["destroyed_unit_model_ids"] == [a["models"][0]["unit_model_id"]]

    d = _unit_named(await _deployment(client, game_id), "D")
    # Away from it: neither engaged nor on an objective.
    check = await _check_consolidation(client, game_id, d, _shifted(d, dx=1))
    assert "No model ends within Engagement Range" not in " ".join(check["problems"])
    assert "(Or it can end on an objective, each model that moves closer to one)" in check[
        "problems"
    ]
    # Onto the ruin: its base reaches over x 13.
    positions = [{"unit_model_id": d["models"][0]["unit_model_id"], "x": 13.5, "y": 8.5}]
    check = await _check_consolidation(client, game_id, d, positions)
    assert check["valid"], check
    response = await client.post(
        f"/games/{game_id}/fight/consolidate",
        json={"unit_id": d["unit_id"], "positions": positions},
    )
    assert response.status_code == 200, response.text


async def test_no_consolidation_with_nothing_to_consolidate_to(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D destroys A, far from any other enemy and from the objective (the
    # Medium ruin, x 7-13): consolidating is skipped.
    from tests.test_casualties import _set_models

    units = {1: [("A", 1, BLADE)], 2: [("D", 1, BLADE)]}
    places = {"D": [(40, 4)], "A": [(40, 4 + 2 * R32 + 0.5)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _set_models(session, a, wounds=1)
    body = (await _fight(client, game_id, d, a, skip=False)).json()
    assert body["destroyed_unit_model_ids"] == [a["models"][0]["unit_model_id"]]
    state = await _fight_state(client, game_id)
    assert (state["step"], state["consolidating"]) == ("done", None)
