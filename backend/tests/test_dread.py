from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.models import (
    DatasheetAbility,
    Faction,
    FactionAbility,
    GameModelDamage,
    GameModelPosition,
    GameRuleChoice,
    Model,
    UnitModel,
)
from app.routers.games import _defender_positions, _load_game
from app.services.in_game import deployment
from tests.test_deployment import _deployment, _unit_named
from tests.test_movement import _battle, _move
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place, _shoot, _to_shooting

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Models have
# Leadership 6+. Its ruin wall ("Wall L") runs from (7, 8) to (11, 8.5),
# and from (7, 8) down to (7.5, 11).


async def _model(session, unit):
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    return (
        await session.execute(
            select(Model)
            .options(selectinload(Model.abilities), selectinload(Model.faction_abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()


async def _chaos_knights_ability(session, unit, name) -> int:
    # Gives the unit's models a Chaos Knights army rule; its id.
    faction = (
        await session.execute(select(Faction).where(Faction.name == "Chaos Knights"))
    ).scalar_one_or_none() or Faction(name="Chaos Knights")
    from app.seeds.factions.chaos_knights import abilities as chaos_knights

    text = next(e[1] for e in chaos_knights.ENTRIES if e[0] == name)
    ability = FactionAbility(name=name, description=text, faction=faction)
    model = await _model(session, unit)
    model.faction_abilities.append(ability)
    await session.commit()
    return ability.id


async def _ability(session, unit, name):
    model = await _model(session, unit)
    model.abilities.append(DatasheetAbility(name=name, description=name))
    await session.commit()


async def _destroy(session, game_id, unit, count, wounds=2):
    for m in unit["models"][:count]:
        session.add(
            GameModelDamage(
                game_id=game_id, unit_model_id=m["unit_model_id"], wounds_lost=wounds,
                destroyed=True,
            )
        )
        await session.execute(
            delete(GameModelPosition).where(
                GameModelPosition.game_id == game_id,
                GameModelPosition.unit_model_id == m["unit_model_id"],
            )
        )
    await session.commit()


async def _dread(session, game_id, ability_id, *options):
    # Seat 2's Dread abilities chosen (in the first battle round).
    for option in options:
        session.add(
            GameRuleChoice(
                game_id=game_id, battle_round=1, seat=2, faction_ability_id=ability_id,
                option=option,
            )
        )
    await session.commit()


async def _rule_test(client, game_id, unit):
    response = await client.post(
        f"/games/{game_id}/battle-shock/test",
        json={"unit_id": unit["unit_id"], "reason": "A rule"},
    )
    assert response.status_code == 200, response.text
    return next(t for t in response.json()["pending"] if t["unit_id"] == unit["unit_id"])


def _dice(monkeypatch, *rolls):
    values = iter(rolls)
    monkeypatch.setattr(
        "app.services.in_game.battle_shock.random.randint", lambda a, b: next(values)
    )


# --- the target's state, in combat ---


async def test_the_targets_state_goes_to_the_calculator(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 3, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a = _unit_named(deployment_, "A")
    loaded = await _load_game(session, game_id)
    unit = deployment.find_unit(loaded, a["unit_id"])
    assert _defender_positions(loaded, unit) == []
    # 2 of 3 models left: below Starting Strength, not Below Half-strength.
    await _destroy(session, game_id, a, 1)
    loaded = await _load_game(session, game_id)
    assert _defender_positions(loaded, unit) == ["below_starting_strength"]
    # 1 of 3, and on the objective.
    await _destroy(session, game_id, a, 2)
    a = _unit_named(await _deployment(client, game_id), "A")
    survivors = {**a, "models": [m for m in a["models"] if m["position"]]}
    await _place(session, survivors, [(10, 10)])
    loaded = await _load_game(session, game_id)
    assert _defender_positions(loaded, unit) == [
        "below_starting_strength", "below_half_strength", "in_range_of_objective"
    ]


# --- Harbingers of Dread ---


async def _dread_game(client, session, tmp_path, a_count=3):
    # Seat 2's D has Harbingers of Dread; seat 1's A is within 9" of it.
    units = {1: [("A", a_count, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    ability_id = await _chaos_knights_ability(session, d, "Harbingers of Dread")
    await _place(session, a, [(20 + 1.5 * i, 14) for i in range(a_count)])
    return game_id, a, d, ability_id


async def test_deathly_terror_and_despair_worsen_leadership(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d, ability_id = await _dread_game(client, session, tmp_path)
    test = await _rule_test(client, game_id, a)
    # Deathly Terror: 6+ becomes 7+.
    assert test["leadership"] == 7
    await _dread(session, game_id, ability_id, "Despair")
    state = (await client.get(f"/games/{game_id}/battle-shock")).json()
    assert state["pending"][0]["leadership"] == 8
    # Out of range: no worse.
    await _place(session, a, [(40 + 1.5 * i, 38) for i in range(3)])
    state = (await client.get(f"/games/{game_id}/battle-shock")).json()
    assert state["pending"][0]["leadership"] == 6


async def test_dismay_adds_units_to_the_battle_shock_step(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d, ability_id = await _dread_game(client, session, tmp_path)
    await _dread(session, game_id, ability_id, "Dismay")
    # 2 of 3: below Starting Strength (but not half or below).
    await _destroy(session, game_id, a, 1)
    a = _unit_named(await _deployment(client, game_id), "A")
    await _advance_to(client, game_id, 1, 1, "command")
    [test] = (await client.get(f"/games/{game_id}/battle-shock")).json()["pending"]
    assert test["unit_name"] == "A"


async def test_delirium_costs_mortal_wounds(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d, ability_id = await _dread_game(client, session, tmp_path)
    await _dread(session, game_id, ability_id, "Delirium")
    # 1 of 3 left (the nearest D): Below Half-strength.
    await _destroy(session, game_id, {**a, "models": a["models"][::-1]}, 2)
    test = await _rule_test(client, game_id, a)
    _dice(monkeypatch, 1, 1, 2)  # failed; D3: 2
    state = (
        await client.post(
            f"/games/{game_id}/battle-shock/{test['id']}/take", json={"insane_bravery": False}
        )
    ).json()
    [taken] = state["taken"]
    assert (taken["passed"], taken["mortal_wounds"]) == (False, "Delirium: 2 mortal wounds")
    # Its last model (2 wounds) is destroyed.
    a = _unit_named(await _deployment(client, game_id), "A")
    assert a["destroyed"]


async def test_dread_abilities_last_and_can_be_rolled(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d, ability_id = await _dread_game(client, session, tmp_path)
    await _dread(session, game_id, ability_id, "Doom")
    # The start of the third battle round: Doom's taken; roll two D6.
    await _advance_to(client, game_id, 3, 2, "start_of_round")
    start = (await client.get(f"/games/{game_id}/round-start")).json()
    rule = next(
        r for p in start["players"] if p["seat"] == 2 for r in p["rules"]
        if r["name"] == "Harbingers of Dread"
    )
    assert "Doom" not in rule["options"] and "Roll two D6" in rule["options"]
    rolls = iter([2, 5])
    monkeypatch.setattr(
        "app.services.in_game.battle_round.random.randint", lambda a, b: next(rolls)
    )
    response = await client.post(
        f"/games/{game_id}/round-start/choice",
        json={"seat": 2, "faction_ability_id": ability_id, "option": "Roll two D6"},
    )
    assert response.status_code == 200, response.text
    # 2 is Doom (already active: no more effect); 5 is Delirium.
    loaded = await _load_game(session, game_id)
    from app.seeds.factions.chaos_knights import dread
    from app.services.in_game import battle_round

    assert {"Doom", "Delirium", "Deathly Terror"} <= dread.active(loaded, 2)
    # Doom still reaches the calculator in a later round.
    await _advance_to(client, game_id, 4, 2, "movement")
    loaded = await _load_game(session, game_id)
    assert "Doom" in battle_round.active_options(loaded, 2)


# --- Voices in the Code, Executioner, Super-heavy Walker ---


async def test_voices_in_the_code(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("D", 1, {})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _ability(session, d, "Voices in the Code")
    await _place(session, a, [(21.5, 4)])  # in Engagement Range of D
    await _advance_to(client, game_id, 1, 2, "fight")
    [test] = (await client.get(f"/games/{game_id}/battle-shock")).json()["pending"]
    assert (test["unit_name"], test["reason"]) == ("A", "Voices in the Code")


async def test_executioner(client: AsyncClient, session, tmp_path, monkeypatch):
    # D destroys A; seat 1's B is within 3" of A's last model.
    monkeypatch.setattr("app.services.combat.random.randint", lambda a, b: 6)
    units = {1: [("A", 1, {}), ("B", 1, {})], 2: [("D", 2, {"weapon_range": 24})]}
    spots = {"A": (20, 38), "B": (30, 38), "D": (20, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    a, b, d = (_unit_named(deployment_, n) for n in "ABD")
    from tests.test_casualties import _set_models

    await _set_models(session, a, save=7)
    await _ability(session, d, "Executioner")
    await _place(session, a, [(20, 22)])
    await _place(session, b, [(22.5, 22)])
    await _to_shooting(client, game_id)
    await _shoot(client, game_id, d, a)
    pending = (await client.get(f"/games/{game_id}/battle-shock")).json()["pending"]
    assert [(t["unit_name"], t["reason"]) for t in pending] == [("B", "Executioner")]


async def test_super_heavy_walker(client: AsyncClient, session, tmp_path, monkeypatch):
    units = {1: [("A", 1, {})], 2: [("K", 1, {})]}
    game, deployment_ = await _battle(
        client, session, tmp_path, units=units, spots={"A": (20, 38), "K": (9, 6)}
    )
    game_id = game["id"]
    k = _unit_named(deployment_, "K")
    await _chaos_knights_ability(session, k, "Super-heavy Walker")
    # Straight through the wall at y 8 - it can, and rolls a 1.
    monkeypatch.setattr("app.services.in_game.movement.random.randint", lambda a, b: 1)
    to = [{"unit_model_id": k["models"][0]["unit_model_id"], "x": 9, "y": 10.5}]
    response = await _move(client, game_id, k, "normal", to)
    assert response.status_code == 200, response.text
    state = (await client.get(f"/games/{game_id}/battle-shock")).json()
    assert [u["name"] for u in state["battle_shocked"]] == ["K"]
    assert state["taken"][0]["reason"] == "Super-heavy Walker"
