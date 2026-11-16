from httpx import AsyncClient

from tests import live_games
from tests.test_admech_datasheets import _with
from tests.test_deployment import _unit_named
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place, _shoot, _shooting_game, _to_shooting

# A phase's start and end steps (see app/services/in_game/phase_start.py and
# phase_end.py): activated abilities "at the start of" or "at the end of" a
# phase are used in them, and the game waits for their players first. Seat 2
# (D) goes first.


async def test_the_start_step_waits_for_harbinger_of_despair(
    client: AsyncClient, session, tmp_path
):
    game, deployment_ = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _with(session, d, "Harbinger of Despair")
    await _place(session, a, [(20, 20)])
    await _to_shooting(client, game_id)
    # Seat 2's Shooting phase begins: it waits on them - D can't shoot yet.
    state = (await client.get(f"/games/{game_id}/phase-start")).json()
    assert (state["seat"], state["phase"]) == (2, "shooting")
    [harbinger] = state["activations"]
    assert harbinger["ability"] == "Harbinger of Despair" and harbinger["when"] == "start"
    assert a["unit_id"] in [t["unit_id"] for t in harbinger["targets"]]
    response = await client.get(f"/games/{game_id}/shooting/targets?unit_id={d['unit_id']}")
    assert response.status_code == 400 and "waiting for player 2" in response.text
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 400
    response = await client.post(
        f"/games/{game_id}/activations",
        json={"unit_id": d["unit_id"], "ability": "Harbinger of Despair", "target_unit_id": a["unit_id"]},
    )
    assert response.status_code == 200, response.text
    # (Once a turn: nothing left to use - the phase goes on.)
    assert (await client.get(f"/games/{game_id}/phase-start")).json()["seat"] is None
    assert (await _shoot(client, game_id, d, a)).status_code == 200


