from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import UnitModel, Weapon, WeaponAbility
from tests.test_deployment import R32, _deployment, _unit_named
from tests.test_fighting import BLADE, _done, _fight_state, _row_at, _to_fight
from tests.test_movement import _battle, _shifted
from tests.test_shooting import _place

# The core rules' Fight phase (12): who piles in, who's eligible to fight,
# overrun fights, passing, the weapons each model fights with, and splitting
# melee attacks between targets. Seat 2 (D) is the player whose turn it is.


async def _add_weapon(session, unit, name, attacks="1", abilities=()):
    # Gives every model in the unit another melee weapon.
    unit_models = (
        await session.execute(
            select(UnitModel)
            .options(selectinload(UnitModel.weapons))
            .where(UnitModel.id.in_([m["unit_model_id"] for m in unit["models"]]))
        )
    ).scalars().all()
    weapon = Weapon(
        name=name, range=None, attacks=attacks, skill=2, strength=4, ap=0, damage="1",
        weapon_type="melee", model_id=unit_models[0].model_id,
        abilities=[WeaponAbility(name=a) for a in abilities],
    )
    for unit_model in unit_models:
        unit_model.weapons.append(weapon)
    await session.commit()
    return weapon.id


async def _charged_game(client, session, tmp_path, monkeypatch, then_at):
    # D charges A (8" roll), then A is moved `then_at` inches (base to base)
    # in front of D's model - as if something moved it away.
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
    await _place(session, a, [(20, 7 + 2 * R32 + then_at)])
    await client.post(f"/games/{game_id}/advance")
    deployment = await _deployment(client, game_id)
    return game_id, _unit_named(deployment, "D"), _unit_named(deployment, "A")


