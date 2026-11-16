from __future__ import annotations


from fastapi import HTTPException

from app.models import Stratagem, Unit
from app.engine.state import Game, GameBattleShockTest, GameBattleShockWounds, GameStratagemUse
from app.services import dice
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


def starting_strength(unit: Unit, game: Game | None = None) -> int:
    # (A unit whose model was set up again by Divine Intervention is a unit
    # of that one model.)
    if game is not None and (returned := _returned_model(game, unit)) is not None:
        return returned.wounds
    models = unit.unit_models
    if len(models) == 1:
        return models[0].wounds
    return len(models)


def current_strength(game: Game, unit: Unit) -> int:
    # Models on the battlefield - or, for a unit of one model, its wounds
    # left (0 if it's destroyed).
    if len(unit.unit_models) == 1 or _returned_model(game, unit) is not None:
        return sum(casualties.wounds_remaining(game, unit).values())
    return len(deployment.models_on_battlefield(game, unit))


def _returned_model(game: Game, unit: Unit):
    from app.seeds.factions.adepta_sororitas import miracle_rules

    return miracle_rules.returned_model(game, unit)


def below_half_strength(game: Game, unit: Unit) -> bool:
    # At half its starting strength or below (for the Battle-shock step).
    return 2 * current_strength(game, unit) <= starting_strength(unit, game)


def below_starting_strength(game: Game, unit: Unit) -> bool:
    return current_strength(game, unit) < starting_strength(unit, game)


def below_half_strength_strict(game: Game, unit: Unit) -> bool:
    # Below Half-strength, for rules that use the term: less than half its
    # starting strength.
    return 2 * current_strength(game, unit) < starting_strength(unit, game)


def leadership(unit: Unit) -> int:
    # The unit's best Leadership (the lowest roll that passes).
    return min(m.model.leadership for m in unit.unit_models)


def needed(game: Game, unit: Unit) -> int:
    # The roll its Battle-shock tests need: its best Leadership, worsened by
    # any rules (Deathly Terror, Despair).
    from app.seeds.factions.chaos_knights import dread

    return leadership(unit) + dread.leadership_worsened(game, unit) - leadership_improved(game, unit)


def leadership_improved(game: Game, unit: Unit) -> int:
    # What friendly auras improve its Leadership by (datasheet_abilities
    # LEADERSHIP_AURAS - e.g. The Silent King: 1 for NECRONS units within 6"
    # of Szarekh), each ability once.
    from app.seeds import datasheet_abilities
    from app.services.in_game.deployment import TOLERANCE, gap

    config = datasheet_abilities.LEADERSHIP_AURAS
    if not config or game.status != "in_progress":
        return 0
    seat = deployment.owner(game, unit).seat
    player = next(p for p in game.players if p.seat == seat)
    keywords = {k.name for m in unit.unit_models for k in m.model.keywords}
    mine = _unit_bases(game, unit)
    placed = deployment.positions(game)
    total = 0
    for name, how in config.items():
        if not set(how["keywords"]) <= keywords:
            continue
        for other in deployment.deployable_units(player):
            near = [
                deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
                for m in deployment.models_on_battlefield(game, other)
                if m.id in placed and any(a.name == name for a in m.model.abilities)
            ]
            if any(gap(a, b) <= how["range"] + TOLERANCE for a in near for b in mine):
                total += how["bonus"]
                break
    return total


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
        elif (modifier := _forced_by_aura(game, unit)) is not None:
            # (An enemy aura makes it - e.g. Nightmare Shroud: below its
            # Starting Strength within 6", at -1.)
            require(game, unit, BATTLE_SHOCK_STEP, modifier)


# Enemy auras that make a unit below its Starting Strength take a test in its
# Battle-shock step: {ability: (range, modifier)} - Nightmare Shroud.
FORCED_TEST_AURAS = {"Nightmare Shroud (Aura)": (6.0, -1)}


def _forced_by_aura(game: Game, unit: Unit) -> int | None:
    from app.services.in_game.deployment import gap

    if not below_starting_strength(game, unit):
        return None
    seat = deployment.owner(game, unit).seat
    mine = _unit_bases(game, unit)
    for player in game.players:
        if player.seat == seat:
            continue
        for other in deployment.deployable_units(player):
            for name, (reach, modifier) in FORCED_TEST_AURAS.items():
                near = [
                    b
                    for m in deployment.models_on_battlefield(game, other)
                    if any(a.name == name for a in m.model.abilities)
                    for b in [_unit_bases_of_model(game, m)]
                ]
                if any(gap(a, b) <= reach + 1e-6 for a in near for b in mine):
                    return modifier
    return None


def _unit_bases_of_model(game: Game, unit_model):
    placed = deployment.positions(game)
    p = placed[unit_model.id]
    return deployment.base_at(unit_model, p.x, p.y, p.rotation)


def _unit_bases(game: Game, unit: Unit) -> list:
    placed = deployment.positions(game)
    return [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in deployment.models_on_battlefield(game, unit)
    ]


