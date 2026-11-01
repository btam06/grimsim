from httpx import AsyncClient

from tests.test_deployment import _game
from tests.test_movement import _battle

# The agent interface (see app/routers/agent.py): the decision a game is
# waiting on, its legal actions, and applying them - checked by playing
# whole stretches of games with random legal actions.


async def _decision(client, game_id):
    response = await client.get(f"/games/{game_id}/agent")
    assert response.status_code == 200, response.text
    return response.json()


async def _random_steps(client, game_id, steps):
    # Up to `steps` random legal actions; the log of them.
    for _ in range(steps):
        response = await client.post(f"/games/{game_id}/agent/random")
        if response.status_code != 200:
            break
    return (await client.get(f"/games/{game_id}/agent/log?limit=1000")).json()


def _summary(problems):
    # Each kind of problem, how often.
    import collections

    return collections.Counter((e["type"], (e["error"] or "")[:150]) for e in problems)


def _problems(log):
    # Crashes (not a refusal - an exception), and actions listed as legal
    # that were then refused.
    return [e for e in log if e["mismatch"] or (e["error"] and ":" in e["error"].split(" ")[0])]


async def test_the_decision_and_its_actions(client: AsyncClient, session, tmp_path):
    game, _ = await _battle(client, session, tmp_path)
    decision = await _decision(client, game["id"])
    assert decision["waiting_for"] == {"seat": 2, "reason": "their movement phase"}
    types = set(decision["counts"])
    assert {"advance", "move", "roll_advance"} <= types
    moves = [a for a in decision["actions"] if a["type"] == "move"]
    # A move to positions of the agent's own (no default: staying put would
    # be a 0" move)...
    assert moves[0]["placement"]["default"] is None
    assert not moves[0]["concrete"]
    # ...and towards the closest enemy unit, ready to make.
    towards = [a for a in moves if " towards " in a["label"]]
    assert towards and all(a["concrete"] for a in towards)


async def test_each_unit_moves_once_a_phase(client: AsyncClient, session, tmp_path):
    # For an agent: a unit that's moved isn't offered another move (a person
    # can still redo it).
    game, _ = await _battle(client, session, tmp_path)
    decision = await _decision(client, game["id"])
    move = next(a for a in decision["actions"] if a["concrete"] and a["type"] == "move")
    unit_id = move["params"]["unit_id"]
    response = await client.post(
        f"/games/{game['id']}/agent/apply",
        json={"action": {"type": "move", "seat": move["seat"],
                         "params": {**move["params"], "positions": move["placement"]["default"]}}},
    )
    assert response.json()["log"]["ok"], response.text
    decision = response.json()["decision"]
    assert not [
        a for a in decision["actions"]
        if a["params"].get("unit_id") == unit_id
        and a["type"] in ("move", "roll_advance", "reset_move")
    ]


