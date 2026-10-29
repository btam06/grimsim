from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import DatasheetAbility, Faction, FactionAbility, ListWarlord, Model, UnitModel
from app.routers.games import _load_game
from app.seeds.factions.space_marines import abilities as space_marines
from app.seeds.factions.space_marines import datasheet_abilities as space_marine_datasheets
from app.services.in_game import command_phase, deployment
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named
from tests.test_movement import _move, _shifted
from tests.test_reinforcements import _advance_to

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Seat 1's
# faction is the Space Marines: A has Combat Doctrines, B doesn't; C is a
# CHARACTER with Transhuman Strategist. Seat 2 has D. Every model has a 24"
# gun.

DOCTRINES = space_marines.COMBAT_DOCTRINES
ASSAULT, DEVASTATOR, TACTICAL = "Assault Doctrine", "Devastator Doctrine", "Tactical Doctrine"
TEXT = dict(space_marines.ENTRIES)
STRATEGIST = "Transhuman Strategist"


async def _model(session, unit):
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    return (
        await session.execute(
            select(Model)
            .options(selectinload(Model.abilities), selectinload(Model.faction_abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()


async def _doctrines_game(client, session, tmp_path):
    units = {
        1: [
            ("A", 1, {"weapon_range": 24}),
            ("B", 1, {"weapon_range": 24}),
            ("C", 1, {"weapon_range": 24, "keywords": ("CHARACTER",)}),
        ],
        2: [("D", 1, {"weapon_range": 24})],
    }
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    named = {name: _unit_named(deployment_, name) for name in "ABCD"}
    a = await _model(session, named["A"])
    faction = await session.get(Faction, a.faction_id)
    faction.name = "Space Marines"
    ability = FactionAbility(name=DOCTRINES, description=TEXT[DOCTRINES], faction=faction)
    a.faction_abilities.append(ability)
    c = await _model(session, named["C"])
    text = dict((e[0], e[1]) for e in space_marine_datasheets.ENTRIES)[STRATEGIST]
    c.abilities.append(DatasheetAbility(name=STRATEGIST, description=text))
    await session.commit()
    return game_id, ability.id, named


async def _deploy_all(client, game_id, named):
    spots = {"A": (20, 38), "D": (20, 4), "B": (30, 38), "C": (40, 38)}
    for name, (x, y) in spots.items():
        response = await _deploy(client, game_id, named[name], _row(named[name], x, y))
        assert response.status_code == 200, response.text


async def _command(client, game_id):
    response = await client.get(f"/games/{game_id}/command")
    assert response.status_code == 200, response.text
    return next(a for a in response.json()["abilities"] if a["ability"] == DOCTRINES)


async def _choose(client, game_id, ability_id, option):
    return await client.post(
        f"/games/{game_id}/command/choice",
        json={"seat": 1, "faction_ability_id": ability_id, "option": option},
    )


async def _advanced(client, game_id, name):
    unit = _unit_named(await _deployment(client, game_id), name)
    response = await client.post(
        f"/games/{game_id}/movement/advance", json={"unit_id": unit["unit_id"]}
    )
    assert response.status_code == 200, response.text
    unit = _unit_named(await _deployment(client, game_id), name)
    response = await _move(client, game_id, unit, "advance", _shifted(unit, dy=-1))
    assert response.status_code == 200, response.text


async def test_each_combat_doctrine_once_a_battle(client: AsyncClient, session, tmp_path):
    game_id, ability_id, named = await _doctrines_game(client, session, tmp_path)
    await _deploy_all(client, game_id, named)
    await _advance_to(client, game_id, 1, 1, "command")
    rule = await _command(client, game_id)
    assert rule["faction_ability_id"] == ability_id and rule["unit_id"] is None
    assert rule["unit_name"] == "A"
    assert {ASSAULT, DEVASTATOR, TACTICAL} <= set(rule["options"])
    # Optional: the Command phase can end without one.
    assert not rule["required"] and rule["active"] is None

    response = await _choose(client, game_id, ability_id, DEVASTATOR)
    assert response.status_code == 200, response.text
    # Changed in the same phase: only the last one counts as selected.
    await _choose(client, game_id, ability_id, TACTICAL)
    rule = await _command(client, game_id)
    assert (rule["active"], rule["chosen"]) == (TACTICAL, True)
    response = await _choose(client, game_id, ability_id, DEVASTATOR)
    assert response.status_code == 200, response.text

    # Active through seat 2's turn, until seat 1's next Command phase.
    await _advance_to(client, game_id, 2, 2, "shooting")
    game = await _load_game(session, game_id)
    assert command_phase.active_army_options(game, 1) == [DEVASTATOR]
    await _advance_to(client, game_id, 2, 1, "command")
    game = await _load_game(session, game_id)
    assert command_phase.active_army_options(game, 1) == []

    # Used up: the others can still be selected (Tactical too - it was only
    # selected in passing).
    rule = await _command(client, game_id)
    assert DEVASTATOR not in rule["options"] and TACTICAL in rule["options"]
    assert rule["used_options"] == [DEVASTATOR]
    response = await _choose(client, game_id, ability_id, DEVASTATOR)
    assert "already been selected this battle" in response.json()["detail"]
    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["phase"] == "movement"

    # Not in the opponent's Command phase.
    await _advance_to(client, game_id, 3, 2, "command")
    response = await client.post(
        f"/games/{game_id}/command/choice",
        json={"seat": 1, "faction_ability_id": ability_id, "option": ASSAULT},
    )
    assert response.status_code == 400


async def test_devastator_doctrine_shoots_after_advancing(
    client: AsyncClient, session, tmp_path
):
    game_id, ability_id, named = await _doctrines_game(client, session, tmp_path)
    await _deploy_all(client, game_id, named)
    await _advance_to(client, game_id, 1, 1, "command")
    await _choose(client, game_id, ability_id, DEVASTATOR)
    await client.post(f"/games/{game_id}/advance")
    for name in "AB":
        await _advanced(client, game_id, name)
    await _advance_to(client, game_id, 1, 1, "shooting")
    shooting = {
        u["name"]: u for u in (await client.get(f"/games/{game_id}/shooting")).json()["units"]
    }
    # Only units with the rule.
    assert shooting["A"]["can_shoot"], shooting["A"]
    assert shooting["B"]["reason"] == "it Advanced, and has no Assault weapons"
    await _advance_to(client, game_id, 1, 1, "charge")
    charge = {u["name"]: u for u in (await client.get(f"/games/{game_id}/charge")).json()["units"]}
    assert charge["A"]["reason"] == "it Advanced this turn"


async def test_assault_doctrine_charges_after_advancing(client: AsyncClient, session, tmp_path):
    game_id, ability_id, named = await _doctrines_game(client, session, tmp_path)
    await _deploy_all(client, game_id, named)
    await _advance_to(client, game_id, 1, 1, "command")
    await _choose(client, game_id, ability_id, ASSAULT)
    await client.post(f"/games/{game_id}/advance")
    for name in "AB":
        await _advanced(client, game_id, name)
    await _advance_to(client, game_id, 1, 1, "shooting")
    shooting = {
        u["name"]: u for u in (await client.get(f"/games/{game_id}/shooting")).json()["units"]
    }
    # It can charge, not shoot.
    assert shooting["A"]["reason"] == "it Advanced, and has no Assault weapons"
    await _advance_to(client, game_id, 1, 1, "charge")
    charge = {u["name"]: u for u in (await client.get(f"/games/{game_id}/charge")).json()["units"]}
    # Advancing doesn't stop it (nothing's within 12" here, though).
    assert charge["A"]["reason"] in (None, 'no enemy unit is within 12"')
    assert charge["B"]["reason"] == "it Advanced this turn"


async def test_tactical_doctrine_shoots_and_charges_after_falling_back(
    client: AsyncClient, session, tmp_path
):
    game_id, ability_id, named = await _doctrines_game(client, session, tmp_path)
    await _deploy_all(client, game_id, named)
    await _advance_to(client, game_id, 1, 1, "command")
    await _choose(client, game_id, ability_id, TACTICAL)
    game = await _load_game(session, game_id)
    a, b = (deployment.find_unit(game, named[n]["unit_id"]) for n in "AB")
    assert command_phase.eligible_after(game, a, "fell_back", "shoot")
    assert command_phase.eligible_after(game, a, "fell_back", "charge")
    assert not command_phase.eligible_after(game, a, "advanced", "charge")
    assert not command_phase.eligible_after(game, b, "fell_back", "shoot")


async def test_transhuman_strategist_gains_cp_while_warlord(
    client: AsyncClient, session, tmp_path
):
    game_id, _, named = await _doctrines_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    list_id = next(p for p in game.players if p.seat == 1).army_list.id
    session.add(ListWarlord(list_id=list_id, unit_id=named["C"]["unit_id"]))
    await session.commit()
    await _deploy_all(client, game_id, named)
    game = (await client.get(f"/games/{game_id}")).json()
    cp = {p["seat"]: p["cp"] for p in game["players"]}
    # Its 1CP at the start of the round, on top of the Command phase's.
    assert cp[1] == cp[2] + 1


async def test_a_lists_warlord_is_one_of_its_characters(client: AsyncClient, session, tmp_path):
    game_id, _, named = await _doctrines_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    army_list = next(p for p in game.players if p.seat == 1).army_list
    lists = (await client.get("/lists")).json()
    current = next(item for item in lists if item["id"] == army_list.id)
    assert current["warlord_unit_id"] is None
    payload = {k: current[k] for k in ("name", "points_limit", "faction_id", "detachment_ids")}
    payload["user_id"] = current["user_id"]

    for unit, detail in ((named["B"], "CHARACTER"), (named["D"], "in this list")):
        response = await client.put(
            f"/lists/{army_list.id}", json={**payload, "warlord_unit_id": unit["unit_id"]}
        )
        assert response.status_code == 400 and detail in response.json()["detail"]
    response = await client.put(
        f"/lists/{army_list.id}", json={**payload, "warlord_unit_id": named["C"]["unit_id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["warlord_unit_id"] == named["C"]["unit_id"]
    # Saving it again keeps it; leaving it out clears it.
    response = await client.put(
        f"/lists/{army_list.id}", json={**payload, "warlord_unit_id": named["C"]["unit_id"]}
    )
    assert response.json()["warlord_unit_id"] == named["C"]["unit_id"]
    response = await client.put(f"/lists/{army_list.id}", json=payload)
    assert response.json()["warlord_unit_id"] is None
