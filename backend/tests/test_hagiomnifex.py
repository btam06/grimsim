from httpx import AsyncClient

from app.models import Enhancement, Unit
from app.routers.games import _load_game
from app.seeds.factions.adepta_sororitas import hagiomnifex
from app.services.in_game import deployment, movement, shooting
from tests.test_acts_of_faith import _list_detachment
from tests.test_core_shooting import _game
from tests.test_dread import _rule_test
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place, _shoot

# Hagiomnifex (see app/seeds/factions/adepta_sororitas/hagiomnifex.py). Games
# from test_core_shooting: seat 2's D and F, seat 1's A and E, in seat 2's
# Shooting phase (seat 2 goes first). D has the upgrade.


async def _with_hagiomnifex(client, session, tmp_path, **kwargs):
    game_id, u = await _game(client, session, tmp_path, **kwargs)
    detachment = await _list_detachment(session, game_id, "Sanctified Orators")
    unit = await session.get(Unit, u["D"]["unit_id"])
    await session.refresh(unit, ["upgrade"])
    unit.upgrade = Enhancement(
        name=hagiomnifex.HAGIOMNIFEX, detachment_id=detachment.id, kind="upgrade", points=25
    )
    await session.commit()
    return game_id, u


async def _use(client, game_id, unit, ability):
    return await client.post(
        f"/games/{game_id}/hagiomnifex", json={"unit_id": unit["unit_id"], "ability": ability}
    )


async def test_used_at_the_start_of_a_phase_once_a_turn(client: AsyncClient, session, tmp_path):
    game_id, u = await _with_hagiomnifex(client, session, tmp_path)
    [state] = (await client.get(f"/games/{game_id}/hagiomnifex")).json()
    assert state["reason"] is None and state["active"] is None
    response = await _use(client, game_id, u["D"], hagiomnifex.PSALM_OF_RIGHTEOUS_SMITING)
    assert response.status_code == 200, response.text
    assert response.json()[0]["active"] == hagiomnifex.PSALM_OF_RIGHTEOUS_SMITING
    # Once a turn.
    response = await _use(client, game_id, u["D"], hagiomnifex.RITE_OF_REVELATION)
    assert response.status_code == 400
    # Next turn, the opponent's - at the start of their phase, it can again;
    # the last one's over.
    await _advance_to(client, game_id, 1, 1, "movement")
    [state] = (await client.get(f"/games/{game_id}/hagiomnifex")).json()
    assert state["reason"] is None and state["active"] is None


async def test_not_once_the_phase_has_started(client: AsyncClient, session, tmp_path):
    game_id, u = await _with_hagiomnifex(client, session, tmp_path)
    # F shoots A (moved within its 24" gun's range first): the phase has
    # started.
    await _place(session, u["A"], [(40, 20)])
    response = await _shoot(client, game_id, u["F"], u["A"])
    assert response.status_code == 200, response.text
    response = await _use(client, game_id, u["D"], hagiomnifex.PSALM_OF_RIGHTEOUS_SMITING)
    assert response.status_code == 400
    assert "start of the phase has passed" in response.json()["detail"]


async def test_rite_of_revelation_sees_hidden_models_further(
    client: AsyncClient, session, tmp_path
):
    # A (INFANTRY) hidden in the Medium ruin area; D 16.5" away (as in
    # test_condemned_units_hidden_models_are_seen_from_further).
    game_id, u = await _with_hagiomnifex(
        client, session, tmp_path, a_kwargs={"keywords": ("INFANTRY",)}
    )
    await _place(session, u["A"], [(11.5, 10.5)])
    await _place(session, u["E"], [(40, 30)])
    await _place(session, u["D"], [(11.5, 27)])
    game = await _load_game(session, game_id)
    d_, a_, f_ = (deployment.find_unit(game, u[n]["unit_id"]) for n in "DAF")
    assert not shooting.reach(game, d_, a_).visible
    response = await _use(client, game_id, u["D"], hagiomnifex.RITE_OF_REVELATION)
    assert response.status_code == 200, response.text
    assert shooting.reach(game, d_, a_).visible
    # Only while that unit's shooting.
    assert shooting.detection_range(game, a_, f_) == 15
    assert shooting.detection_range(game, a_, d_) == 21


async def test_sermon_of_intolerance_passes_battle_shock_tests(
    client: AsyncClient, session, tmp_path
):
    game_id, u = await _with_hagiomnifex(client, session, tmp_path)
    await _use(client, game_id, u["D"], hagiomnifex.SERMON_OF_INTOLERANCE)
    test = await _rule_test(client, game_id, u["D"])
    response = await client.post(
        f"/games/{game_id}/battle-shock/{test['id']}/take", json={"insane_bravery": False}
    )
    [taken] = response.json()["taken"]
    assert taken["passed"] and taken["dice"] == []


async def test_catechism_of_raging_fervour_adds_to_move(client: AsyncClient, session, tmp_path):
    game_id, u = await _with_hagiomnifex(client, session, tmp_path)
    await _advance_to(client, game_id, 2, 2, "movement")
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, u["D"]["unit_id"])
    model = unit.unit_models[0]
    assert movement.move_characteristic(game, unit, model) == 6
    await _use(client, game_id, u["D"], hagiomnifex.CATECHISM_OF_RAGING_FERVOUR)
    assert movement.move_characteristic(game, unit, model) == 7


async def test_psalm_and_chorus_in_combat(monkeypatch):
    # +1 S for the unit's attacks; -1 to wound for attacks with S above T.
    from tests.test_combat import _doctrina_combat, _weapon

    class _Game:
        hagiomnifex_uses = []
        battle_round, turn_seat, phase = 1, 2, "shooting"

    g = _Game()
    unit = type("U", (), {"id": 7})()
    g.hagiomnifex_uses = [
        type("R", (), dict(unit_id=7, battle_round=1, turn_seat=2, phase="shooting",
                           ability=hagiomnifex.PSALM_OF_RIGHTEOUS_SMITING))()
    ]
    smiting = hagiomnifex.attack_rules(g, unit)
    g.hagiomnifex_uses[0].ability = hagiomnifex.CHORUS_OF_REPUDIATION
    chorus = hagiomnifex.defence_rules(g, unit)
    # S1 vs T1 (4+) with a wound roll of 3: wounds only with +1 S (2+).
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: 3)
    weapon = _weapon(attacks="1", skill=3, strength=1, ap=-10, weapon_type="ranged")
    assert _doctrina_combat(weapon).total_damage == 0
    assert _doctrina_combat(weapon, attacker_rules=smiting).total_damage == 1
    # S2 vs T1 (2+, a 3 wounds) with -1 to wound (3+): still wounds; S2 with
    # a roll of 2 then fails.
    rolls = iter([3, 2, 1])
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: next(rolls, 1))
    weapon2 = _weapon(attacks="1", skill=3, strength=2, ap=-10, weapon_type="ranged")
    assert _doctrina_combat(weapon2, defender_rules=chorus).total_damage == 0
    rolls = iter([3, 2, 1])
    assert _doctrina_combat(weapon2).total_damage == 1
