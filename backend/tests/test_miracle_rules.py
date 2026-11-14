from httpx import AsyncClient

from app.engine.state import GameStratagemUse
from app.models import Stratagem
from app.routers.games import _load_game
from app.seeds.factions.adepta_sororitas import miracle_rules
from app.services.combat import WeaponBonus
from app.services.in_game import casualties, deployment, stratagem_actions
from tests import live_games
from tests.test_acts_of_faith import (
    SORORITAS,
    _enhancement,
    _give_ability,
    _list_detachment,
    _pool,
    _sororitas_army,
    _sororitas_game,
)
from tests.test_deployment import _unit_named
from tests.test_dread import _rule_test
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to

# The rules that discard or re-roll Miracle dice (see
# app/seeds/factions/adepta_sororitas/miracle_rules.py). Games on the test
# layout: seat 2's army is Adepta Sororitas; its unit "D" (3 models, 2 W) is
# ADEPTA SORORITAS with Acts of Faith; seat 2 goes first.


def _dice(monkeypatch, *values):
    rolls = iter(values)
    monkeypatch.setattr("app.services.dice.randint", lambda lo, hi: next(rolls))


async def _state(client, game_id, seat=2):
    response = await client.get(f"/games/{game_id}/miracle-dice")
    assert response.status_code == 200, response.text
    return next(p for p in response.json() if p["seat"] == seat)


async def _with(client, session, tmp_path, enhancement, detachment="Hallowed Martyrs"):
    game_id, a, d = await _sororitas_game(client, session, tmp_path)
    taken = await _list_detachment(session, game_id, detachment)
    await _enhancement(session, d, enhancement, taken)
    return game_id, a, d


# --- Manual of Saint Griselda ---


async def test_the_manual_at_the_start_of_the_command_phase(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d = await _with(
        client, session, tmp_path, miracle_rules.MANUAL, "Bringers of Flame"
    )
    # Not in the movement phase.
    assert not (await _state(client, game_id))["manual"]
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[3, 2, 5])
    assert (await _state(client, game_id))["manual"]
    response = await client.post(
        f"/games/{game_id}/miracle-dice/manual", json={"seat": 2, "values": [3, 2]}
    )
    assert response.status_code == 200, response.text
    assert sorted(_pool(game_id)) == [5, 5]
    # Once a phase.
    response = await client.post(
        f"/games/{game_id}/miracle-dice/manual", json={"seat": 2, "values": [5]}
    )
    assert response.status_code == 400


async def test_the_manual_sum_is_at_most_6(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _with(
        client, session, tmp_path, miracle_rules.MANUAL, "Bringers of Flame"
    )
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[4, 5])
    response = await client.post(
        f"/games/{game_id}/miracle-dice/manual", json={"seat": 2, "values": [4, 5]}
    )
    assert response.status_code == 200, response.text
    assert _pool(game_id) == [6]


async def test_the_manual_is_too_late_after_a_battle_shock_test(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d = await _with(
        client, session, tmp_path, miracle_rules.MANUAL, "Bringers of Flame"
    )
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[3, 2])
    test = await _rule_test(client, game_id, d)
    await client.post(
        f"/games/{game_id}/battle-shock/{test['id']}/take", json={"insane_bravery": False}
    )
    state = await _state(client, game_id)
    assert not state["manual"]
    assert "start of the Command phase has passed" in state["manual_reason"]


async def test_dice_not_in_the_pool_cant_be_discarded(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _with(
        client, session, tmp_path, miracle_rules.MANUAL, "Bringers of Flame"
    )
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[3])
    response = await client.post(
        f"/games/{game_id}/miracle-dice/manual", json={"seat": 2, "values": [3, 3]}
    )
    assert response.status_code == 400
    assert _pool(game_id) == [3]


# --- Chaplet of Sacrifice ---


async def test_the_chaplet_at_the_end_of_the_command_phase(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _with(client, session, tmp_path, miracle_rules.CHAPLET)
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[1, 2, 3])
    # At full strength: 1 dice.
    assert (await _state(client, game_id))["chaplet"] == 1
    _dice(monkeypatch, 6)
    response = await client.post(
        f"/games/{game_id}/miracle-dice/chaplet", json={"seat": 2, "values": [1]}
    )
    assert response.status_code == 200, response.text
    assert sorted(_pool(game_id)) == [2, 3, 6]
    # The end of the phase: no more Acts of Faith in it.
    test = await _rule_test(client, game_id, d)
    response = await client.post(
        f"/games/{game_id}/battle-shock/{test['id']}/take",
        json={"insane_bravery": False, "miracle_die": 6},
    )
    assert response.status_code == 400
    assert "Chaplet" in response.json()["detail"]


