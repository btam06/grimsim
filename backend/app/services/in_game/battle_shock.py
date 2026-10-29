from __future__ import annotations

import random

from fastapi import HTTPException

from app.models import (
    Game,
    GameBattleShockTest,
    GameBattleShockWounds,
    GameStratagemUse,
    Stratagem,
    Unit,
)
from app.services.in_game import casualties, deployment

# Battle-shock. A unit takes a Battle-shock test when a rule or stratagem
# makes it, and in its controller's Command phase's Battle-shock step if it's
# at half its starting strength or below, or Battle-shocked. The test: roll
# 2D6 (plus any modifier) - it's passed on a result of at least the unit's
# best Leadership (e.g. 6+). Failed, the unit is Battle-shocked: its models
# have 0 OC (see app/services/in_game/objectives.py). A Battle-shocked unit
# tests again in each of its controller's Battle-shock steps until it passes
# one, and then it's no longer Battle-shocked.
#
# A unit's starting strength is how many models it has - or, for a unit of
# one model, how many wounds it has. It's at half strength or below while
# the models it has on the battlefield (or that one model's wounds left) are
# no more than half of that.
#
# Before a test is rolled, its controller can use Insane Bravery (once per
# battle) to pass it automatically, for its CP.
#
# Rules that change this: a unit's Leadership can be worsened (Harbingers of
# Dread's auras - see app/seeds/factions/chaos_knights/dread.py), Dismay adds units to the
# Battle-shock step, Delirium makes a failed test cost D3 mortal wounds;
# Voices in the Code makes enemy units in Engagement Range test at the start
# of the Fight phase, and Executioner makes those near a unit it destroys
# test; a Super-heavy Walker crossing a ruin wall can be Battle-shocked
# outright (see `battle_shock_outright`).
#
# Tests are taken one at a time by the player whose unit it is: a test to
# take is recorded first (pending), then rolled - so the player can decide
# on Insane Bravery. The game doesn't move on while a test is pending.

BATTLE_SHOCK_STEP = "battle_shock_step"
VOICES_IN_THE_CODE = "Voices in the Code"
EXECUTIONER = "Executioner"
EXECUTIONER_RANGE = 3.0
ENGAGEMENT_RANGE = 2.0
DELIRIUM_DICE = 3
INSANE_BRAVERY = "Insane Bravery"
DICE = 2


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


# --- strength ---


def starting_strength(unit: Unit) -> int:
    models = unit.unit_models
    if len(models) == 1:
        return models[0].wounds
    return len(models)


def current_strength(game: Game, unit: Unit) -> int:
    # Models on the battlefield - or, for a unit of one model, its wounds
    # left (0 if it's destroyed).
    if len(unit.unit_models) == 1:
        return sum(casualties.wounds_remaining(game, unit).values())
    return len(deployment.models_on_battlefield(game, unit))


def below_half_strength(game: Game, unit: Unit) -> bool:
    # At half its starting strength or below (for the Battle-shock step).
    return 2 * current_strength(game, unit) <= starting_strength(unit)


def below_starting_strength(game: Game, unit: Unit) -> bool:
    return current_strength(game, unit) < starting_strength(unit)


def below_half_strength_strict(game: Game, unit: Unit) -> bool:
    # Below Half-strength, for rules that use the term: less than half its
    # starting strength.
    return 2 * current_strength(game, unit) < starting_strength(unit)


def leadership(unit: Unit) -> int:
    # The unit's best Leadership (the lowest roll that passes).
    return min(m.model.leadership for m in unit.unit_models)


def needed(game: Game, unit: Unit) -> int:
    # The roll its Battle-shock tests need: its best Leadership, worsened by
    # any rules (Deathly Terror, Despair).
    from app.seeds.factions.chaos_knights import dread

    return leadership(unit) + dread.leadership_worsened(game, unit)


# --- tests ---


def _taken(game: Game, unit: Unit) -> list[GameBattleShockTest]:
    return [t for t in game.battle_shock_tests if t.unit_id == unit.id and t.passed is not None]


