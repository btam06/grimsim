from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import DatasheetAbility, GameModelDamage, Model, UnitModel
from app.routers.games import _load_game, _rule_options
from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech
from app.services.in_game import deployment
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named
from tests.test_movement import _move, _shifted
from tests.test_reinforcements import _advance_to

# Games on the test layout: the attacker (seat 1) deploys along y 32-44, the
# defender (seat 2) along y 0-12, and the defender goes first. Seat 1 has
# Cawl (Canticles of the Omnissiah, Self-repair Mechanisms) at (10, 38),
# Thulia (Rod of the War Forge) at (20, 38), Skitarii within 6" of her at
# (24, 38), Far Skitarii at (45, 38) and Kastelans (Battle Protocols) at
# (50, 40); seat 2 has D at (20, 4). Every model has a 24" gun.

TEXT = {entry[0]: entry[1] for entry in admech.ENTRIES}
SEAT_1 = {
    "Cawl": ((10, 38), ("Canticles of the Omnissiah", "Self-repair Mechanisms"), ()),
    "Thulia": ((20, 38), ("Rod of the War Forge",), ("THULIA GHULD",)),
    "Skitarii": ((24, 38), (), ("SKITARII",)),
    "Far": ((45, 38), (), ("SKITARII",)),
    "Kastelans": ((50, 40), ("Battle Protocols",), ()),
}


async def _give(session, unit, names):
    # Gives the unit's models (they share one Model) those datasheet abilities.
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    model = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    for name in names:
        model.abilities.append(DatasheetAbility(name=name, description=TEXT[name]))
    await session.commit()


async def _command_game(client, session, tmp_path, monkeypatch, roll=3):
    monkeypatch.setattr("app.services.in_game.command_phase.random.randint", lambda a, b: roll)
    units = {
        1: [
            (name, 1, {"weapon_range": 24, "keywords": keywords})
            for name, (_, _, keywords) in SEAT_1.items()
        ],
        2: [("D", 1, {"weapon_range": 24})],
    }
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    named = {name: _unit_named(deployment_, name) for name in [*SEAT_1, "D"]}
    for name, (_, abilities, _) in SEAT_1.items():
        await _give(session, named[name], abilities)
    order = ["Cawl", "D", "Thulia", "Skitarii", "Far", "Kastelans"]
    for name in order:
        spot = SEAT_1[name][0] if name in SEAT_1 else (20, 4)
        response = await _deploy(client, game_id, named[name], _row(named[name], *spot))
        assert response.status_code == 200, response.text
    return game_id, named


async def _command(client, game_id):
    response = await client.get(f"/games/{game_id}/command")
    assert response.status_code == 200, response.text
    return response.json()


async def _choose(client, game_id, unit, ability, option, target=None):
    return await client.post(
        f"/games/{game_id}/command/choice",
        json={
            "seat": 1,
            "unit_id": unit["unit_id"],
            "ability": ability,
            "option": option,
            "target_unit_id": target["unit_id"] if target else None,
        },
    )


def _ability(command, name):
    return next(a for a in command["abilities"] if a["ability"] == name)


async def _options(session, game_id, unit):
    game = await _load_game(session, game_id)
    return _rule_options(game, deployment.find_unit(game, unit["unit_id"]))


