from httpx import AsyncClient

from app.models import DatasheetAbility, GameModelDamage, Wargear, WargearAbility
from app.routers.games import _load_game
from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech_datasheets
from app.seeds.factions.adeptus_mechanicus import vengeance
from app.services.in_game import battle_shock, casualties, deployment, reactive_move, repair
from app.services.in_game import game as game_service
from app.services.in_game import shooting
from tests.test_deployment import _unit_named
from tests.test_movement import _battle, _move
from tests.test_shooting import _place
from tests.test_space_marine_units import _model_of
from tests.test_space_marines import _applies

# The Skitarii Marshal's, Tech-priest Enginseer's and Serberys Raiders'
# rules. Games are in seat 2's first movement phase (see
# tests/test_movement.py _battle).

BATTLELINE = ("ADEPTUS MECHANICUS", "BATTLELINE")


async def _give(session, unit, *names):
    model = await _model_of(session, unit)
    for name in names:
        model.abilities.append(DatasheetAbility(name=name, description=name))
    await session.commit()


def test_control_edict_while_leading():
    rules = admech_datasheets.RULES["Control Edict"]
    leading = {"attacker_unit_model_keywords": [{"CHARACTER"}, {"SKITARII"}]}
    alone = {"attacker_unit_model_keywords": [{"CHARACTER"}]}
    assert _applies(rules, {**leading, "step": "hit"})
    assert not _applies(rules, alone)