async def test_a_unit_that_charged_piles_in_though_unengaged(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, d, a = await _charged_game(client, session, tmp_path, monkeypatch, then_at=4)
    state = (await client.get(f"/games/{game_id}/pile-in")).json()
    assert (state["seat"], [(u["name"], u["engaged"]) for u in state["units"]]) == (
        2, [("D", False)]
    )
    # Towards A (within 5"), ending engaged with it.
    response = await client.post(
        f"/games/{game_id}/pile-in",
        json={"unit_id": d["unit_id"], "positions": _shifted(d, dy=3)},
    )
    assert response.status_code == 200, response.text


async def test_an_overrun_fight(client: AsyncClient, session, tmp_path, monkeypatch):
    # D charged, but isn't engaged when picked to fight: it piles in first.
    game_id, d, a = await _charged_game(client, session, tmp_path, monkeypatch, then_at=4)
    await _done(client, game_id, 2)
    state = await _fight_state(client, game_id)
    [unit] = [u for u in state["units"] if u["name"] == "D"]
    assert (state["step"], unit["overrun"], unit["can_fight"]) == ("fights_first", True, False)
    assert "overrun" in unit["reason"]
    response = await client.post(
        f"/games/{game_id}/pile-in",
        json={"unit_id": d["unit_id"], "positions": _shifted(d, dy=3)},
    )
    assert response.status_code == 200, response.text
    [unit] = [u for u in (await _fight_state(client, game_id))["units"] if u["name"] == "D"]
    assert (unit["overrun"], unit["can_fight"]) == (False, True), unit["reason"]


async def test_passing_ends_the_fight_step(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D charged, but A is now more than 5" away: D's player can pass, and with
    # nothing of A's player's eligible, the Fight step ends.
    game_id, d, a = await _charged_game(client, session, tmp_path, monkeypatch, then_at=7)
    await _done(client, game_id, 2)
    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"], state["can_pass"]) == ("fights_first", 2, True)
    assert (await client.post(f"/games/{game_id}/fight/pass", json={"seat": 1})).status_code == 400
    response = await client.post(f"/games/{game_id}/fight/pass", json={"seat": 2})
    assert response.status_code == 200, response.text
    assert (await _fight_state(client, game_id))["step"] == "done"


async def test_no_passing_within_5(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, d, a = await _charged_game(client, session, tmp_path, monkeypatch, then_at=4)
    await _done(client, game_id, 2)
    assert not (await _fight_state(client, game_id))["can_pass"]
    response = await client.post(f"/games/{game_id}/fight/pass", json={"seat": 2})
    assert response.status_code == 400


async def test_one_melee_weapon_per_model(client: AsyncClient, session, tmp_path, monkeypatch):
    units = {1: [("A", 1, BLADE)], 2: [("D", 1, BLADE)]}
    game_id, deployment = await _to_fight(
        client, session, tmp_path, monkeypatch, units, {"D": [(20, 4)], "A": [(20, 6)]}
    )
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    axe = await _add_weapon(session, d, "D axe")
    fangs = await _add_weapon(session, d, "D fangs", abilities=["Extra Attacks"])
    targets = (await client.get(f"/games/{game_id}/fight/targets?unit_id={d['unit_id']}")).json()
    blade = next(w["id"] for w in targets[0]["weapons"] if w["name"] == "D blade")
    response = await client.post(
        f"/games/{game_id}/fight",
        json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"],
              "weapon_ids": [blade, axe]},
    )
    assert response.status_code == 400
    assert "one melee weapon" in response.json()["detail"]
    # The blade, and the [EXTRA ATTACKS] fangs as well.
    response = await client.post(
        f"/games/{game_id}/fight",
        json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"], "weapon_ids": [blade]},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["combat"]["attack_rolls"]) == 2
    assert fangs


async def test_splitting_melee_attacks(client: AsyncClient, session, tmp_path, monkeypatch):
    # D (one model, a 3-attack axe) is engaged with A and B: 2 attacks
    # against A, 1 against B.
    units = {1: [("A", 1, BLADE), ("B", 1, BLADE)], 2: [("D", 1, {})]}
    places = {"D": [(20, 4)], "A": [(20, 6)], "B": [(21.8, 5)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, a, b = (_unit_named(deployment, n) for n in "DAB")
    axe = await _add_weapon(session, d, "D axe", attacks="3")

    async def fight(splits):
        return await client.post(
            f"/games/{game_id}/fight",
            json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"],
                  "weapon_ids": [axe],
                  "splits": [{"weapon_id": axe, "target_unit_id": t["unit_id"], "attacks": n}
                             for t, n in splits]},
        )

    assert "that many attacks" in (await fight([(a, 3), (b, 1)])).json()["detail"]
    assert "at least one" in (await fight([(a, 3), (b, 0)])).json()["detail"]
    response = await fight([(a, 2), (b, 1)])
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["combat"]["attack_rolls"]) == 2
    [split] = body["split_combats"]
    assert (split["name"], len(split["combat"]["attack_rolls"])) == ("B", 1)
    state = await _fight_state(client, game_id)
    assert [(f["unit_name"], f["target_name"], f["total_damage"]) for f in state["fights"]] == [
        ("D", "A", 3)
    ]


async def test_engaged_at_the_start_of_the_fight_step_stays_eligible(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # E is engaged with A when the Fight step starts; once D's fight moves A
    # away (here: placed elsewhere), E is still eligible - with no one to
    # fight, its player can pass.
    from app.routers.games import _load_game
    from app.services.in_game import deployment as deployment_service, fighting

    units = {1: [("A", 1, BLADE)], 2: [("E", 1, BLADE)]}
    game_id, deployment = await _to_fight(
        client, session, tmp_path, monkeypatch, units, {"E": [(20, 4)], "A": [(20, 6)]}
    )
    e, a = _unit_named(deployment, "E"), _unit_named(deployment, "A")
    await _place(session, a, [(40, 30)])
    session.expire_all()
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, e["unit_id"])
    assert fighting.engaged_at_fight_start(game, unit)
    assert fighting.eligible_to_fight(game, unit)
    assert _row_at(0, 0, 1)


async def test_an_engaging_consolidation_brings_new_foes_to_fight(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D destroys A; B (more than 2" but within 3" of D, so not engaged) hasn't
    # fought. D's engaging consolidation ends engaged with B: B fights next.
    from tests.test_casualties import _set_models

    units = {1: [("A", 1, BLADE), ("B", 1, BLADE)], 2: [("D", 1, BLADE)]}
    places = {"D": [(20, 4)], "A": [(20, 4 + 2 * R32 + 0.5)], "B": [(20 - 2 * R32 - 2.5, 4)]}
    game_id, deployment = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    d, a, b = (_unit_named(deployment, n) for n in "DAB")
    await _set_models(session, a, wounds=1)
    response = await client.post(
        f"/games/{game_id}/fight",
        json={"unit_id": d["unit_id"], "target_unit_id": a["unit_id"],
              "weapon_ids": [w["id"] for w in (await client.get(
                  f"/games/{game_id}/fight/targets?unit_id={d['unit_id']}")).json()[0]["weapons"]]},
    )
    assert response.status_code == 200, response.text
    state = await _fight_state(client, game_id)
    assert state["step"] == "consolidate"
    assert (state["consolidating"]["mode"], state["consolidating"]["options"]) == (
        "engaging", [{"id": b["unit_id"], "name": "B"}]
    )
    d = _unit_named(await _deployment(client, game_id), "D")
    check = (await client.post(
        f"/games/{game_id}/fight/consolidate/check",
        json={"unit_id": d["unit_id"], "positions": _shifted(d, dy=0.5)},
    )).json()
    assert "The unit must end engaged with B" in check["problems"]
    response = await client.post(
        f"/games/{game_id}/fight/consolidate",
        json={"unit_id": d["unit_id"], "positions": _shifted(d, dx=-1), "pick_ids": [b["unit_id"]]},
    )
    assert response.status_code == 200, response.text
    state = await _fight_state(client, game_id)
    assert (state["step"], state["seat"]) == ("remaining", 1)
    [unit] = [u for u in state["units"] if u["name"] == "B"]
    assert unit["can_fight"], unit
