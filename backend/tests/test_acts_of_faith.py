from httpx import AsyncClient
from sqlalchemy import select

from app.models import ArmyList, Faction, FactionAbility
from app.routers.games import _load_game
from app.seeds.factions.adepta_sororitas import abilities as sororitas_abilities
from app.seeds.factions.adepta_sororitas import acts_of_faith
from app.services.in_game import casualties, deployment
from tests import live_games
from tests.test_deployment import _deployment, _unit_named
from tests.test_dread import _model, _rule_test
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place, _to_shooting

# Acts of Faith (see app/seeds/factions/adepta_sororitas/acts_of_faith.py).
# Games on the test layout, in seat 2's first movement phase: seat 2's army
# is made Adepta Sororitas, its unit "D" an ADEPTA SORORITAS unit with the
# ability.

SORORITAS = {"keywords": ("ADEPTA SORORITAS",), "weapon_range": 24}


async def _sororitas_army(session, game_id, seat=2):
    # Makes the seat's Army Faction Adepta Sororitas.
    player = live_games.player(game_id, seat)
    army_list = await session.get(ArmyList, player.list_id)
    faction = (
        await session.execute(select(Faction).where(Faction.name == acts_of_faith.FACTION))
    ).scalar_one_or_none()
    if faction is None:
        faction = Faction(name=acts_of_faith.FACTION)
        session.add(faction)
        await session.flush()
    army_list.faction_id = faction.id
    await session.commit()
    return faction


async def _give_ability(session, unit, faction):
    text = next(e[1] for e in sororitas_abilities.ENTRIES if e[0] == acts_of_faith.ACTS_OF_FAITH)
    model = await _model(session, unit)
    model.faction_abilities.append(
        FactionAbility(name=acts_of_faith.ACTS_OF_FAITH, description=text, faction=faction)
    )
    await session.commit()


async def _sororitas_game(client, session, tmp_path, d_kwargs=None, a_kwargs=None, ability=True):
    units = {
        1: [("A", 3, {"weapon_range": 24, **(a_kwargs or {})})],
        2: [("D", 3, {**SORORITAS, **(d_kwargs or {})})],
    }
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    faction = await _sororitas_army(session, game["id"])
    if ability:
        await _give_ability(session, d, faction)
    return game["id"], a, d


def _pool(game_id, seat=2, values=None):
    player = live_games.player(game_id, seat)
    if values is not None:
        player.miracle_dice[:] = values
    return player.miracle_dice


async def _player_out(client, game_id, seat=2):
    game = (await client.get(f"/games/{game_id}")).json()
    return next(p for p in game["players"] if p["seat"] == seat)


# --- gaining Miracle dice ---


async def test_a_miracle_dice_at_the_start_of_each_turn(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    assert _pool(game_id) == []
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 5)
    # The opponent's turn starts: the Adepta Sororitas player still gains one.
    await _advance_to(client, game_id, 1, 1, "command")
    assert _pool(game_id) == [5]
    assert _pool(game_id, seat=1) == []
    out = await _player_out(client, game_id)
    assert (out["acts_of_faith"], out["miracle_dice"]) == (True, [5])
    assert not (await _player_out(client, game_id, seat=1))["acts_of_faith"]
    # And their own next turn.
    await _advance_to(client, game_id, 2, 2, "command")
    assert _pool(game_id) == [5, 5]


async def test_a_miracle_dice_when_a_sororitas_unit_is_destroyed(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 3)
    # Losing models isn't enough: only the whole unit.
    casualties.mortal_wounds(game, unit, 2)
    assert _pool(game_id) == []
    casualties.mortal_wounds(game, unit, 10)
    assert _pool(game_id) == [3]
    assert [(g.reason, g.unit_id) for g in game.miracle_gains] == [
        (acts_of_faith.UNIT_DESTROYED, d["unit_id"])
    ]


async def test_no_miracle_dice_for_other_units_or_armies(
    client: AsyncClient, session, tmp_path
):
    # The enemy's unit destroyed: nothing for either player.
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    casualties.mortal_wounds(game, deployment.find_unit(game, a["unit_id"]), 10)
    assert _pool(game_id) == [] and _pool(game_id, seat=1) == []


# --- performing Acts of Faith ---