def is_battle_shocked(game: Game, unit: Unit) -> bool:
    # Whether its latest test taken failed (and it's on the battlefield).
    taken = _taken(game, unit)
    return bool(taken) and taken[-1].passed is False


def battle_shocked_ids(game: Game) -> set[int]:
    latest: dict[int, bool] = {}
    for test in game.battle_shock_tests:
        if test.passed is not None:
            latest[test.unit_id] = test.passed
    return {unit_id for unit_id, passed in latest.items() if not passed}


def pending(game: Game) -> list[GameBattleShockTest]:
    # The tests waiting to be taken (by units still on the battlefield).
    placed = deployment.positions(game)
    on_battlefield = {
        unit.id
        for player in game.players
        for unit in deployment.deployable_units(player)
        if deployment.is_deployed(unit, placed)
    }
    return [
        t for t in game.battle_shock_tests if t.passed is None and t.unit_id in on_battlefield
    ]


def require(game: Game, unit: Unit, reason: str, modifier: int = 0) -> GameBattleShockTest:
    # The unit must take a Battle-shock test (e.g. a rule or stratagem makes
    # it): recorded, for its controller to take.
    if game.status != "in_progress":
        raise _bad_request("the game isn't in progress")
    if not deployment.is_deployed(unit, deployment.positions(game)):
        raise _bad_request("that unit isn't on the battlefield")
    if any(t.unit_id == unit.id for t in pending(game)):
        raise _bad_request("that unit already has a Battle-shock test to take")
    if reason != BATTLE_SHOCK_STEP and is_battle_shocked(game, unit):
        raise _bad_request("that unit is already Battle-shocked")
    test = GameBattleShockTest(
        unit_id=unit.id,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        phase=game.phase,
        reason=reason,
        modifier=modifier,
        insane_bravery=False,
    )
    game.battle_shock_tests.append(test)
    return test


def battle_shock_step(game: Game) -> None:
    # The Battle-shock step of the Command phase: each of the player whose
    # turn it is's units on the battlefield that's at half strength or below,
    # or Battle-shocked, must take a test (once a phase).
    if any(
        t.reason == BATTLE_SHOCK_STEP
        and t.battle_round == game.battle_round
        and t.turn_seat == game.turn_seat
        for t in game.battle_shock_tests
    ):
        return
    from app.seeds.factions.chaos_knights import dread

    player = next(p for p in game.players if p.seat == game.turn_seat)
    placed = deployment.positions(game)
    for unit in deployment.deployable_units(player):
        if not deployment.is_deployed(unit, placed):
            continue
        if (
            is_battle_shocked(game, unit)
            or below_half_strength(game, unit)
            or dread.dismay(game, unit)
        ):
            require(game, unit, BATTLE_SHOCK_STEP)


def _unit_bases(game: Game, unit: Unit) -> list:
    placed = deployment.positions(game)
    return [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in deployment.models_on_battlefield(game, unit)
    ]


def _has_ability(unit: Unit, name: str) -> bool:
    return any(a.name == name for m in unit.unit_models for a in m.model.abilities)


def _test_if_able(game: Game, unit: Unit, reason: str) -> None:
    # The unit must take a test - unless it already has one to take, or is
    # Battle-shocked.
    if any(t.unit_id == unit.id for t in pending(game)) or is_battle_shocked(game, unit):
        return
    require(game, unit, reason)


def start_of_fight(game: Game) -> None:
    # The start of the Fight phase: Voices in the Code - each enemy unit
    # within Engagement Range of a unit with it takes a Battle-shock test.
    from app.services.in_game.deployment import gap

    placed = deployment.positions(game)
    units = [
        (p.seat, u)
        for p in game.players
        for u in deployment.deployable_units(p)
        if deployment.is_deployed(u, placed)
    ]
    for seat, voices in units:
        if not _has_ability(voices, VOICES_IN_THE_CODE):
            continue
        near = _unit_bases(game, voices)
        for other_seat, enemy in units:
            if other_seat != seat and any(
                gap(a, b) <= ENGAGEMENT_RANGE + 1e-6 for a in near for b in _unit_bases(game, enemy)
            ):
                _test_if_able(game, enemy, VOICES_IN_THE_CODE)