def _has_ability(unit: Unit, name: str) -> bool:
    return any(a.name == name for m in unit.unit_models for a in m.model.abilities)


def _test_if_able(game: Game, unit: Unit, reason: str, modifier: int = 0) -> None:
    # The unit must take a test - unless it already has one to take, or is
    # Battle-shocked.
    if any(t.unit_id == unit.id for t in pending(game)) or is_battle_shocked(game, unit):
        return
    require(game, unit, reason, modifier)


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
    # (And the abilities in FIGHT_START_BATTLE_SHOCK - e.g. Terrifying
    # Monstrosity.)
    from app.seeds import datasheet_abilities

    names = {VOICES_IN_THE_CODE} | datasheet_abilities.FIGHT_START_BATTLE_SHOCK
    auras = datasheet_abilities.FIGHT_START_BATTLE_SHOCK_AURAS

    def aura_on(seat: int, unit: Unit) -> str | None:
        # A friendly aura with it reaching the unit (e.g. Unrestrained Terror:
        # WAR DOG units within 6").
        keywords = {k.name for m in unit.unit_models for k in m.model.keywords}
        mine = _unit_bases(game, unit)
        for name, how in sorted(auras.items()):
            if not set(how["keywords"]) <= keywords:
                continue
            for other_seat, other in units:
                if other_seat == seat and _has_ability(other, name) and any(
                    gap(a, b) <= how["range"] + 1e-6 for a in _unit_bases(game, other) for b in mine
                ):
                    return name
        return None

    for seat, voices in units:
        name = next((n for n in sorted(names) if _has_ability(voices, n)), None) or (
            aura_on(seat, voices) if auras else None
        )
        if name is None:
            continue
        near = _unit_bases(game, voices)
        for other_seat, enemy in units:
            if other_seat != seat and any(
                gap(a, b) <= ENGAGEMENT_RANGE + 1e-6 for a in near for b in _unit_bases(game, enemy)
            ):
                _test_if_able(game, enemy, name)
    # Righteous Denunciation: enemy units within 6" of a model with it, at -1.
    from app.seeds.factions.adepta_sororitas import unit_abilities

    for enemy, modifier in unit_abilities.denunciation_tests(game):
        _test_if_able(game, enemy, unit_abilities.RIGHTEOUS_DENUNCIATION, modifier)


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


def rerolls_failed(game: Game, unit) -> bool:
    # Whether the unit re-rolls a failed Battle-shock test: its army's
    # detachment rules let its units with certain keywords re-roll Leadership
    # rolls (e.g. Wretched Thralls: DAMNED units) - a failed one's always
    # worth re-rolling.
    from app.seeds import factions as faction_seeds
    from app.services.list_building import enhancements as enhancement_rules

    # (The Censer of the Sacred Rose reaching it, too.)
    from app.seeds.factions.adepta_sororitas import unit_abilities as sororitas

    if sororitas.relic_on(game, unit, sororitas.CENSER):
        return True
    # (Or a model leading it has an ability that lets it - e.g. Fiery Faith.)
    from app.seeds import datasheet_abilities

    leading = datasheet_abilities.LEADING_BATTLE_SHOCK_REROLLS
    if leading and any(
        a.name in leading and enhancement_rules.is_leading(unit, m)
        for m in deployment.models_on_battlefield(game, unit)
        for a in m.model.abilities
    ):
        return True
    configs = faction_seeds.BATTLE_SHOCK_REROLLS
    player = deployment.owner(game, unit)
    models = deployment.models_on_battlefield(game, unit) or list(unit.unit_models)
    for detachment in player.army_list.detachments:
        for rule in detachment.rules:
            config = configs.get(rule.name)
            if config is not None and models and all(
                set(config["keywords"]) <= enhancement_rules.model_keywords(unit, m)
                for m in models
            ):
                return True
    return False