async def test_an_advance_roll_with_a_miracle_dice(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    _pool(game_id, values=[6, 2])
    out = await _player_out(client, game_id)
    assert out["act_of_faith_unit_ids"] == [d["unit_id"]]
    response = await client.post(
        f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"], "miracle_die": 6}
    )
    assert response.status_code == 200, response.text
    unit = next(u for u in response.json()["units"] if u["unit_id"] == d["unit_id"])
    assert unit["advance_roll"] == 6
    assert _pool(game_id) == [2]
    # Once a phase: it's no longer offered.
    assert (await _player_out(client, game_id))["act_of_faith_unit_ids"] == []


async def test_a_miracle_dice_has_to_be_in_the_pool(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    _pool(game_id, values=[2])
    response = await client.post(
        f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"], "miracle_die": 6}
    )
    assert response.status_code == 400
    assert "no Miracle dice of 6" in response.json()["detail"]
    # Nothing rolled or spent.
    assert _pool(game_id) == [2]
    movement = (await client.get(f"/games/{game_id}/movement")).json()
    assert movement["units"][0]["advance_roll"] is None


async def test_only_units_with_the_ability(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _sororitas_game(client, session, tmp_path, ability=False)
    _pool(game_id, values=[6])
    assert (await _player_out(client, game_id))["act_of_faith_unit_ids"] == []
    response = await client.post(
        f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"], "miracle_die": 6}
    )
    assert response.status_code == 400
    assert "doesn't have Acts of Faith" in response.json()["detail"]


async def test_a_battle_shock_test_with_a_miracle_dice(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    _pool(game_id, values=[1])
    test = await _rule_test(client, game_id, d)
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 4)
    response = await client.post(
        f"/games/{game_id}/battle-shock/{test['id']}/take",
        json={"insane_bravery": False, "miracle_die": 1},
    )
    assert response.status_code == 200, response.text
    [taken] = response.json()["taken"]
    # 1 + 4 against Leadership 6+: failed.
    assert (taken["dice"], taken["passed"]) == ([1, 4], False)
    assert _pool(game_id) == []


async def test_a_hit_roll_with_a_miracle_dice(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    await _to_shooting(client, game_id)
    _pool(game_id, values=[1])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 6)
    targets = (
        await client.get(f"/games/{game_id}/shooting/targets?unit_id={d['unit_id']}")
    ).json()
    weapon_ids = [w["id"] for t in targets if t["unit_id"] == a["unit_id"] for w in t["weapons"]]
    response = await client.post(
        f"/games/{game_id}/shooting",
        json={
            "unit_id": d["unit_id"],
            "target_unit_id": a["unit_id"],
            "weapon_ids": weapon_ids,
            "miracle": {"roll": "hit", "value": 1},
        },
    )
    assert response.status_code == 200, response.text
    combat = response.json()["combat"]
    # The first Hit roll is the Miracle dice (a 1: a miss, and not re-rolled);
    # the rest are rolled.
    assert combat["attack_rolls"] == [1, 6, 6]
    assert combat["hits"] == 2
    assert len(combat["acts_of_faith"]) == 1 and "Hit roll" in combat["acts_of_faith"][0]
    assert _pool(game_id) == []


async def test_a_saving_throw_with_a_miracle_dice(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # Seat 1's A shoots D (seat 2's, Adepta Sororitas) in its own turn: D
    # saves with a Miracle dice.
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    await _advance_to(client, game_id, 1, 1, "shooting")
    _pool(game_id, values=[6, 6])
    # (4s: hits and wounds.)
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 4)
    targets = (
        await client.get(f"/games/{game_id}/shooting/targets?unit_id={a['unit_id']}")
    ).json()
    weapon_ids = [w["id"] for t in targets if t["unit_id"] == d["unit_id"] for w in t["weapons"]]
    shot = {"unit_id": a["unit_id"], "target_unit_id": d["unit_id"], "weapon_ids": weapon_ids}
    response = await client.post(f"/games/{game_id}/shooting", json=shot)
    assert response.status_code == 200, response.text
    # The shot waits on D's player: an Act of Faith for a save?
    assert response.json()["combat"] is None
    pending = response.json()["pending"]
    assert pending["type"] == "save_miracle" and pending["seat"] == 2
    assert pending["unit_id"] == d["unit_id"]
    assert [o["id"] for o in pending["options"]] == ["miracle:6", "decline"]
    assert _pool(game_id) == [6, 6]
    game = (await client.get(f"/games/{game_id}")).json()
    assert game["pending_decision"]["prompt"] == pending["prompt"]
    # Nothing else happens until they decide - and only they can.
    assert (await client.post(f"/games/{game_id}/shooting", json=shot)).status_code == 409
    response = await client.post(
        f"/games/{game_id}/attack-decision", json={"seat": 1, "choice": "miracle:6"}
    )
    assert response.status_code == 400
    response = await client.post(
        f"/games/{game_id}/attack-decision", json={"seat": 2, "choice": "miracle:6"}
    )
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["kind"] == "shoot" and out["shot"]["pending"] is None
    combat = out["shot"]["combat"]
    assert sorted(combat["save_rolls"]) == [4, 4, 6]
    assert (await client.get(f"/games/{game_id}")).json()["pending_decision"] is None
    assert "Saving throw" in combat["acts_of_faith"][0]
    assert _pool(game_id) == [6]


async def test_an_attackers_act_of_faith_is_for_its_own_rolls(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    await _to_shooting(client, game_id)
    _pool(game_id, values=[6])
    response = await client.post(
        f"/games/{game_id}/shooting",
        json={
            "unit_id": d["unit_id"],
            "target_unit_id": a["unit_id"],
            "weapon_ids": [],
            "miracle": {"roll": "save", "value": 6},
        },
    )
    assert response.status_code == 400
    assert _pool(game_id) == [6]


async def test_an_unused_miracle_dice_stays_in_the_pool(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # A Damage roll for a flat-Damage weapon: never rolled, so not spent.
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    await _to_shooting(client, game_id)
    _pool(game_id, values=[6])
    targets = (
        await client.get(f"/games/{game_id}/shooting/targets?unit_id={d['unit_id']}")
    ).json()
    weapon_ids = [w["id"] for t in targets if t["unit_id"] == a["unit_id"] for w in t["weapons"]]
    response = await client.post(
        f"/games/{game_id}/shooting",
        json={
            "unit_id": d["unit_id"],
            "target_unit_id": a["unit_id"],
            "weapon_ids": weapon_ids,
            "miracle": {"roll": "damage", "value": 6},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["combat"]["acts_of_faith"] == []
    assert _pool(game_id) == [6]
    # Still able to perform one this phase.
    assert (await _player_out(client, game_id))["act_of_faith_unit_ids"] == [d["unit_id"]]


async def test_a_charge_roll_with_a_miracle_dice(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D charges A (every rolled die a 4); one of its dice is a Miracle dice.
    from app.models import Stratagem
    from app.services.in_game import core_stratagems
    from tests.test_charging import _charge_game

    game_id, d, a = await _charge_game(client, session, tmp_path, monkeypatch)
    faction = await _sororitas_army(session, game_id)
    await _give_ability(session, d, faction)
    _pool(game_id, values=[6, 1])
    response = await client.post(
        f"/games/{game_id}/charge/roll", json={"unit_id": d["unit_id"], "miracle_die": 6}
    )
    assert response.status_code == 200, response.text
    unit = next(u for u in response.json()["units"] if u["unit_id"] == d["unit_id"])
    assert (unit["dice"], unit["roll"]) == ([6, 4], 10)
    assert _pool(game_id) == [1]
    # A roll with a Miracle dice in it can't be re-rolled (Command Re-roll).
    game = await _load_game(session, game_id)
    reroll = Stratagem(name="Command Re-roll", game_action=core_stratagems.COMMAND_REROLL)
    player = live_games.player(game_id, 2)
    unit_ = deployment.find_unit(game, d["unit_id"])
    assert core_stratagems.choices(game, player, reroll, unit_) == []


# --- the detachments' Miracle dice rules ---


async def _list_detachment(session, game_id, name, seat=2):
    # Renames the seat's list's (one) detachment `name`; it.
    from app.models import Detachment

    army_list = await session.get(ArmyList, live_games.player(game_id, seat).list_id)
    await session.refresh(army_list, ["detachments"])
    detachment = army_list.detachments[0]
    detachment.name = name
    await session.commit()
    return await session.get(Detachment, detachment.id)


async def _enhancement(session, unit, name, detachment):
    from app.models import Enhancement, UnitModel

    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    await session.refresh(unit_model, ["enhancement"])
    unit_model.enhancement = Enhancement(
        name=name, detachment_id=detachment.id, kind="enhancement", points=10
    )
    await session.commit()


async def test_sacred_rites_two_acts_of_faith_a_phase(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    await _list_detachment(session, game_id, "Army of Faith")
    _pool(game_id, values=[6, 6, 6])
    test = await _rule_test(client, game_id, d)
    response = await client.post(
        f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"], "miracle_die": 6}
    )
    assert response.status_code == 200, response.text
    # A second this phase.
    assert (await _player_out(client, game_id))["act_of_faith_unit_ids"] == [d["unit_id"]]
    response = await client.post(
        f"/games/{game_id}/battle-shock/{test['id']}/take",
        json={"insane_bravery": False, "miracle_die": 6},
    )
    assert response.status_code == 200, response.text
    # But not a third.
    assert (await _player_out(client, game_id))["act_of_faith_unit_ids"] == []
    assert _pool(game_id) == [6]


async def test_saintly_example_gains_d3_more(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    detachment = await _list_detachment(session, game_id, "Hallowed Martyrs")
    await _enhancement(session, d, "Saintly Example", detachment)
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 2)
    # Its bearer (the first model, 2 wounds) destroyed: D3 (2) Miracle dice.
    casualties.mortal_wounds(game, unit, 2)
    assert _pool(game_id) == [2, 2]
    assert [g.reason for g in game.miracle_gains] == ["Saintly Example"] * 2


async def test_litanies_of_faith_at_the_start_of_the_command_phase(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    detachment = await _list_detachment(session, game_id, "Army of Faith")
    await _enhancement(session, d, "Litanies of Faith", detachment)
    # Every die a 3: a Leadership test of 6 against 6+ passes.
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 3)
    # Not at the start of the opponent's turn...
    await _advance_to(client, game_id, 1, 1, "command")
    assert _pool(game_id) == [3]
    # ...but at the start of their own Command phase.
    await _advance_to(client, game_id, 2, 2, "command")
    assert _pool(game_id) == [3, 3, 3]


async def test_triptych_of_the_macharian_crusade_saves_succeed(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D saves with a Miracle dice of 1 - and still saves.
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    detachment = await _list_detachment(session, game_id, "Army of Faith")
    await _enhancement(session, d, "Triptych of the Macharian Crusade", detachment)
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    await _advance_to(client, game_id, 1, 1, "shooting")
    _pool(game_id, values=[1])
    targets = (
        await client.get(f"/games/{game_id}/shooting/targets?unit_id={a['unit_id']}")
    ).json()
    weapon_ids = [w["id"] for t in targets if t["unit_id"] == d["unit_id"] for w in t["weapons"]]
    # Hits and wounds on 4s; saves on 1s otherwise fail - the same rolls each
    # time the attack's made (again, once D's player decides).
    rolls = []
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: rolls.pop(0))
    rolls[:] = [4] * 6 + [1] * 10
    response = await client.post(
        f"/games/{game_id}/shooting",
        json={"unit_id": a["unit_id"], "target_unit_id": d["unit_id"], "weapon_ids": weapon_ids},
    )
    assert response.json()["pending"]["type"] == "save_miracle", response.text
    rolls[:] = [4] * 6 + [1] * 10
    response = await client.post(
        f"/games/{game_id}/attack-decision", json={"seat": 2, "choice": "miracle:1"}
    )
    assert response.status_code == 200, response.text
    combat = response.json()["shot"]["combat"]
    assert sorted(combat["save_rolls"]) == [1, 1, 1]
    # Two failed saves (1 damage each); the Miracle dice's 1 saved.
    assert combat["total_damage"] == 2


async def test_divine_guidance_gains_a_miracle_dice_for_a_kill(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    from app.engine.state import GameStratagemUse, GameStratagemTarget
    from app.models import Stratagem

    game_id, a, d = await _sororitas_game(client, session, tmp_path, a_kwargs={})
    await _place(session, a, [(20 + 1.5 * i, 20) for i in range(3)])
    await _to_shooting(client, game_id)
    game = await _load_game(session, game_id)
    player = live_games.player(game_id, 2)
    stratagem = Stratagem(name="Divine Guidance", cp=1)
    use = GameStratagemUse(
        stratagem=stratagem, battle_round=game.battle_round, turn_seat=game.turn_seat,
        phase=game.phase, cp=1,
    )
    use.target_link = GameStratagemTarget(unit_id=d["unit_id"])
    player.stratagem_uses.append(use)
    unit = deployment.find_unit(game, d["unit_id"])
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: 5)
    acts_of_faith.after_attacks(game, unit, 0, fought=False)
    assert _pool(game_id) == []
    acts_of_faith.after_attacks(game, unit, 1, fought=False)
    acts_of_faith.after_attacks(game, unit, 2, fought=False)
    # Once for the use.
    assert _pool(game_id) == [5]


async def test_the_attackers_own_strength_goes_to_the_calculator(
    client: AsyncClient, session, tmp_path
):
    # (For The Blood of Martyrs.)
    from app.combat_rules.conditions import BELOW_HALF_STRENGTH, BELOW_STARTING_STRENGTH
    from app.routers.games import _attacker_positions
    from app.seeds.factions.adepta_sororitas.conditions import WITHIN_6_OF_TARGET

    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    unit, target = (deployment.find_unit(game, u["unit_id"]) for u in (d, a))
    assert not {BELOW_STARTING_STRENGTH, BELOW_HALF_STRENGTH} & set(
        _attacker_positions(game, unit, target)
    )
    casualties.mortal_wounds(game, unit, 4)
    positions = set(_attacker_positions(game, unit, target))
    assert {BELOW_STARTING_STRENGTH, BELOW_HALF_STRENGTH} <= positions
    assert WITHIN_6_OF_TARGET not in positions


# --- the detachments' combat rules ---


def _rules_combat(rules, positions, **weapon):
    from tests.test_combat import _doctrina_combat, _weapon

    return _doctrina_combat(
        _weapon(attacks="1", ap=-10, weapon_type="ranged", **weapon),
        attacker_rules=rules,
        attacker_positions=set(positions),
    )


def test_the_blood_of_martyrs(monkeypatch):
    from app.combat_rules.conditions import BELOW_HALF_STRENGTH, BELOW_STARTING_STRENGTH
    from app.seeds.factions.adepta_sororitas.datasheet_abilities import RULES

    rules = RULES["The Blood of Martyrs"]
    # A Hit roll of 3 against BS4 (hits only with +1), then a Wound roll of 3
    # with S1 against T1 (4+: wounds only with +1).
    for positions, expected in (
        ((), 0),
        ((BELOW_STARTING_STRENGTH,), 0),
        ((BELOW_STARTING_STRENGTH, BELOW_HALF_STRENGTH), 1),
    ):
        rolls = iter([3, 3, 1])
        monkeypatch.setattr("app.services.dice.randint", lambda a, b: next(rolls, 1))
        result = _rules_combat(rules, positions, skill=4, strength=1)
        assert (result.hits, result.total_damage) == (
            (0, 0) if not positions else (1, expected)
        ), positions


def test_fervent_purgation(monkeypatch):
    from app.seeds.factions.adepta_sororitas.conditions import WITHIN_6_OF_TARGET
    from app.seeds.factions.adepta_sororitas.datasheet_abilities import ENTRIES
    from app.combat_rules import Rule

    _, _, conditions, effects = next(e for e in ENTRIES if e[0] == "Fervent Purgation")
    rules = [Rule(conditions=tuple(conditions), effects=tuple(effects))]
    # S1 against T1 wounds on 4+; +1 S (S2: double T1) on 2+. A Wound roll of 3.
    for positions, damage in (((), 0), ((WITHIN_6_OF_TARGET,), 1)):
        rolls = iter([6, 3, 1])
        monkeypatch.setattr("app.services.dice.randint", lambda a, b: next(rolls, 1))
        assert _rules_combat(rules, positions, strength=1).total_damage == damage, positions


def test_symphonic_payload_rerolls_a_low_attacks_roll(monkeypatch):
    from app.seeds.factions.adepta_sororitas.datasheet_abilities import ENTRIES
    from app.combat_rules import Rule
    from tests.test_combat import _doctrina_combat, _weapon

    _, _, conditions, effects = next(e for e in ENTRIES if e[0] == "Symphonic Payload")
    rules = [Rule(conditions=tuple(conditions), effects=tuple(effects))]
    # A D6 for its Attacks, then 6s.
    for first, with_rule, attacks in ((1, False, 1), (1, True, 5), (4, True, 4)):
        rolls = iter([first, 5])
        monkeypatch.setattr("app.services.dice.randint", lambda a, b: next(rolls, 6))
        result = _doctrina_combat(
            _weapon(attacks="D6", ap=-10, weapon_type="ranged"),
            attacker_rules=rules if with_rule else [],
        )
        assert len(result.attack_rolls) == attacks, (first, with_rule)
        assert bool(result.choices) == (with_rule and first == 1)