def unit_about_to_be_destroyed(game: Game, unit_model, destroyed_by: Unit | None) -> None:
    # The last model of a unit is about to be removed, destroyed by
    # `destroyed_by`'s attacks: Executioner - each other unit of its army
    # within 3" of it takes a Battle-shock test.
    from app.services.in_game.deployment import gap

    if destroyed_by is None or not _has_ability(destroyed_by, EXECUTIONER):
        return
    unit = deployment.find_unit(game, unit_model.unit_id)
    owner = deployment.owner(game, unit)
    position = deployment.positions(game)[unit_model.id]
    last = deployment.base_at(unit_model, position.x, position.y, position.rotation)
    placed = deployment.positions(game)
    for other in deployment.deployable_units(owner):
        if other.id == unit.id or not deployment.is_deployed(other, placed):
            continue
        if any(gap(last, b) <= EXECUTIONER_RANGE + 1e-6 for b in _unit_bases(game, other)):
            _test_if_able(game, other, EXECUTIONER)


def battle_shock_outright(game: Game, unit: Unit, reason: str, roll: int) -> None:
    # A rule Battle-shocks the unit without a test (e.g. a Super-heavy Walker
    # rolling a 1): recorded as a failed test (`roll` its die).
    game.battle_shock_tests.append(
        GameBattleShockTest(
            unit_id=unit.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            phase=game.phase,
            reason=reason,
            modifier=0,
            first_die=roll,
            insane_bravery=False,
            passed=False,
        )
    )


def insane_bravery_reason(game: Game, seat: int, stratagem: Stratagem | None) -> str | None:
    # Why the player can't use Insane Bravery now, or None if they can: in the
    # Battle-shock step of their own Command phase, once per battle, for CP.
    if stratagem is None:
        return "there's no Insane Bravery stratagem"
    if game.phase != "command" or game.turn_seat != seat:
        return "it's used in the Battle-shock step of your own Command phase"
    player = next(p for p in game.players if p.seat == seat)
    if any(u.stratagem_id == stratagem.id for u in player.stratagem_uses):
        return "it has already been used this battle"
    if player.cp < stratagem.cp:
        return "not enough CP"
    return None


def take(
    game: Game, test: GameBattleShockTest, insane_bravery: Stratagem | None = None
) -> GameBattleShockTest:
    # Takes a pending test: passed automatically with Insane Bravery (if
    # given, and its CP spent), otherwise rolled.
    if test.passed is not None:
        raise _bad_request("that Battle-shock test has already been taken")
    unit = deployment.find_unit(game, test.unit_id)
    if insane_bravery is not None:
        player = deployment.owner(game, unit)
        if reason := insane_bravery_reason(game, player.seat, insane_bravery):
            raise _bad_request(f"can't use {INSANE_BRAVERY}: {reason}")
        player.cp -= insane_bravery.cp
        player.stratagem_uses.append(
            GameStratagemUse(
                stratagem_id=insane_bravery.id,
                stratagem=insane_bravery,
                battle_round=game.battle_round,
                turn_seat=game.turn_seat,
                phase=game.phase,
                cp=insane_bravery.cp,
            )
        )
        test.insane_bravery = True
        test.passed = True
        return test
    from app.seeds.factions.chaos_knights import dread

    test.first_die, test.second_die = (random.randint(1, 6) for _ in range(DICE))
    test.passed = test.first_die + test.second_die + test.modifier >= needed(game, unit)
    if not test.passed and dread.delirium(game, unit):
        roll = random.randint(1, DELIRIUM_DICE)
        test.wounds = GameBattleShockWounds(source="Delirium", roll=roll)
        casualties.mortal_wounds(game, unit, roll)
    if not test.passed:
        # An action it's started can't complete now.
        # (Imported here: actions imports this module.)
        from app.services.in_game import actions

        actions.check_started(game)
    return test