async def test_done_closes_the_start_step(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _with(session, d, "Harbinger of Despair")
    await _place(session, a, [(20, 20)])
    await _to_shooting(client, game_id)
    response = await client.post(f"/games/{game_id}/phase-start/done", json={"seat": 2})
    assert response.status_code == 200, response.text
    [harbinger] = [
        x for x in (await client.get(f"/games/{game_id}/activations")).json()
        if x["ability"] == "Harbinger of Despair"
    ]
    assert harbinger["reason"] == "it's used at the start of the phase"
    assert (await _shoot(client, game_id, d, a)).status_code == 200


async def test_a_player_with_nothing_to_use_isnt_waited_on(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    await _to_shooting(client, game_id)
    assert (await client.get(f"/games/{game_id}/phase-start")).json()["seat"] is None
    assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == "charge"


async def test_the_end_step_waits_for_lord_of_the_storm(client: AsyncClient, session, tmp_path):
    from app.services.in_game import phase_end

    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _with(session, a, "Lord of the Storm")
    await _place(session, a, [(20, 10)])
    # Seat 1's Command phase: ending it waits on them.
    await _advance_to(client, game_id, 1, 1, "command")
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "command"
    state = (await client.get(f"/games/{game_id}/phase-end")).json()
    assert (state["seat"], state["open"]) == (1, True)
    [lord] = state["activations"]
    assert lord["ability"] == "Lord of the Storm" and lord["when"] == "end"
    response = await client.post(
        f"/games/{game_id}/activations", json={"unit_id": a["unit_id"], "ability": "Lord of the Storm"}
    )
    assert response.status_code == 200, response.text
    # (Nothing else to use: the phase can end - Done ends it.)
    assert live_games.game(game_id).phase == "command"
    assert (await client.get(f"/games/{game_id}/phase-end")).json()["seat"] is None
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "movement"
    assert not phase_end.opened(live_games.game(game_id))


async def test_done_ends_the_phase(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a = _unit_named(deployment_, "A")
    await _with(session, a, "Lord of the Storm")
    await _advance_to(client, game_id, 1, 1, "command")
    assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == "command"
    response = await client.post(f"/games/{game_id}/phase-end/done", json={"seat": 1})
    assert response.status_code == 200, response.text
    assert response.json()["phase"] == "movement"


# --- Seething Hatred: one Hit or Wound roll re-rolled, its player's asked ---


async def _hatred(client, session, tmp_path, monkeypatch):
    units = {1: [("A", 1, {"weapon_range": 24})], 2: [("D", 1, {"weapon_range": 24})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _with(session, a, "Seething Hatred")
    await _place(session, a, [(20, 20)])
    await _advance_to(client, game_id, 1, 1, "shooting")
    rolls: list[int] = []
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: rolls.pop(0) if rolls else 1)

    async def attack(dice, choice=None):
        rolls[:] = dice
        if choice is None:
            return await _shoot(client, game_id, a, d)
        return await client.post(
            f"/games/{game_id}/attack-decision", json={"seat": 1, "choice": choice}
        )

    return attack


async def test_seething_hatred_is_offered_once_the_hit_rolls_are_made(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    attack = await _hatred(client, session, tmp_path, monkeypatch)
    # A 1 to hit: shown, then re-rolled (a 6), then a 6 to wound.
    dice = [1, 6, 6, 1, 1]
    pending = (await attack(dice)).json()["pending"]
    assert (pending["type"], pending["roll"], pending["seat"]) == ("reroll_dice", "hit", 1)
    assert pending["dice"] == [{"value": 1, "passed": False, "rerolled": False, "rerollable": True}]
    assert [o["id"] for o in pending["options"]] == ["one:0", "carry_on"]
    assert "Seething Hatred" in pending["options"][0]["label"]
    response = await attack(dice, "one:0")
    assert response.status_code == 200, response.text
    combat = response.json()["shot"]["combat"]
    assert combat["attack_rerolls"] == [6] and combat["hits"] == 1
    assert any("Seething Hatred" in c for c in combat["choices"])


async def test_seething_hatred_can_be_kept_for_a_wound_roll(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    attack = await _hatred(client, session, tmp_path, monkeypatch)
    # A 1 to hit, not re-rolled - a 1 to wound... nothing: it missed. A 6 to
    # hit, a 1 to wound: offered then - re-rolled to a 6.
    dice = [6, 1, 6, 1, 1]
    pending = (await attack(dice)).json()["pending"]
    assert pending["roll"] == "wound" and "Wound rolls" in pending["prompt"]
    combat = (await attack(dice, "one:0")).json()["shot"]["combat"]
    assert combat["wound_rerolls"] == [6] and combat["total_damage"] >= 1


async def test_a_program_playing_gets_the_start_steps_activations(
    client: AsyncClient, session, tmp_path
):
    game, deployment_ = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment_, "D"), _unit_named(deployment_, "A")
    await _with(session, d, "Harbinger of Despair")
    await _place(session, a, [(20, 20)])
    await _to_shooting(client, game_id)
    decision = (await client.get(f"/games/{game_id}/agent")).json()
    assert decision["waiting_for"]["seat"] == 2
    use = next(x for x in decision["actions"] if x["type"] == "activate")
    assert use["params"]["ability"] == "Harbinger of Despair"
    response = await client.post(
        f"/games/{game_id}/agent/apply",
        json={"action": {"type": "activate", "seat": 2, "params": use["params"]}},
    )
    assert response.json()["log"]["ok"], response.text
    assert (await client.get(f"/games/{game_id}/phase-start")).json()["seat"] is None


async def test_repair_auto_simulacra_heals_at_the_end_of_the_command_phase(
    client: AsyncClient, session, tmp_path
):
    from app.services.in_game import command_phase

    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a = _unit_named(deployment_, "A")
    await _with(session, a, "Repair Auto-simulacra")
    await _advance_to(client, game_id, 1, 1, "command")
    g = live_games.game(game_id)
    # Not at its start...
    assert not [h for h in command_phase.heals(g) if h.ability == "Repair Auto-simulacra"]
    assert (await client.post(f"/games/{game_id}/advance")).json()["phase"] == "movement"
    # ... at its end.
    assert [h.ability for h in command_phase.heals(live_games.game(game_id))] == [
        "Repair Auto-simulacra"
    ]


async def test_command_re_roll_is_offered_once_the_rolls_are_made(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    from app.services.in_game.core_stratagems import COMMAND_REROLL
    from tests.test_core_stratagems import _core

    await _core(session, "Command Re-roll", COMMAND_REROLL)
    units = {1: [("A", 1, {"weapon_range": 24})], 2: [("D", 1, {"weapon_range": 24})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _place(session, a, [(20, 20)])
    await _advance_to(client, game_id, 1, 1, "shooting")
    g = live_games.game(game_id)
    for p in g.players:
        p.cp = 2
    rolls: list[int] = []
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: rolls.pop(0) if rolls else 1)
    # A 1 to hit, re-rolled: a 6 - then a 6 to wound, and a 1 to save.
    dice = [1, 6, 6, 1, 1]
    rolls[:] = dice
    pending = (await _shoot(client, game_id, a, d)).json()["pending"]
    assert (pending["roll"], pending["seat"]) == ("hit", 1)
    assert [o["id"] for o in pending["options"]] == ["command_reroll:0", "carry_on"]
    rolls[:] = dice
    response = await client.post(
        f"/games/{game_id}/attack-decision", json={"seat": 1, "choice": "command_reroll:0"}
    )
    # Then the defender's offered it for their failed saving throw - no.
    pending = response.json()["shot"]["pending"]
    assert (pending["roll"], pending["seat"]) == ("save", 2)
    assert [o["id"] for o in pending["options"]] == ["command_reroll:0", "carry_on"]
    rolls[:] = dice
    response = await client.post(
        f"/games/{game_id}/attack-decision", json={"seat": 2, "choice": "carry_on"}
    )
    out = response.json()["shot"]
    assert out["pending"] is None, out["pending"]
    assert out["combat"]["attack_rerolls"] == [6]
    g = live_games.game(game_id)
    player = next(p for p in g.players if p.seat == 1)
    # (1CP, and once a phase.)
    assert player.cp == 1
    assert next(p for p in g.players if p.seat == 2).cp == 2
    assert [u.stratagem.name for u in player.stratagem_uses] == ["Command Re-roll"]
    assert "re-rolled: 6" in " ".join(out["combat"]["choices"])
