from httpx import AsyncClient

from app.engine import features
from tests.test_acts_of_faith import _enhancement, _list_detachment, _pool, _sororitas_game
from tests.test_agent import _decision, _problems, _random_steps, _summary
from tests.test_dread import _ability

# The agent interface's Adepta Sororitas choices (see
# app/routers/agent_sororitas.py). Games from test_acts_of_faith: seat 2's
# army is Adepta Sororitas, its unit "D" ADEPTA SORORITAS with Acts of Faith,
# in seat 2's movement phase.


async def _apply(client, game_id, action):
    response = await client.post(
        f"/games/{game_id}/agent/apply",
        json={"action": {"type": action["type"], "seat": action["seat"],
                         "params": action["params"]}},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_advance_with_a_miracle_dice(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    _pool(game_id, values=[2, 6])
    decision = await _decision(client, game_id)
    rolls = [a for a in decision["actions"] if a["type"] == "roll_advance"]
    assert sorted(r["params"].get("miracle_die") or 0 for r in rolls) == [0, 6]
    result = await _apply(client, game_id, next(r for r in rolls if r["params"].get("miracle_die")))
    assert result["log"]["ok"], result["log"]
    assert _pool(game_id) == [2]


async def test_no_variants_without_miracle_dice(client: AsyncClient, session, tmp_path):
    # An empty pool (and an army that isn't Adepta Sororitas): just the roll.
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    decision = await _decision(client, game_id)
    rolls = [a for a in decision["actions"] if a["type"] == "roll_advance"]
    assert [r["params"] for r in rolls] == [{"unit_id": d["unit_id"]}]


async def test_new_action_types_count_as_other():
    # (So a trained policy's inputs keep their size.)
    for kind in ("miracle_manual", "miracle_chaplet", "miracle_psalm", "sacred_healing",
                 "condemn", "judge", "hagiomnifex"):
        assert kind not in features.ACTION_TYPES


async def test_the_manual_from_the_agent(client: AsyncClient, session, tmp_path):
    from tests.test_reinforcements import _advance_to

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    detachment = await _list_detachment(session, game_id, "Bringers of Flame")
    await _enhancement(session, d, "Manual of Saint Griselda", detachment)
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[1, 3, 5])
    decision = await _decision(client, game_id)
    [manual] = [a for a in decision["actions"] if a["type"] == "miracle_manual"]
    assert manual["params"]["values"] == [1, 3]
    result = await _apply(client, game_id, manual)
    assert result["log"]["ok"], result["log"]
    assert sorted(_pool(game_id)) == [4, 5]


async def test_random_play_through_with_sororitas(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Seat 2's D (armed, with some Miracle dice abilities) against seat 1's
    # A, at random: no action listed as legal is refused, nothing crashes.
    monkeypatch.setattr("app.services.dice.new_seed", lambda: 40)
    armed = {"weapon_range": 24, "melee": True}
    game_id, a, d = await _sororitas_game(client, session, tmp_path, d_kwargs=armed,
                                          a_kwargs={"melee": True})
    for name in ("Righteous Repugnance", "Judged for Execution", "Cherub"):
        await _ability(session, d, name)
    detachment = await _list_detachment(session, game_id, "Bringers of Flame")
    await _enhancement(session, d, "Manual of Saint Griselda", detachment)
    _pool(game_id, values=[1, 6])
    log = await _random_steps(client, game_id, 200)
    assert len(log) > 20
    assert _problems(log) == [], _summary(_problems(log))


async def test_the_defender_decides_from_the_agent(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Seat 1's A shoots D: the attack waits on seat 2 - an Act of Faith for a
    # save? - and only that decision's listed until it's made.
    from tests.test_reinforcements import _advance_to
    from tests.test_shooting import _place

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    await _advance_to(client, game_id, 1, 1, "shooting")
    _pool(game_id, values=[6])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 4)
    decision = await _decision(client, game_id)
    shot = next(
        x for x in decision["actions"]
        if x["type"] == "shoot" and x["params"]["target_unit_id"] == d["unit_id"]
    )
    result = await _apply(client, game_id, shot)
    assert result["log"]["ok"], result["log"]
    assert "waiting on seat 2" in result["log"]["result"]
    decision = result["decision"]
    assert decision["waiting_for"]["seat"] == 2
    assert {x["type"] for x in decision["actions"]} == {"attack_decision"}
    assert [x["params"]["choice"] for x in decision["actions"]] == ["miracle:6", "decline"]
    assert "attack_decision" not in features.ACTION_TYPES
    result = await _apply(client, game_id, decision["actions"][0])
    assert result["log"]["ok"], result["log"]
    assert "damage" in result["log"]["result"]
    assert _pool(game_id) == []
    assert result["decision"]["waiting_for"]["seat"] == 1
