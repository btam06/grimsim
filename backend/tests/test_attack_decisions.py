from httpx import AsyncClient

from app.seeds.factions.adeptus_mechanicus import saves as admech_saves
from tests import live_games
from tests.test_acts_of_faith import _enhancement, _list_detachment
from tests.test_deployment import _unit_named
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place

# The defender's decisions as an attack's made against their unit (see
# app/services/in_game/attack_decisions.py) - here Artisan and Necromechanic
# (app/seeds/factions/adeptus_mechanicus/saves.py); Acts of Faith for saves
# are in test_acts_of_faith.py. Seat 1's A (3 models) shoots seat 2's D
# (3 models, 1 wound each) in seat 1's first shooting phase.

HITS_AND_WOUNDS = [4] * 6
FAILED_SAVES = [1] * 10


async def _game(client, session, tmp_path, monkeypatch, enhancement, keywords=("LEGIO CYBERNETICA",)):
    units = {
        1: [("A", 3, {"weapon_range": 24})],
        2: [("D", 3, {"keywords": keywords, "weapon_range": 24})],
    }
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    detachment = await _list_detachment(session, game_id, "Detachment")
    await _enhancement(session, d, enhancement, detachment)
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    await _advance_to(client, game_id, 1, 1, "shooting")
    # Hits and wounds on 4s, saves fail on 1s - the same rolls each time the
    # attack's made (again, as each decision's made).
    rolls: list[int] = []
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: rolls.pop(0))
    targets = (
        await client.get(f"/games/{game_id}/shooting/targets?unit_id={a['unit_id']}")
    ).json()
    weapon_ids = [w["id"] for t in targets if t["unit_id"] == d["unit_id"] for w in t["weapons"]]

    async def shoot():
        rolls[:] = HITS_AND_WOUNDS + FAILED_SAVES
        return await client.post(
            f"/games/{game_id}/shooting",
            json={"unit_id": a["unit_id"], "target_unit_id": d["unit_id"], "weapon_ids": weapon_ids},
        )

    async def decide(choice, seat=2):
        rolls[:] = HITS_AND_WOUNDS + FAILED_SAVES
        return await client.post(
            f"/games/{game_id}/attack-decision", json={"seat": seat, "choice": choice}
        )

    return game_id, shoot, decide


async def test_necromechanic_makes_a_failed_saves_damage_0(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, shoot, decide = await _game(
        client, session, tmp_path, monkeypatch, admech_saves.NECROMECHANIC
    )
    response = await shoot()
    assert response.status_code == 200, response.text
    pending = response.json()["pending"]
    assert pending["type"] == "failed_save" and pending["seat"] == 2
    assert [o["id"] for o in pending["options"]] == ["necromechanic", "decline"]
    response = await decide("necromechanic")
    assert response.status_code == 200, response.text
    shot = response.json()["shot"]
    # (Once a battle round: the other two failed saves aren't asked about.)
    assert shot["pending"] is None
    combat = shot["combat"]
    assert combat["total_damage"] == 2
    assert any("Necromechanic" in c for c in combat["choices"])
    game = live_games.game(game_id)
    assert [u.ability for u in game.ability_uses] == [admech_saves.NECROMECHANIC]


async def test_declining_isnt_asked_again_for_the_weapon(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, shoot, decide = await _game(
        client, session, tmp_path, monkeypatch, admech_saves.NECROMECHANIC
    )
    await shoot()
    response = await decide("decline")
    shot = response.json()["shot"]
    assert shot["pending"] is None
    assert shot["combat"]["total_damage"] == 3
    assert live_games.game(game_id).ability_uses == []


async def test_necromechanic_only_for_legio_cybernetica_or_vehicles(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    _, shoot, _ = await _game(
        client, session, tmp_path, monkeypatch, admech_saves.NECROMECHANIC,
        keywords=("ADEPTUS MECHANICUS",),
    )
    response = await shoot()
    assert response.json()["pending"] is None
    assert response.json()["combat"]["total_damage"] == 3


async def test_artisan_changes_a_failed_save_to_a_6(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # (As if its bearer's leading it, within range of the Acquisition
    # objective marker.)
    monkeypatch.setattr(admech_saves.enhancement_rules, "is_leading", lambda unit, m: True)
    monkeypatch.setattr(
        admech_saves.selected_objectives, "unit_within", lambda game, unit, name, seat=None: True
    )
    game_id, shoot, decide = await _game(
        client, session, tmp_path, monkeypatch, admech_saves.ARTISAN
    )
    response = await shoot()
    pending = response.json()["pending"]
    assert [o["id"] for o in pending["options"]] == ["artisan", "decline"]
    # Nothing else happens while it waits.
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 409
    response = await decide("artisan")
    shot = response.json()["shot"]
    # (Once a phase.)
    assert shot["pending"] is None
    combat = shot["combat"]
    assert sorted(combat["save_rolls"]) == [1, 1, 6]
    assert combat["total_damage"] == 2
    assert any("Artisan" in c for c in combat["choices"])


async def test_artisan_needs_the_acquisition_objective_marker(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    monkeypatch.setattr(admech_saves.enhancement_rules, "is_leading", lambda unit, m: True)
    _, shoot, _ = await _game(client, session, tmp_path, monkeypatch, admech_saves.ARTISAN)
    response = await shoot()
    assert response.json()["pending"] is None
    assert response.json()["combat"]["total_damage"] == 3