async def test_the_chaplet_rerolls_3_below_starting_strength(
    client: AsyncClient, session, tmp_path
):
    game_id, a, d = await _with(client, session, tmp_path, miracle_rules.CHAPLET)
    await _advance_to(client, game_id, 2, 2, "command")
    # Its last model (not the bearer, the first) destroyed.
    live_games.damage(game_id, d["models"][2]["unit_model_id"], wounds_lost=2, destroyed=True)
    live_games.remove_position(d["models"][2]["unit_model_id"], game_id)
    _pool(game_id, values=[1, 2, 3, 4])
    assert (await _state(client, game_id))["chaplet"] == 3
    response = await client.post(
        f"/games/{game_id}/miracle-dice/chaplet", json={"seat": 2, "values": [1, 2, 3, 4]}
    )
    assert response.status_code == 400


async def test_the_chaplet_waits_for_battle_shock_tests(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _with(client, session, tmp_path, miracle_rules.CHAPLET)
    await _advance_to(client, game_id, 2, 2, "command")
    _pool(game_id, values=[1])
    await _rule_test(client, game_id, d)
    state = await _state(client, game_id)
    assert state["chaplet"] == 0 and "Battle-shock" in state["chaplet_reason"]


# --- Psalm of Righteous Judgement ---


async def test_the_psalm_is_offered_when_a_penitent_unit_destroys_one(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _sororitas_game(
        client, session, tmp_path, d_kwargs={"keywords": ("ADEPTA SORORITAS", "PENITENT")}
    )
    taken = await _list_detachment(session, game_id, "Penitent Host")
    await _enhancement(session, d, miracle_rules.PSALM, taken)
    game = await _load_game(session, game_id)
    _pool(game_id, values=[1, 2])
    enemy, penitent = (deployment.find_unit(game, u["unit_id"]) for u in (a, d))
    casualties.mortal_wounds(game, enemy, 10, destroyed_by=penitent)
    [offer] = (await _state(client, game_id))["offers"]
    assert (offer["rule"], offer["unit_name"]) == (miracle_rules.PSALM, "A")
    response = await client.post(
        f"/games/{game_id}/miracle-dice/psalm",
        json={"seat": 2, "offer_id": offer["id"], "value": 1},
    )
    assert response.status_code == 200, response.text
    assert sorted(_pool(game_id)) == [2, 6]
    assert response.json()[0]["offers"] == []


async def test_no_psalm_for_a_unit_that_isnt_penitent(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _with(client, session, tmp_path, miracle_rules.PSALM, "Penitent Host")
    game = await _load_game(session, game_id)
    enemy, unit = (deployment.find_unit(game, u["unit_id"]) for u in (a, d))
    casualties.mortal_wounds(game, enemy, 10, destroyed_by=unit)
    assert (await _state(client, game_id))["offers"] == []


# --- Righteous Rage, Through Suffering, Strength ---


async def test_righteous_rage_discards_for_weapon_bonuses(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _with(
        client, session, tmp_path, miracle_rules.RIGHTEOUS_RAGE, "Bringers of Flame"
    )
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    _pool(game_id, values=[1, 2, 3, 4])
    # Only in the Fight phase.
    assert miracle_rules.rage_max(game, unit) == 0
    game.phase = "fight"
    assert miracle_rules.rage_max(game, unit) == 3
    miracle_rules.use_rage(game, unit, [1, 2])
    assert sorted(_pool(game_id)) == [3, 4]
    bearer = d["models"][0]["unit_model_id"]
    wounds = casualties.wounds_remaining(game, unit)
    assert miracle_rules.weapon_bonuses(game, unit, wounds) == {
        bearer: [WeaponBonus(attacks=2, strength=2)]
    }
    # Again (selected to fight again): it adds up for the phase.
    miracle_rules.use_rage(game, unit, [3])
    assert miracle_rules.weapon_bonuses(game, unit, wounds) == {
        bearer: [WeaponBonus(attacks=3, strength=3)]
    }


async def test_through_suffering_strength_while_wounded(client: AsyncClient, session, tmp_path):
    game_id, a, d = await _with(client, session, tmp_path, miracle_rules.THROUGH_SUFFERING)
    game = await _load_game(session, game_id)
    unit = deployment.find_unit(game, d["unit_id"])
    bearer = d["models"][0]["unit_model_id"]
    assert miracle_rules.weapon_bonuses(game, unit, casualties.wounds_remaining(game, unit)) == {}
    wounds = {**casualties.wounds_remaining(game, unit), bearer: 1}
    assert miracle_rules.weapon_bonuses(game, unit, wounds) == {
        bearer: [WeaponBonus(attacks=1, strength=1, damage=1)]
    }


def test_weapon_bonuses_in_combat(monkeypatch):
    from tests.test_combat import _doctrina_combat, _weapon

    # One S1 attack against T1 (4+ to wound): +2 A and +1 S (S2: 2+). Every
    # roll a 3: each hits; only with +1 S does it wound.
    monkeypatch.setattr("app.services.dice.randint", lambda a, b: 3)
    weapon = _weapon(attacks="1", skill=3, strength=1, ap=-10, weapon_type="melee", range=None)
    plain = _doctrina_combat(weapon, in_engagement_range=True)
    bonus = _doctrina_combat(weapon, in_engagement_range=True, weapon_bonuses={None: [WeaponBonus(attacks=2, strength=1, damage=1)]})
    assert (plain.hits, plain.total_damage) == (1, 0)
    # 3 attacks, each 2 damage.
    assert (bonus.hits, bonus.total_damage) == (3, 6)


# --- Divine Intervention ---


async def _character_game(client, session, tmp_path):
    # Seat 2 also has "C": a lone ADEPTA SORORITAS CHARACTER (2 W).
    units = {
        1: [("A", 3, {"weapon_range": 24})],
        2: [
            ("D", 3, SORORITAS),
            ("C", 1, {"keywords": ("ADEPTA SORORITAS", "CHARACTER"), "weapon_range": 24}),
        ],
    }
    game, deployment_ = await _battle(
        client, session, tmp_path, units=units,
        spots={"A": (20, 38), "D": (20, 4), "C": (30, 4)},
    )
    game_id = game["id"]
    faction = await _sororitas_army(session, game_id)
    c = _unit_named(deployment_, "C")
    await _give_ability(session, c, faction)
    return game_id, _unit_named(deployment_, "A"), _unit_named(deployment_, "D"), c


def _divine():
    return Stratagem(name="Divine Intervention", cp=1, game_action="divine_intervention")


async def test_divine_intervention_sets_the_character_up_again(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d, c = await _character_game(client, session, tmp_path)
    game = await _load_game(session, game_id)
    player = live_games.player(game_id, 2)
    unit = deployment.find_unit(game, c["unit_id"])
    where = live_games.position(c["models"][0]["unit_model_id"], game_id)
    x, y = where.x, where.y
    stratagem = _divine()
    # Not destroyed yet.
    assert stratagem_actions.target_reason(game, player, stratagem, unit) is not None
    casualties.mortal_wounds(game, unit, 2)
    assert stratagem_actions.target_reason(game, player, stratagem, unit) is None
    _pool(game_id, values=[6, 1, 2, 5])
    # 0-3 Miracle dice (ids one more).
    assert [ch.id for ch in stratagem_actions.choices(game, player, stratagem, unit)] == [
        1, 2, 3, 4,
    ]
    use = GameStratagemUse(stratagem=stratagem, cp=1)
    stratagem_actions.carry_out(game, player, stratagem, unit, 3, use)
    # The two lowest discarded.
    assert sorted(_pool(game_id)) == [5, 6]
    assert "D3+2" in use.outcome_link.text
    # The end of the phase: D3 (1) + 2 wounds - its W, 2.
    _dice(monkeypatch, 1)
    miracle_rules.end_of_phase(game)
    placed = live_games.position(c["models"][0]["unit_model_id"], game_id)
    assert (placed.x, placed.y) == (x, y)
    assert casualties.wounds_remaining(game, unit) == {c["models"][0]["unit_model_id"]: 2}
    # Once a battle.
    casualties.mortal_wounds(game, unit, 2)
    assert stratagem_actions.target_reason(game, player, stratagem, unit) is not None


async def test_divine_intervention_needs_the_rest_of_the_unit_gone(
    client: AsyncClient, session, tmp_path
):
    # A CHARACTER in D (leading it): destroyed while the others live.
    game_id, a, d = await _sororitas_game(
        client, session, tmp_path,
        d_kwargs={"keywords": ("ADEPTA SORORITAS", "CHARACTER")},
    )
    game = await _load_game(session, game_id)
    player = live_games.player(game_id, 2)
    unit = deployment.find_unit(game, d["unit_id"])
    casualties.mortal_wounds(game, unit, 2)
    reason = stratagem_actions.target_reason(game, player, _divine(), unit)
    assert "still on the battlefield" in reason