async def test_options_are_selected_in_the_command_phase(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, units = await _command_game(client, session, tmp_path, monkeypatch)
    await _advance_to(client, game_id, 1, 1, "command")
    command = await _command(client, game_id)
    assert command["seat"] == 1
    canticles = _ability(command, "Canticles of the Omnissiah")
    assert canticles["unit_name"] == "Cawl" and canticles["required"]
    assert "Shroudpsalm" in canticles["options"]
    rod = _ability(command, "Rod of the War Forge")
    assert rod["needs_target"]
    # Only SKITARII or THULIA GHULD units within 6" of Thulia.
    target_names = {t["name"] for t in rod["targets"]}
    assert {"Thulia", "Skitarii"} <= target_names and "Far" not in target_names

    # The Command phase can't end until both are selected.
    response = await client.post(f"/games/{game_id}/advance")
    detail = response.json()["detail"]
    assert "Cawl's Canticles of the Omnissiah" in detail
    assert "Thulia's Rod of the War Forge" in detail

    response = await _choose(client, game_id, units["Cawl"], "Canticles of the Omnissiah", None)
    assert "must have one of its options" in response.json()["detail"]
    response = await _choose(
        client, game_id, units["Cawl"], "Canticles of the Omnissiah", "Shroudpsalm"
    )
    assert response.status_code == 200, response.text
    for target in (None, units["Far"]):
        response = await _choose(
            client, game_id, units["Thulia"], "Rod of the War Forge", "Fanatical Devotion", target
        )
        assert 'within 6"' in response.json()["detail"]
    response = await _choose(
        client,
        game_id,
        units["Thulia"],
        "Rod of the War Forge",
        "Fanatical Devotion",
        units["Skitarii"],
    )
    rod = _ability(response.json(), "Rod of the War Forge")
    assert (rod["active"], rod["chosen"], rod["target_unit_id"]) == (
        "Fanatical Devotion", True, units["Skitarii"]["unit_id"]
    )
    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["phase"] == "movement"

    # In combat: Fanatical Devotion applies only to its target; Shroudpsalm
    # to units within 6" of Cawl (see the aura tests below).
    assert "Fanatical Devotion" in await _options(session, game_id, units["Skitarii"])
    assert "Fanatical Devotion" not in await _options(session, game_id, units["Far"])
    assert "Shroudpsalm" in await _options(session, game_id, units["Cawl"])

    # Still active in seat 2's turn...
    await _advance_to(client, game_id, 2, 2, "command")
    assert "Shroudpsalm" in await _options(session, game_id, units["Cawl"])
    # ...until seat 1's next Command phase: then they're selected again.
    await _advance_to(client, game_id, 2, 1, "command")
    assert "Shroudpsalm" not in await _options(session, game_id, units["Cawl"])
    canticles = _ability(await _command(client, game_id), "Canticles of the Omnissiah")
    assert (canticles["active"], canticles["chosen"]) == (None, False)
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 400


async def test_fanatical_devotion_shoots_and_charges_after_advancing(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, units = await _command_game(client, session, tmp_path, monkeypatch)
    await _advance_to(client, game_id, 1, 1, "command")
    await _choose(client, game_id, units["Cawl"], "Canticles of the Omnissiah", "Shroudpsalm")
    await _choose(
        client,
        game_id,
        units["Thulia"],
        "Rod of the War Forge",
        "Fanatical Devotion",
        units["Skitarii"],
    )
    await client.post(f"/games/{game_id}/advance")
    for name in ("Skitarii", "Far"):
        unit = units[name]
        response = await client.post(
            f"/games/{game_id}/movement/advance", json={"unit_id": unit["unit_id"]}
        )
        assert response.status_code == 200, response.text
        moved = _unit_named(await _deployment(client, game_id), name)
        response = await _move(client, game_id, moved, "advance", _shifted(moved, dy=-1))
        assert response.status_code == 200, response.text

    await _advance_to(client, game_id, 1, 1, "shooting")
    response = await client.get(f"/games/{game_id}/shooting")
    shooting = {u["name"]: u for u in response.json()["units"]}
    assert shooting["Skitarii"]["can_shoot"], shooting["Skitarii"]
    assert shooting["Far"]["reason"] == "it Advanced, and has no Assault weapons"

    await _advance_to(client, game_id, 1, 1, "charge")
    response = await client.get(f"/games/{game_id}/charge")
    charge = {u["name"]: u for u in response.json()["units"]}
    assert charge["Skitarii"]["reason"] is None
    assert charge["Far"]["reason"] == "it Advanced this turn"
    roll = "/games/{}/charge/roll"
    response = await client.post(roll.format(game_id), json={"unit_id": units["Far"]["unit_id"]})
    assert "it Advanced this turn" in response.json()["detail"]
    response = await client.post(
        roll.format(game_id), json={"unit_id": units["Skitarii"]["unit_id"]}
    )
    assert response.status_code == 200, response.text


async def test_battle_protocols_stay_until_changed(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, units = await _command_game(client, session, tmp_path, monkeypatch)
    await _advance_to(client, game_id, 1, 1, "command")
    protocols = _ability(await _command(client, game_id), "Battle Protocols")
    # Aegis Protocol to start with; not required.
    assert (protocols["active"], protocols["required"], protocols["persistent"]) == (
        "Aegis Protocol", False, True
    )
    assert "Aegis Protocol" in await _options(session, game_id, units["Kastelans"])
    response = await _choose(
        client, game_id, units["Kastelans"], "Battle Protocols", "Protector Protocol"
    )
    assert response.status_code == 200, response.text
    # Its next Command phase: still in the Protector Protocol, and nothing to
    # select for it.
    await _choose(client, game_id, units["Cawl"], "Canticles of the Omnissiah", "Shroudpsalm")
    await _choose(
        client, game_id, units["Thulia"], "Rod of the War Forge", "Adaptive Tactics",
        units["Thulia"],
    )
    await _advance_to(client, game_id, 2, 1, "command")
    protocols = _ability(await _command(client, game_id), "Battle Protocols")
    assert (protocols["active"], protocols["chosen"]) == ("Protector Protocol", False)
    response = await client.post(f"/games/{game_id}/advance")
    assert "Battle Protocols" not in response.json()["detail"]


async def test_self_repair_at_the_start_of_the_command_phase(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, units = await _command_game(client, session, tmp_path, monkeypatch, roll=2)
    cawl = units["Cawl"]["models"][0]["unit_model_id"]
    session.add(GameModelDamage(game_id=game_id, unit_model_id=cawl, wounds_lost=1))
    await session.commit()
    await _advance_to(client, game_id, 1, 1, "command")
    [heal] = (await _command(client, game_id))["heals"]
    # Rolled 2, but had only 1 wound to regain.
    assert (heal["unit_name"], heal["ability"], heal["roll"], heal["healed"]) == (
        "Cawl", "Self-repair Mechanisms", 2, 1
    )
    deployment_ = await _deployment(client, game_id)
    model = _unit_named(deployment_, "Cawl")["models"][0]
    assert model["wounds_remaining"] == model["wounds"]


# --- auras (see app/services/in_game/auras.py) ---


async def test_shroudpsalm_reaches_6_inches_from_cawl(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, units = await _command_game(client, session, tmp_path, monkeypatch)
    await _advance_to(client, game_id, 1, 1, "command")
    await _choose(client, game_id, units["Cawl"], "Canticles of the Omnissiah", "Shroudpsalm")
    # Cawl's own unit is in range; Thulia, 10" away, isn't.
    assert "Shroudpsalm" in await _options(session, game_id, units["Cawl"])
    assert "Shroudpsalm" not in await _options(session, game_id, units["Thulia"])

    # Shown while moving: Cawl's Shroudpsalm, and how far Thulia's Rod reaches.
    deployment_ = await _deployment(client, game_id)
    cawl, thulia = (_unit_named(deployment_, n) for n in ("Cawl", "Thulia"))
    assert {(a["name"], a["range"]) for a in cawl["auras"]} == {("Shroudpsalm", 6.0)}
    assert ("Rod of the War Forge", 6.0) in {(a["name"], a["range"]) for a in thulia["auras"]}


async def test_an_aura_with_no_choice_is_always_on_within_range(
    client: AsyncClient, session, tmp_path
):
    # Seat 2's Bearer has Nullstone Field Generator (Aura) at (20, 4): Near,
    # at (26, 4), is within 6" of it; Far, at (40, 4), isn't.
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    units = {
        1: [("A", 1, {})],
        2: [("Bearer", 1, {}), ("Near", 1, {}), ("Far", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    named = {n: _unit_named(deployment_, n) for n in ("A", "Bearer", "Near", "Far")}
    name = "Nullstone Field Generator (Aura)"
    text = next(e[1] for e in necrons.ENTRIES if e[0] == name)
    unit_model = await session.get(UnitModel, named["Bearer"]["models"][0]["unit_model_id"])
    model = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    model.abilities.append(DatasheetAbility(name=name, description=text))
    await session.commit()
    spots = {"A": (20, 40), "Bearer": (20, 4), "Near": (26, 4), "Far": (40, 4)}
    for unit_name in ("A", "Bearer", "Near", "Far"):
        unit = named[unit_name]
        response = await _deploy(client, game_id, unit, _row(unit, *spots[unit_name]))
        assert response.status_code == 200, response.text

    assert "Nullstone Field" in await _options(session, game_id, named["Bearer"])
    assert "Nullstone Field" in await _options(session, game_id, named["Near"])
    assert "Nullstone Field" not in await _options(session, game_id, named["Far"])
    # Not the enemy's.
    assert "Nullstone Field" not in await _options(session, game_id, named["A"])


async def test_machine_vengeance_targets_one_enemy_unit(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, units = await _command_game(client, session, tmp_path, monkeypatch)
    await _advance_to(client, game_id, 1, 1, "command")
    canticles = _ability(await _command(client, game_id), "Canticles of the Omnissiah")
    # Any enemy unit on the battlefield can be its target.
    option = "Invocation of Machine Vengeance"
    assert [t["name"] for t in canticles["option_targets"][option]] == ["D"]
    response = await _choose(client, game_id, units["Cawl"], "Canticles of the Omnissiah", option)
    assert "needs an enemy unit" in response.json()["detail"]
    response = await _choose(
        client, game_id, units["Cawl"], "Canticles of the Omnissiah", option, units["Skitarii"]
    )
    assert "needs an enemy unit" in response.json()["detail"]
    response = await _choose(
        client, game_id, units["Cawl"], "Canticles of the Omnissiah", option, units["D"]
    )
    canticles = _ability(response.json(), "Canticles of the Omnissiah")
    assert (canticles["active"], canticles["target_unit_id"]) == (option, units["D"]["unit_id"])

    # Only when attacking D - from anywhere in seat 1's army (it's global).
    game = await _load_game(session, game_id)
    far, d = (deployment.find_unit(game, units[n]["unit_id"]) for n in ("Far", "D"))
    assert option in _rule_options(game, far, d)
    assert option not in _rule_options(game, far)
    assert option not in _rule_options(game, far, far)


async def test_the_fires_of_mars_for_the_unit_chosen_within_6(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, units = await _command_game(client, session, tmp_path, monkeypatch)
    await _advance_to(client, game_id, 1, 1, "command")
    await _choose(client, game_id, units["Cawl"], "Canticles of the Omnissiah", "Shroudpsalm")
    response = await _choose(
        client, game_id, units["Thulia"], "Rod of the War Forge", "The Fires of Mars",
        units["Skitarii"],
    )
    assert response.status_code == 200, response.text
    assert "The Fires of Mars" in await _options(session, game_id, units["Skitarii"])
    for name in ("Far", "Thulia", "Kastelans"):
        assert "The Fires of Mars" not in await _options(session, game_id, units[name])
    # Thulia can choose herself instead (she's THULIA GHULD, and within 6").
    response = await _choose(
        client, game_id, units["Thulia"], "Rod of the War Forge", "The Fires of Mars",
        units["Thulia"],
    )
    assert response.status_code == 200, response.text
    assert "The Fires of Mars" in await _options(session, game_id, units["Thulia"])
    assert "The Fires of Mars" not in await _options(session, game_id, units["Skitarii"])
    # Not a unit without SKITARII or THULIA GHULD, however close.
    response = await _choose(
        client, game_id, units["Thulia"], "Rod of the War Forge", "The Fires of Mars",
        units["Cawl"],
    )
    assert response.status_code == 400