async def test_tactica_obliqua(client: AsyncClient, session, tmp_path, monkeypatch):
    units = {
        1: [("R", 1, {}), ("B", 1, {"keywords": BATTLELINE})],
        2: [("D", 1, {})],
    }
    spots = {"R": (20, 34), "B": (26, 38), "D": (20, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    r, b, d = (_unit_named(deployment_, n) for n in "RBD")
    await _give(session, r, "Tactica Obliqua")
    assert (await client.get(f"/games/{game_id}/reactive-moves")).json() == []
    # D ends a move within 8" of R.
    await _place(session, d, [(20, 25)])
    response = await _move(client, game_id, d, "normal", [
        {"unit_model_id": d["models"][0]["unit_model_id"], "x": 20, "y": 26}
    ])
    assert response.status_code == 200, response.text
    [move] = (await client.get(f"/games/{game_id}/reactive-moves")).json()
    assert (move["unit_id"], move["ability"], move["roll"], move["trigger_name"]) == (
        r["unit_id"], "Tactica Obliqua", None, "D"
    )

    monkeypatch.setattr(reactive_move.random, "randint", lambda a, b: 3)
    [move] = (
        await client.post(f"/games/{game_id}/reactive-moves/roll", json={"unit_id": r["unit_id"]})
    ).json()
    assert (move["roll"], move["further"]) == (3, 6.0)
    model = r["models"][0]["unit_model_id"]

    async def check(x, y):
        payload = {"unit_id": r["unit_id"], "positions": [{"unit_model_id": model, "x": x, "y": y}]}
        return (await client.post(f"/games/{game_id}/reactive-moves/check", json=payload)).json()

    # Up to its 3"; or up to 6", ending wholly within 6" of B.
    assert (await check(20, 37))["valid"]
    assert not (await check(15, 37))["valid"]
    assert (await check(25, 36.5))["valid"]
    response = await client.post(
        f"/games/{game_id}/reactive-moves",
        json={"unit_id": r["unit_id"], "positions": [{"unit_model_id": model, "x": 20, "y": 37}]},
    )
    assert response.status_code == 200, response.text
    # Once a phase.
    assert (await client.get(f"/games/{game_id}/reactive-moves")).json() == []


async def test_servo_skull_uplink(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("M", 1, {}), ("S", 1, {"keywords": ("SKITARII",)})]}
    spots = {"A": (20, 38), "M": (20, 4), "S": (24, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    m, s = (_unit_named(deployment_, n) for n in "MS")
    await _give(session, m, "Servo-skull Uplink")
    # Nothing Battle-shocked: nothing to rally.
    [rally] = (await client.get(f"/games/{game_id}/rallies")).json()
    assert rally["targets"] == []
    game_ = await _load_game(session, game_id)
    battle_shock.battle_shock_outright(game_, deployment.find_unit(game_, s["unit_id"]), "test", 1)
    await session.commit()
    [rally] = (await client.get(f"/games/{game_id}/rallies")).json()
    assert [t["unit_id"] for t in rally["targets"]] == [s["unit_id"]]
    response = await client.post(
        f"/games/{game_id}/rallies",
        json={"unit_id": m["unit_id"], "ability": "Servo-skull Uplink", "target_unit_id": s["unit_id"]},
    )
    assert response.status_code == 200, response.text
    session.expire_all()
    game_ = await _load_game(session, game_id)
    assert not battle_shock.is_battle_shocked(game_, deployment.find_unit(game_, s["unit_id"]))
    # Once per battle.
    assert (await client.get(f"/games/{game_id}/rallies")).json() == []


async def test_omnissiahs_blessing_and_vengeance(client: AsyncClient, session, tmp_path):
    vehicle = ("ADEPTUS MECHANICUS", "VEHICLE")
    units = {
        1: [("A", 1, {})],
        2: [("E", 1, {"melee": True}), ("V", 1, {"keywords": vehicle}), ("W", 1, {"keywords": vehicle})],
    }
    spots = {"A": (20, 38), "E": (20, 4), "V": (23, 4), "W": (40, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_id = game["id"]
    e, v, w = (_unit_named(deployment_, n) for n in "EVW")
    await _give(session, e, "Omnissiah's Blessing", "Vengeance for the Omnissiah")
    # Back to seat 2's Command phase, with V wounded.
    game_ = await _load_game(session, game_id)
    game_.phase = "command"
    v_model = v["models"][0]["unit_model_id"]
    game_.model_damage.append(GameModelDamage(unit_model_id=v_model, wounds_lost=1, destroyed=False))
    await session.commit()
    [blessing] = (await client.get(f"/games/{game_id}/repairs")).json()
    # ADEPTUS MECHANICUS models within 3": V, not W (nor E, which isn't one here).
    assert [t["unit_model_id"] for t in blessing["targets"]] == [v_model]
    response = await client.post(
        f"/games/{game_id}/repairs",
        json={"unit_id": e["unit_id"], "ability": "Omnissiah's Blessing", "unit_model_id": v_model},
    )
    assert response.status_code == 200, response.text
    session.expire_all()
    game_ = await _load_game(session, game_id)
    assert casualties.damage(game_)[v_model].wounds_lost == 0
    # A VEHICLE: Feel No Pain 5+ until seat 2's next Command phase.
    rules = repair.model_rules(game_, deployment.find_unit(game_, v["unit_id"]))
    assert rules[v_model][0].effects == ("feel_no_pain_5",)
    # Once a Command phase.
    assert (await client.get(f"/games/{game_id}/repairs")).json() == []

    # Vengeance: W, more than 12" from E, destroyed - nothing; V, within 12" - E avenges.
    e_unit = deployment.find_unit(game_, e["unit_id"])
    for victim, avenged in ((w, False), (v, True)):
        casualties.mortal_wounds(game_, deployment.find_unit(game_, victim["unit_id"]), 10)
        assert vengeance.active(game_, e_unit) == avenged
    rule = admech_datasheets.RULES["Vengeance for the Omnissiah"]
    axe = {"step": "pre_weapon", "weapon_name": "Omnissian axe"}
    assert _applies(rule, {**axe, "attacker_positions": {"vengeance_for_the_omnissiah"}})
    assert not _applies(rule, axe)


async def test_enginseer_lone_operative_unless_leading(client: AsyncClient, session, tmp_path):
    units = {
        1: [("A", 1, {})],
        2: [("E", 1, {"keywords": ("CHARACTER",)}), ("V", 1, {"keywords": ("ADEPTUS MECHANICUS", "VEHICLE")})],
    }
    spots = {"A": (20, 38), "E": (20, 4), "V": (23, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    e = _unit_named(deployment_, "E")
    await _give(session, e, "Enginseer")
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, e["unit_id"])
    # Within 3" of V: Lone Operative; V moved away, not.
    assert shooting.lone_operative(game_, unit)
    v = deployment.find_unit(game_, _unit_named(deployment_, "V")["unit_id"])
    deployment.positions(game_)[v.unit_models[0].id].x = 40
    assert not shooting.lone_operative(game_, unit)
    assert admech_datasheets.CONDITIONAL_LONE_OPERATIVE["Enginseer"][2] is True


def test_leading_a_unit():
    from types import SimpleNamespace

    def model(*keywords):
        kws = [SimpleNamespace(name=k) for k in keywords]
        return SimpleNamespace(model=SimpleNamespace(keywords=kws))

    unit = lambda *models: SimpleNamespace(unit_models=list(models))  # noqa: E731
    assert shooting.leading(unit(model("CHARACTER"), model("INFANTRY")))
    assert not shooting.leading(unit(model("CHARACTER")))
    assert not shooting.leading(unit(model("INFANTRY"), model("INFANTRY")))


async def test_enhanced_data_tether(client: AsyncClient, session, tmp_path, monkeypatch):
    units = {1: [("A", 1, {})], 2: [("R", 1, {})]}
    game, deployment_ = await _battle(
        client, session, tmp_path, units=units, spots={"A": (20, 38), "R": (20, 4)}
    )
    r = _unit_named(deployment_, "R")
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import UnitModel

    unit_model = (
        await session.execute(
            select(UnitModel)
            .options(selectinload(UnitModel.wargear))
            .where(UnitModel.id == r["models"][0]["unit_model_id"])
        )
    ).scalar_one()
    gear = Wargear(name="Enhanced data-tether", model_id=unit_model.model_id)
    gear.abilities = [WargearAbility(name="Enhanced data-tether", description="tether")]
    unit_model.wargear.append(gear)
    await session.commit()
    session.expire_all()
    game_ = await _load_game(session, game["id"])
    player = next(p for p in game_.players if p.seat == 2)
    cp = player.cp
    monkeypatch.setattr(game_service.random, "randint", lambda a, b: 5)
    game_service._stratagem_targeted(player, deployment.find_unit(game_, r["unit_id"]))
    assert player.cp == cp + 1


def test_omnissiahs_blessing_in_the_calculator():
    # Army-wide: picked for a defending unit in a list with an Enginseer, its
    # VEHICLE models have Feel No Pain 5+ (others don't).
    from app.seeds import datasheet_abilities as datasheet_ability_seeds
    from tests.test_space_marines import _applies

    option = datasheet_ability_seeds.OPTIONS["Omnissiah's Blessing"]["Omnissiah's Blessing"]
    assert option.army_wide
    assert {r.side for r in option.rules} == {"defender"}
    assert _applies(option.rules, {"target_model_keywords": {"VEHICLE", "ADEPTUS MECHANICUS"}})
    assert not _applies(option.rules, {"target_model_keywords": {"INFANTRY"}})
