from httpx import AsyncClient

from app.routers.games import _load_game
from app.services.in_game import deployment, reinforcements
from tests.test_deployment import _deployment, _game, _unit_named
from tests.test_fighting import BLADE, _fight_state, _to_fight
from tests.test_reinforcements import _declare
from tests.test_unit_effects import _give_sm

# Abilities used as battle formations are declared (Thunderhawk Insertion:
# one GRAVIS/PHOBOS/TACTICUS unit has Deep Strike - see
# app/services/in_game/battle_formations.py) and when a unit's selected to
# fight (Banner of Macragge: once a battle, for the army, +1 A and S - see
# app/services/in_game/fight_abilities.py).


async def test_thunderhawk_insertion(client: AsyncClient, session, tmp_path):
    units = {
        1: [("Calgar", 1, {}), ("T", 1, {"keywords": ("TACTICUS",)}), ("X", 1, {})],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    named = {n: _unit_named(await _deployment(client, game_id), n) for n in ("Calgar", "T", "X")}
    await _give_sm(session, named["Calgar"], ["Thunderhawk Insertion"])
    formations = (await client.get(f"/games/{game_id}/formations")).json()
    [grant] = next(p for p in formations["players"] if p["seat"] == 1)["grants"]
    assert (grant["ability"], grant["grants"], grant["unit_id"]) == (
        "Thunderhawk Insertion", "Deep Strike", None
    )
    assert [t["name"] for t in grant["targets"]] == ["T"]

    def payload(unit):
        return {"seat": 1, "source_unit_id": named["Calgar"]["unit_id"],
                "ability": "Thunderhawk Insertion", "unit_id": unit["unit_id"]}

    response = await client.post(f"/games/{game_id}/formations/grant", json=payload(named["X"]))
    assert "GRAVIS/PHOBOS/TACTICUS" in response.json()["detail"]
    decision = (await client.get(f"/games/{game_id}/agent")).json()
    assert any(a["type"] == "grant_formation" for a in decision["actions"])
    response = await client.post(f"/games/{game_id}/formations/grant", json=payload(named["T"]))
    assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    assert reinforcements.has_deep_strike(deployment.find_unit(game, named["T"]["unit_id"]), game)
    assert not reinforcements.has_deep_strike(deployment.find_unit(game, named["X"]["unit_id"]), game)
    # (Agents choose it once.)
    decision = (await client.get(f"/games/{game_id}/agent")).json()
    assert not any(a["type"] == "grant_formation" for a in decision["actions"])
    # Declared: it stays as chosen.
    await _declare(client, game_id, 1)
    response = await client.post(f"/games/{game_id}/formations/grant", json=payload(named["T"]))
    assert response.status_code == 400


async def test_banner_of_macragge_once_a_battle_for_the_army(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Seat 2's D and E both have the Banner: D uses it (its 1-attack blade
    # makes 2); then it's used up for seat 2's army - E can't.
    units = {1: [("A", 1, BLADE), ("B", 1, BLADE)], 2: [("D", 1, BLADE), ("E", 1, BLADE)]}
    places = {"D": [(20, 4)], "A": [(20, 6)], "E": [(40, 4)], "B": [(40, 6)]}
    game_id, deployment_ = await _to_fight(client, session, tmp_path, monkeypatch, units, places)
    a, b, d, e = (_unit_named(deployment_, n) for n in "ABDE")
    for unit in (d, e):
        await _give_sm(session, unit, ["Banner of Macragge"])
    state = await _fight_state(client, game_id)
    assert {u["name"]: u["abilities"] for u in state["units"]}["D"] == ["Banner of Macragge"]
    decision = (await client.get(f"/games/{game_id}/agent")).json()
    assert any(a.get("params", {}).get("abilities") for a in decision["actions"])

    async def fight(unit, target, abilities):
        targets = (await client.get(f"/games/{game_id}/fight/targets?unit_id={unit['unit_id']}")).json()
        [entry] = [t for t in targets if t["unit_id"] == target["unit_id"]]
        return await client.post(f"/games/{game_id}/fight", json={
            "unit_id": unit["unit_id"], "target_unit_id": target["unit_id"],
            "weapon_ids": [w["id"] for w in entry["weapons"] if w["default"]],
            "abilities": abilities,
        })

    response = await fight(d, a, ["Banner of Macragge"])
    assert response.status_code == 200, response.text
    assert len(response.json()["combat"]["attack_rolls"]) == 2
    assert (await fight(b, e, [])).status_code == 200
    state = await _fight_state(client, game_id)
    assert {u["name"]: u["abilities"] for u in state["units"]}["E"] == []
    response = await fight(e, b, ["Banner of Macragge"])
    assert "can't use Banner of Macragge" in response.json()["detail"]