async def test_applying_an_action_is_logged(client: AsyncClient, session, tmp_path):
    game, _ = await _battle(client, session, tmp_path)
    decision = await _decision(client, game["id"])
    advance = next(a for a in decision["actions"] if a["type"] == "advance")
    response = await client.post(
        f"/games/{game['id']}/agent/apply",
        json={"action": {"type": "advance", "seat": advance["seat"], "params": {}}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["log"]["ok"], body["log"]["listed"]) == (True, True)
    assert body["decision"]["state"].endswith("shooting")
    # Not a legal action now: logged as refused (not listed, so no mismatch).
    response = await client.post(
        f"/games/{game['id']}/agent/apply",
        json={"action": {"type": "roll_charge", "seat": 2, "params": {"unit_id": 1}}},
    )
    log = response.json()["log"]
    assert (log["ok"], log["listed"], log["mismatch"]) == (False, False, False)


async def test_random_play_through_the_battle(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Two armed units, starting 30" apart. (Seeded: the same game each time,
    # so a failure can be replayed.)
    monkeypatch.setattr("app.services.dice.new_seed", lambda: 40)
    armed = {"weapon_range": 24, "melee": True}
    units = {1: [("A", 5, armed)], 2: [("D", 5, armed)]}
    game, _ = await _battle(client, session, tmp_path, units=units)
    log = await _random_steps(client, game["id"], 150)
    assert len(log) > 20
    assert "shoot" in {e["type"] for e in log if e["ok"]}
    assert _problems(log) == [], _summary(_problems(log))


async def test_random_play_through_deployment(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path, declare=False)
    log = await _random_steps(client, game["id"], 60)
    assert _problems(log) == [], _summary(_problems(log))
    assert (await _decision(client, game["id"]))["state"] != game["status"]


async def test_random_play_through_a_fight(client: AsyncClient, session, tmp_path, monkeypatch):
    # Engaged units in the fight phase (piling in done): fights, consolidating
    # and the next turn, at random. (Seeded: the same game each time.)
    from tests.test_fighting import BLADE, _to_fight

    monkeypatch.setattr("app.services.dice.new_seed", lambda: 40)

    units = {1: [("A", 2, BLADE)], 2: [("D", 2, BLADE)]}
    places = {"D": [(20, 4), (21.5, 4)], "A": [(20, 6), (21.5, 6)]}
    game_id, _ = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    log = await _random_steps(client, game_id, 30)
    types = {e["type"] for e in log if e["ok"]}
    assert "fight" in types, log
    assert _problems(log) == [], _summary(_problems(log))


async def test_the_battle_rounds_required_options_come_first(
    client: AsyncClient, session, tmp_path
):
    # At the start of the round, seat 1 must choose a Doctrina Imperative
    # before anything else - though seat 2 has the first turn.
    from tests.test_battle_round import PROTECTOR, _doctrina_game

    game_id, ability_id, _ = await _doctrina_game(client, session, tmp_path)
    decision = await _decision(client, game_id)
    assert decision["waiting_for"]["seat"] == 1
    assert "advance" not in decision["counts"]
    choice = next(
        a for a in decision["actions"]
        if a["type"] == "round_start_choice" and a["params"]["option"] == PROTECTOR
    )
    response = await client.post(
        f"/games/{game_id}/agent/apply",
        json={"action": {"type": choice["type"], "seat": choice["seat"], "params": choice["params"]}},
    )
    assert response.json()["log"]["ok"]
    decision = response.json()["decision"]
    assert "advance" in decision["counts"]


async def test_teleport_homers_wait_for_their_player(client: AsyncClient, session, tmp_path):
    # Seat 1 has a Teleport Homer: once the battle's begun, the game waits for
    # them to set up its token (or be done without one) - not for "advance".
    from tests.test_teleport_homer import _homer_game

    game_id, _, _ = await _homer_game(client, session, tmp_path)
    decision = await _decision(client, game_id)
    assert decision["waiting_for"] == {"seat": 1, "reason": "setting up Teleport Homers"}
    finish = next(a for a in decision["actions"] if a["type"] == "finish_teleport_homers")
    assert finish["seat"] == 1
    response = await client.post(
        f"/games/{game_id}/agent/apply",
        json={"action": {"type": finish["type"], "seat": finish["seat"], "params": {}}},
    )
    assert response.json()["log"]["ok"]
    assert response.json()["decision"]["waiting_for"]["reason"] != "setting up Teleport Homers"


async def test_the_command_phases_required_choices_come_first(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    from tests.test_command_phase import _command_game
    from tests.test_reinforcements import _advance_to

    game_id, units = await _command_game(client, session, tmp_path, monkeypatch)
    await _advance_to(client, game_id, 1, 1, "command")
    decision = await _decision(client, game_id)
    # Canticles and the Rod must be selected before the phase can end.
    assert "advance" not in decision["counts"]
    choices = [a for a in decision["actions"] if a["type"] == "command_choice"]
    protocol = next(a for a in choices if a["params"]["ability"] == "Battle Protocols")
    response = await client.post(
        f"/games/{game_id}/agent/apply",
        json={"action": {"type": "command_choice", "seat": 1, "params": protocol["params"]}},
    )
    assert response.json()["log"]["ok"], response.text
    # One selection an ability: the protocol's made - not offered again.
    decision = response.json()["decision"]
    assert not [
        a for a in decision["actions"]
        if a["type"] == "command_choice" and a["params"]["ability"] == "Battle Protocols"
    ]
    for ability in ("Canticles of the Omnissiah", "Rod of the War Forge"):
        choice = next(
            a for a in decision["actions"]
            if a["type"] == "command_choice" and a["params"]["ability"] == ability
        )
        response = await client.post(
            f"/games/{game_id}/agent/apply",
            json={"action": {"type": "command_choice", "seat": 1, "params": choice["params"]}},
        )
        assert response.json()["log"]["ok"], response.text
        decision = response.json()["decision"]
    assert "advance" in decision["counts"]


async def test_an_emergency_disembark_is_always_ready(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Six models out of a destroyed transport: set up together (in
    # coherency) where they can be.
    from tests.test_emergency import _destroy_transport, _give
    from tests.test_reinforcements import _advance_to
    from tests.test_scoring_rules import _transport_game

    from app.services.in_game import emergency

    game_id, t, p = await _transport_game(client, session, tmp_path, passengers=6)
    await _give(session, t, "Deadly Demise 1")
    await _advance_to(client, game_id, 1, 1, "movement")
    await _destroy_transport(session, game_id, t)
    # Even if what's suggested scatters them round the wreck (every other
    # model on its far side, out of coherency).
    suggested = emergency.suggested

    def scattered(game, unit):
        found = suggested(game, unit)
        return {
            i: (40 - x, 76 - y, r) if n % 2 else (x, y, r)
            for n, (i, (x, y, r)) in enumerate(found.items())
        }

    monkeypatch.setattr(emergency, "suggested", scattered)
    decision = await _decision(client, game_id)
    [action] = [a for a in decision["actions"] if a["type"] == "emergency_disembark"]
    assert action["concrete"] and action["placement"]["default"]
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: 6)
    response = await client.post(
        f"/games/{game_id}/agent/apply",
        json={"action": {"type": "emergency_disembark", "seat": 1,
                         "params": {**action["params"],
                                    "positions": action["placement"]["default"]}}},
    )
    assert response.json()["log"]["ok"], response.json()["log"]["error"]
