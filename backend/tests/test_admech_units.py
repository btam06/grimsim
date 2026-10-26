from httpx import AsyncClient

from app.models import DatasheetAbility, GameDisembarkation
from app.routers.games import _load_game
from app.seeds import weapon_abilities as weapon_ability_seeds
from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech_datasheets
from app.seeds.factions.adeptus_mechanicus import fire_support
from app.services.in_game import deployment, game as game_service, movement
from tests.test_deployment import _unit_named
from tests.test_movement import _battle
from tests.test_shooting import _place
from tests.test_space_marine_units import _model_of
from tests.test_space_marines import _applies

# The Hastarii Fusiliers', Pteraxii Skystalkers', Skorpius Dunerider's and
# Sicarian Ruststalkers' rules. Games are in seat 2's first turn (see
# tests/test_movement.py _battle): seat 2 has P and B (ADEPTUS MECHANICUS
# BATTLELINE), seat 1 has A.

BATTLELINE = ("ADEPTUS MECHANICUS", "BATTLELINE")


async def _admech_battle(client, session, tmp_path, ability):
    units = {
        1: [("A", 1, {})],
        2: [("P", 1, {"weapon_range": 24}), ("B", 1, {"keywords": BATTLELINE})],
    }
    spots = {"A": (20, 38), "P": (20, 4), "B": (40, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    named = {n: _unit_named(deployment_, n) for n in "APB"}
    model = await _model_of(session, named["P"])
    model.abilities.append(DatasheetAbility(name=ability, description=ability))
    await session.commit()
    return game["id"], named


def test_monocular_targeting_helms():
    rules = admech_datasheets.RULES["Monocular Targeting Helms"]
    fusil = {"weapon_name": "Neutron fusil"}
    assert _applies(rules, {**fusil, "defender_keywords": {"VEHICLE"}})
    assert not _applies(rules, {**fusil, "defender_keywords": {"INFANTRY"}})
    assert not _applies(rules, {"weapon_name": "Phosphor blaster", "defender_keywords": {"VEHICLE"}})


def test_rapid_fire_9():
    weapons = {entry[0]: entry for entry in weapon_ability_seeds.ENTRIES}
    assert weapons["Rapid Fire 9"][3] == ["add_nine_attacks"]


async def test_optimised_gait(client: AsyncClient, session, tmp_path):
    game_id, named = await _admech_battle(client, session, tmp_path, "Optimised Gait")
    game = await _load_game(session, game_id)
    p = deployment.find_unit(game, named["P"]["unit_id"])
    # B is 20" away: +1.
    assert movement.roll_bonus(game, p, "advance") == 1
    assert movement.roll_bonus(game, p, "charge") == 1
    await _place(session, named["B"], [(24, 4)])
    session.expire_all()
    game = await _load_game(session, game_id)
    p = deployment.find_unit(game, named["P"]["unit_id"])
    # Within 6" of B: +2.
    assert movement.roll_bonus(game, p, "advance") == 2


async def test_ride_the_thermals(client: AsyncClient, session, tmp_path):
    game_id, named = await _admech_battle(client, session, tmp_path, "Ride the Thermals")
    p, a, b = named["P"], named["A"], named["B"]
    await _place(session, a, [(20, 24)])
    response = await client.post(f"/games/{game_id}/advance")
    assert response.json()["phase"] == "shooting"
    shooting = (await client.get(f"/games/{game_id}/shooting")).json()
    unit = next(u for u in shooting["units"] if u["unit_id"] == p["unit_id"])
    # Not before it has shot.
    assert unit["shoot_scoot"] is None
    [target] = (
        await client.get(f"/games/{game_id}/shooting/targets?unit_id={p['unit_id']}")
    ).json()
    response = await client.post(
        f"/games/{game_id}/shooting",
        json={
            "unit_id": p["unit_id"],
            "target_unit_id": a["unit_id"],
            "weapon_ids": [w["id"] for w in target["weapons"]],
        },
    )
    assert response.status_code == 200, response.text
    shooting = (await client.get(f"/games/{game_id}/shooting")).json()
    unit = next(u for u in shooting["units"] if u["unit_id"] == p["unit_id"])
    assert (unit["shoot_scoot"], unit["shoot_scoot_reach"]) == ("Ride the Thermals", 12)

    model = p["models"][0]["unit_model_id"]

    async def check(x, y):
        payload = {"unit_id": p["unit_id"], "positions": [{"unit_model_id": model, "x": x, "y": y}]}
        return (await client.post(f"/games/{game_id}/shoot-scoot/check", json=payload)).json()

    assert (await check(20, 9))["valid"]
    # Further than 6": only ending wholly within 6" of a BATTLELINE unit.
    far = await check(20, 14)
    assert not far["valid"] and "BATTLELINE" in " ".join(far["problems"])
    await _place(session, b, [(23, 14)])
    assert (await check(20, 14))["valid"]
    response = await client.post(
        f"/games/{game_id}/shoot-scoot",
        json={"unit_id": p["unit_id"], "positions": [{"unit_model_id": model, "x": 20, "y": 14}]},
    )
    assert response.status_code == 200, response.text
    # Once, and no charge this turn.
    assert (await client.post(f"/games/{game_id}/shoot-scoot/check", json={
        "unit_id": p["unit_id"], "positions": [{"unit_model_id": model, "x": 20, "y": 15}],
    })).status_code == 400
    await client.post(f"/games/{game_id}/advance")
    charge = (await client.get(f"/games/{game_id}/charge")).json()
    unit = next(u for u in charge["units"] if u["unit_id"] == p["unit_id"])
    assert unit["reason"] == "it moved after shooting this turn"


async def test_fire_support(client: AsyncClient, session, tmp_path):
    game_id, named = await _admech_battle(client, session, tmp_path, "Fire Support")
    await client.post(f"/games/{game_id}/advance")
    game = await _load_game(session, game_id)
    assert game.phase == "shooting"
    p, a, b = (deployment.find_unit(game, named[n]["unit_id"]) for n in "PAB")
    # No hits: nothing picked out.
    fire_support.after_shooting(game, p, a, 0)
    assert not game.fire_support_targets
    fire_support.after_shooting(game, p, a, 2)
    # B didn't disembark from P: no re-roll; once it has, it re-rolls against A.
    assert fire_support.rules(game, b, a) == []
    game.disembarkations.append(
        GameDisembarkation(
            unit_id=b.id, transport_unit_id=p.id, battle_round=game.battle_round,
            turn_seat=game.turn_seat,
        )
    )
    assert fire_support.rules(game, b, a) == [fire_support.REROLL_WOUNDS]
    assert fire_support.rules(game, b, p) == []


async def test_broad_spectrum_data_tether(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, named = await _admech_battle(
        client, session, tmp_path, "Broad Spectrum Data-tether"
    )
    game = await _load_game(session, game_id)
    player = next(pl for pl in game.players if pl.seat == 2)
    p = deployment.find_unit(game, named["P"]["unit_id"])
    cp = player.cp
    monkeypatch.setattr(game_service.random, "randint", lambda a, b: 4)
    game_service._stratagem_targeted(player, p)
    assert player.cp == cp
    monkeypatch.setattr(game_service.random, "randint", lambda a, b: 5)
    game_service._stratagem_targeted(player, p)
    assert player.cp == cp + 1


async def test_secutor_of_olympus(client: AsyncClient, session, tmp_path, monkeypatch):
    from app.services.in_game import shooting_start

    units = {1: [("V", 1, {"keywords": ("VEHICLE",)}), ("A", 1, {})], 2: [("T", 1, {})]}
    spots = {"V": (20, 38), "A": (40, 38), "T": (20, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    t, v, a = (_unit_named(deployment_, n) for n in "TVA")
    model = await _model_of(session, t)
    model.abilities.append(DatasheetAbility(name="Secutor of Olympus", description="Secutor"))
    await session.commit()
    # Out of the movement phase: not yet.
    assert (await client.get(f"/games/{game_id}/shooting-start")).json() == []
    # V within 12" of Thulia; A isn't a VEHICLE.
    await _place(session, v, [(20, 14)])
    await _place(session, a, [(24, 8)])
    await client.post(f"/games/{game_id}/advance")
    [ability] = (await client.get(f"/games/{game_id}/shooting-start")).json()
    assert (ability["ability"], [x["unit_id"] for x in ability["targets"]]) == (
        "Secutor of Olympus", [v["unit_id"]]
    )
    payload = {"unit_id": t["unit_id"], "ability": "Secutor of Olympus"}
    response = await client.post(
        f"/games/{game_id}/shooting-start", json={**payload, "target_unit_id": a["unit_id"]}
    )
    assert "VEHICLE" in response.json()["detail"]
    # Every die a 4: on a 2+, D3+1 (4+1) mortal wounds - V's 2 wounds gone.
    monkeypatch.setattr(shooting_start.random, "randint", lambda lo, hi: 4)
    response = await client.post(
        f"/games/{game_id}/shooting-start", json={**payload, "target_unit_id": v["unit_id"]}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["roll"], result["wounds"]) == (4, 5)
    assert result["destroyed_unit_model_ids"] == [v["models"][0]["unit_model_id"]]
    game_ = await _load_game(session, game_id)
    [destroyed] = game_.models_destroyed
    assert destroyed.destroyed_by_unit_id == t["unit_id"]
    # Once a phase.
    assert (await client.get(f"/games/{game_id}/shooting-start")).json() == []