def take(
    game: Game,
    test: GameBattleShockTest,
    insane_bravery: Stratagem | None = None,
    miracle_die: int | None = None,
) -> GameBattleShockTest:
    # Takes a pending test: passed automatically with Insane Bravery (if
    # given, and its CP spent), otherwise rolled - with `miracle_die` (an Act
    # of Faith) as its first die, if given, and only the second rolled.
    from app.seeds.factions.adepta_sororitas import acts_of_faith

    if test.passed is not None:
        raise _bad_request("that Battle-shock test has already been taken")
    unit = deployment.find_unit(game, test.unit_id)
    if insane_bravery is not None and miracle_die is not None:
        raise _bad_request("a test passed with Insane Bravery isn't rolled")
    from app.seeds.factions.adepta_sororitas import hagiomnifex

    if insane_bravery is None and hagiomnifex.auto_pass_battle_shock(game, unit):
        # Sermon of Intolerance: it succeeds, unrolled.
        if miracle_die is not None:
            raise _bad_request("a test that automatically succeeds isn't rolled")
        test.passed = True
        return test
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

    # Enemy auras that worsen it (e.g. Neurostatic Interference).
    test.modifier += aura_modifier(game, unit)
    if miracle_die is not None:
        test.first_die = acts_of_faith.perform(
            game, unit, acts_of_faith.BATTLE_SHOCK, miracle_die
        )
        test.second_die = dice.randint(1, 6)
    else:
        test.first_die, test.second_die = (dice.randint(1, 6) for _ in range(DICE))
    test.passed = test.first_die + test.second_die + test.modifier >= needed(game, unit)
    if not test.passed and miracle_die is None and rerolls_failed(game, unit):
        # (e.g. Wretched Thralls: a failed test's re-rolled.)
        test.rerolled = [test.first_die, test.second_die]
        test.first_die, test.second_die = (dice.randint(1, 6) for _ in range(DICE))
        test.passed = test.first_die + test.second_die + test.modifier >= needed(game, unit)
    if not test.passed and test.wounds is None:
        # A test an ability made it take, failing which it suffers mortal
        # wounds (e.g. Holy Judgement - see shooting_start).
        from app.seeds import datasheet_abilities

        how = datasheet_abilities.START_OF_SHOOTING.get(test.reason, {})
        if how.get("fail_mortal_wounds"):
            wounds = how["fail_mortal_wounds"]
            test.wounds = GameBattleShockWounds(source=test.reason, roll=wounds)
            casualties.mortal_wounds(game, unit, wounds)
    if not test.passed and test.wounds is None and dread.delirium(game, unit):
        roll = dice.randint(1, DELIRIUM_DICE)
        test.wounds = GameBattleShockWounds(source="Delirium", roll=roll)
        casualties.mortal_wounds(game, unit, roll)
    if not test.passed:
        # An action it's started can't complete now.
        # (Imported here: actions imports this module.)
        from app.services.in_game import actions

        actions.check_started(game)
    return test


def aura_modifier(game: Game, unit: Unit) -> int:
    # What enemy auras do to the unit's Battle-shock tests (datasheet_abilities
    # BATTLE_SHOCK_AURAS - e.g. Neurostatic Interference: -1 within 6", -2
    # while the aura's unit is near a friendly ADEPTUS MECHANICUS BATTLELINE
    # unit). The worst counts.
    from app.seeds import datasheet_abilities
    from app.services.in_game import regions
    from app.services.in_game.deployment import TOLERANCE, gap

    config = datasheet_abilities.BATTLE_SHOCK_AURAS
    seat = deployment.owner(game, unit).seat
    placed = deployment.positions(game)

    def bases(u):
        return [
            deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
            for m in u.unit_models
            if m.id in placed
        ]

    mine = bases(unit)
    worst = 0
    for player in game.players:
        if player.seat == seat:
            continue
        for other in deployment.deployable_units(player):
            names = {a.name for m in deployment.models_on_battlefield(game, other) for a in m.model.abilities}
            for name in names & set(config):
                how = config[name]
                if not any(gap(a, b) <= how["range"] + TOLERANCE for a in bases(other) for b in mine):
                    continue
                value = how["modifier"]
                if (near := how.get("near")) is not None:
                    keywords, reach, instead = near
                    if regions.near_friendly(game, other, keywords, reach):
                        value = instead
                worst = min(worst, value)
    return worst


def after_shooting(
    game: Game, unit: Unit, target: Unit, hits: int, indirect_hits: int = 0
) -> None:
    # The unit has shot `target` in its Shooting phase, scoring `hits` (of
    # them `indirect_hits` with [INDIRECT FIRE] weapons): its abilities that
    # make a unit it hit take a Battle-shock test (e.g. Dread Snipers) do -
    # those in AFTER_SHOOTING_INDIRECT_ONLY only if an [INDIRECT FIRE]
    # weapon hit it (e.g. Devastating Refrain).
    from app.seeds import datasheet_abilities

    config = datasheet_abilities.AFTER_SHOOTING_BATTLE_SHOCK
    indirect_only = datasheet_abilities.AFTER_SHOOTING_INDIRECT_ONLY
    if game.phase != "shooting" or deployment.owner(game, unit).seat != game.turn_seat:
        return
    if hits <= 0 or not deployment.models_on_battlefield(game, target):
        return
    if is_battle_shocked(game, target) or any(t.unit_id == target.id for t in pending(game)):
        return
    names = {a.name for m in deployment.models_on_battlefield(game, unit) for a in m.model.abilities}
    keywords = {k.name for m in target.unit_models for k in m.model.keywords}
    required = datasheet_abilities.AFTER_SHOOTING_TARGET_KEYWORDS
    for name in sorted(names & set(config)):
        if name in indirect_only and indirect_hits <= 0:
            continue
        # (Only a unit with these keywords - e.g. Cursed Flames: INFANTRY.)
        if name in required and not set(required[name]) <= keywords:
            continue
        require(game, target, name, config[name])
        return
