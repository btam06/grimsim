from __future__ import annotations

import math
import random

from fastapi import HTTPException

from app.models import Game, GameUnitMove, GameUnitMoveStart, Unit, UnitModel
from app.services.in_game import (
    deployment,
    embarked,
    mission_state,
    pathing,
    regions,
    reinforcements,
)
from app.services.in_game.deployment import TOLERANCE, Placement

# Moving units in the movement phase. In their turn's movement phase a player
# can move each of their units - or leave it where it is (it remains
# stationary). Until the phase ends, a unit can be moved again (each move
# measured from where it started the phase) or put back where it started.
# Not every model in a unit has to move. A unit can:
#
# - make a Normal move: each model up to its Movement characteristic (M);
# - Advance: up to M plus a D6. The D6 is rolled when it's chosen (before the
#   unit moves, or after a Normal move), and from then on the unit Advances
#   this phase - it can't go back to a Normal move, and resetting it keeps the
#   roll;
# - Fall Back: up to M - only a unit that starts within Engagement Range of an
#   enemy model, which can't make a Normal move or Advance (so a unit can only
#   leave Engagement Range by Falling Back). Its mode (09.07) is chosen for
#   it: an Ordered Retreat, unless it's Battle-shocked - then a Desperate
#   Escape, moving through enemy models, but with a hazard roll for each model
#   first (once a phase, however often it's moved).
#
# Models go round enemy models - but MONSTER/VEHICLE units making a Normal
# move or Advance go through any but MONSTER/VEHICLE models (17.01). A FLYING
# unit can take to the skies (21.03): 2" less (none less with Hover), but
# through models and terrain.
#
# How far a model moved is how far its base's centre is from where it started
# (paths aren't checked). Where the unit ends up must be on the battlefield,
# not overlapping other models or terrain features, and in coherency (see
# app/services/in_game/deployment.py) - and no model within Engagement Range of an
# enemy model.

# Within 2" (base to base) of an enemy model.
ENGAGEMENT_RANGE = 2.0
# A Super-heavy Walker's roll after a move it made MOBILE for, this phase
# (kept as a marked unit - see app/services/in_game/mission_state.py).
SUPER_HEAVY_ROLL = "super_heavy_roll"
KIND_NAMES = {"normal": "Normal move", "advance": "Advance", "fall_back": "Fall Back"}


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _this_phase(game: Game, move: GameUnitMove) -> bool:
    return move.battle_round == game.battle_round and move.turn_seat == game.turn_seat


def unit_move(game: Game, unit: Unit) -> GameUnitMove | None:
    # The unit's move this movement phase (declared or made), if any.
    return next(
        (m for m in game.unit_moves if m.unit_id == unit.id and _this_phase(game, m)), None
    )


def is_movement_phase(game: Game) -> bool:
    return game.status == "in_progress" and game.phase == "movement"


def movable_units(game: Game) -> list[Unit]:
    # The units the player whose turn it is has on the battlefield.
    if game.turn_seat is None:
        return []
    player = next(p for p in game.players if p.seat == game.turn_seat)
    placed = deployment.positions(game)
    return [
        u for u in deployment.deployable_units(player) if deployment.is_deployed(u, placed)
    ]


def start_positions(game: Game, unit: Unit) -> dict[int, tuple[float, float, float]]:
    # Where the unit's models (those on the battlefield) were at the start of
    # this movement phase - where its move is measured from: as recorded when
    # it first moved, or where they are now if it hasn't.
    placed = deployment.positions(game)
    move = unit_move(game, unit)
    recorded = {s.unit_model_id: (s.x, s.y, s.rotation) for s in move.starts} if move else {}
    return {
        m.id: recorded.get(m.id, (placed[m.id].x, placed[m.id].y, placed[m.id].rotation))
        for m in unit.unit_models
        if m.id in placed
    }


def _start_bases(game: Game, unit: Unit) -> dict[int, deployment.Base]:
    models = {m.id: m for m in unit.unit_models}
    return {
        i: deployment.base_at(models[i], x, y, rotation)
        for i, (x, y, rotation) in start_positions(game, unit).items()
    }


def _enemy_bases(game: Game, unit: Unit) -> list[deployment.Base]:
    seat = deployment.owner(game, unit).seat
    return [b for p, _, b in deployment.placed_bases(game, unit) if p.seat != seat]


def in_engagement_range(game: Game, unit: Unit) -> bool:
    # Whether any of the unit's models is within Engagement Range of an enemy
    # model.
    enemies = _enemy_bases(game, unit)
    return any(
        deployment.gap(base, enemy) <= ENGAGEMENT_RANGE + TOLERANCE
        for base in _start_bases(game, unit).values()
        for enemy in enemies
    )


AIRCRAFT = "AIRCRAFT"


def is_aircraft(unit: Unit) -> bool:
    return any(k.name == AIRCRAFT for m in unit.unit_models for k in m.model.keywords)


def _engaged_with_non_aircraft(game: Game, unit: Unit) -> bool:
    # Engaged with an enemy model that isn't an AIRCRAFT (being engaged only
    # with AIRCRAFT doesn't stop a Normal move or Advance - 23.02).
    seat = deployment.owner(game, unit).seat
    enemies = [
        b
        for p, m, b in deployment.placed_bases(game, unit)
        if p.seat != seat and not any(k.name == AIRCRAFT for k in m.model.keywords)
    ]
    return any(
        deployment.gap(base, enemy) <= ENGAGEMENT_RANGE + TOLERANCE
        for base in _start_bases(game, unit).values()
        for enemy in enemies
    )


def allowed_kinds(game: Game, unit: Unit) -> list[str]:
    # The moves the unit can make: Fall Back if it started the phase within
    # Engagement Range (of anything but AIRCRAFT); only an Advance once it's
    # rolled to; otherwise a Normal move or Advance. (It can move again until
    # the phase ends.) AIRCRAFT only make ingress moves (23.02).
    if is_aircraft(unit):
        return []
    move = unit_move(game, unit)
    if move is not None and move.advance_roll is not None:
        return ["advance"]
    return ["fall_back"] if _engaged_with_non_aircraft(game, unit) else ["normal", "advance"]


def allowance(
    model: UnitModel, kind: str, move: GameUnitMove | None, take_to_skies: bool = False
) -> float:
    # How far a model can move: its M, plus the D6 if it's Advancing - 2"
    # less if it takes to the skies (but for Hover).
    extra = move.advance_roll if kind == "advance" and move and move.advance_roll else 0
    skies = 2 if take_to_skies and not _hovers(model) else 0
    return float(model.model.movement + extra - skies)


FLY = "FLY"
HOVER = "Hover"
DESPERATE_ESCAPE = "desperate_escape"


def _hovers(model: UnitModel) -> bool:
    return any(a.name == HOVER for a in model.model.abilities)


def can_fly(unit: Unit) -> bool:
    # Whether the unit can FLY (a model in it has FLY).
    return any(k.name == FLY for m in unit.unit_models for k in m.model.keywords)


def _big_unit(unit: Unit) -> bool:
    return bool(unit.unit_models) and all(
        {k.name for k in m.model.keywords} & pathing.BIG for m in unit.unit_models
    )


def desperate(game: Game, unit: Unit, kind: str) -> bool:
    # Whether its Fall Back move is a Desperate Escape: it's Battle-shocked.
    from app.services.in_game import battle_shock

    return kind == "fall_back" and battle_shock.is_battle_shocked(game, unit)


def through(game: Game, unit: Unit, kind: str, take_to_skies: bool = False) -> str:
    # What the unit's models can go through on this move (see pathing).
    if take_to_skies and can_fly(unit):
        return "all"
    if desperate(game, unit, kind):
        return "enemies"
    if pathing.is_super_heavy_walker(unit):
        return "non_titanic"
    if kind in ("normal", "advance") and _big_unit(unit):
        return "small"
    return "none"


def _check_unit(game: Game, unit: Unit) -> None:
    # That the unit can move now: it's the movement phase of its owner's turn,
    # and it's on the battlefield. (It can move again, from where it started
    # the phase, until the phase ends.)
    if not is_movement_phase(game):
        raise _bad_request("units can only move in the movement phase")
    if deployment.owner(game, unit).seat != game.turn_seat:
        raise _bad_request("only the player whose turn it is can move their units")
    if not deployment.is_deployed(unit, deployment.positions(game)):
        raise _bad_request("that unit isn't on the battlefield")
    if reinforcements.movement_ended(game):
        raise _bad_request("the movement phase is over")
    move = unit_move(game, unit)
    if move is not None and move.kind == reinforcements.ARRIVED:
        raise _bad_request("it arrived from Reserves this phase: it can't move again")
    if move is not None and move.kind == embarked.DISEMBARKED:
        raise _bad_request(
            "it disembarked from a transport that had moved this phase: it can't move again"
        )


def roll_bonus(game: Game, unit: Unit, roll: str) -> int:
    # What the unit's abilities add to its `roll` ("advance", "charge") now -
    # e.g. Optimised Gait: +1, or +2 within 6" of a friendly ADEPTUS
    # MECHANICUS BATTLELINE unit. (The best one counts.)
    from app.seeds import datasheet_abilities

    config = datasheet_abilities.ROLL_BONUSES
    names = {a.name for m in unit.unit_models for a in m.model.abilities}
    best = 0
    for name in names & set(config):
        bonus = config[name]
        if roll not in bonus["rolls"]:
            continue
        value = bonus["bonus"]
        if (near := bonus.get("near")) is not None:
            keywords, reach, instead = near
            if regions.near_friendly(game, unit, keywords, reach):
                value = instead
        best = max(best, value)
    return best


def roll_advance(game: Game, unit: Unit) -> GameUnitMove:
    # Rolls the unit's Advance D6, before it moves - once a phase: if it's
    # already rolled, that roll stands. (What its abilities add is added to
    # it then - see roll_bonus.)
    _check_unit(game, unit)
    if "advance" not in allowed_kinds(game, unit):
        raise _bad_request("that unit can't Advance")
    if (move := unit_move(game, unit)) is not None:
        # Already moved (normally) this phase: roll now; already rolled: that
        # roll stands.
        if move.advance_roll is None:
            move.advance_roll = random.randint(1, 6) + roll_bonus(game, unit, "advance")
        return move
    move = GameUnitMove(
        unit_id=unit.id,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        kind="advance",
        advance_roll=random.randint(1, 6) + roll_bonus(game, unit, "advance"),
        completed=False,
    )
    game.unit_moves.append(move)
    return move


def check_move(
    game: Game,
    unit: Unit,
    kind: str,
    placement: dict[int, tuple[float, float, float]],
    take_to_skies: bool = False,
    mobile: bool = False,
) -> Placement:
    # Whether the unit could make a `kind` move to `placement` ((x, y,
    # rotation) by unit model id - every model in it, moved or not), taking
    # to the skies if it says so (and can FLY) - or, for a Super-heavy
    # Walker, `mobile` (through terrain).
    _check_unit(game, unit)
    take_to_skies = take_to_skies and can_fly(unit)
    kinds = allowed_kinds(game, unit)
    if kind not in kinds:
        if kinds == ["fall_back"]:
            raise _bad_request("that unit is within Engagement Range: it can only Fall Back")
        if kinds == ["advance"]:
            raise _bad_request("that unit has rolled to Advance: it Advances this phase")
        if not kinds:
            raise _bad_request("AIRCRAFT units only make ingress moves")
        raise _bad_request("only a unit within Engagement Range can Fall Back")
    move = unit_move(game, unit)
    if kind == "advance" and (move is None or move.advance_roll is None):
        raise _bad_request("roll for the Advance before moving")
    # Every model it has left (destroyed ones are off the battlefield).
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    start = _start_bases(game, unit)
    problems = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    enemies = _enemy_bases(game, unit)
    # How far each model moves: round dense terrain and enemy models, unless
    # it can go through them (see app/services/in_game/pathing.py).
    pather = pathing.for_unit(
        game, unit, start,
        max((allowance(m, kind, move, take_to_skies) for m in models), default=0),
        through(game, unit, kind, take_to_skies),
        mobile and pathing.is_super_heavy_walker(unit),
    )
    for model in models:
        found = []
        limit = allowance(model, kind, move, take_to_skies)
        if problem := pathing.too_far(pather, start[model.id], bases[model.id], limit):
            found.append(problem)
        if any(
            deployment.gap(bases[model.id], enemy) <= ENGAGEMENT_RANGE + TOLERANCE
            for enemy in enemies
        ):
            found.append("would end within Engagement Range of an enemy model")
        problems[model.id] = found + problems[model.id]
    result = deployment.summarise(models, problems)
    result.paths = pather.bends(start, bases)
    return result


def check_free_move(
    game: Game,
    unit: Unit,
    placement: dict[int, tuple[float, float, float]],
    start: dict[int, tuple[float, float, float]],
    reach: float,
) -> Placement:
    # Whether the unit could make a Normal move of up to `reach` from `start`
    # to `placement`, outside the movement phase (e.g. a Scouts move, or Ride
    # the Thermals): on the battlefield, not overlapping, in coherency, each
    # model within reach (round dense terrain), and none ending within
    # Engagement Range of an enemy model.
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    every = {m.id: m for m in unit.unit_models}
    starts = {
        i: deployment.base_at(every[i], x, y, rotation) for i, (x, y, rotation) in start.items()
    }
    problems = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    enemies = _enemy_bases(game, unit)
    pather = pathing.for_unit(game, unit, starts, reach)
    for model in models:
        found = []
        if problem := pathing.too_far(pather, starts[model.id], bases[model.id], reach):
            found.append(problem)
        if any(
            deployment.gap(bases[model.id], e) <= ENGAGEMENT_RANGE + TOLERANCE for e in enemies
        ):
            found.append("would end within Engagement Range of an enemy model")
        problems[model.id] = found + problems[model.id]
    result = deployment.summarise(models, problems)
    result.paths = pather.bends(starts, bases)
    return result


def check_reach_or_further(
    game: Game,
    unit: Unit,
    placement: dict[int, tuple[float, float, float]],
    reach: float,
    further: tuple[float, tuple[str, ...], float] | None,
    name: str,
) -> Placement:
    # As check_free_move from where the unit is now, up to `reach` - or, with
    # `further` (inches, keywords, inches), up to further than that, if every
    # model ends wholly within the last inches of a friendly unit with those
    # keywords (e.g. Ride the Thermals, Tactica Obliqua).
    limit = max(reach, further[0]) if further else reach
    start = current_positions(game, unit)
    result = check_free_move(game, unit, placement, start, limit)
    if not further or further[0] <= reach:
        return result
    _, keywords, within = further
    every = {m.id: m for m in unit.unit_models}
    starts = {i: deployment.base_at(every[i], *xyr) for i, xyr in start.items()}
    ends = {i: deployment.base_at(every[i], *placement[i]) for i in start if i in placement}
    pather = pathing.for_unit(game, unit, starts, limit)
    if any(pathing.too_far(pather, starts[i], ends[i], reach) for i in ends):
        near = any(
            all(
                regions.base_wholly_within_of(b, regions.unit_bases(game, other), within)
                for b in ends.values()
            )
            for other in regions.friendly_units_with(game, unit, keywords)
        )
        if not near:
            result.problems.append(
                f'{name}: moving more than {reach:g}", every model must end wholly within '
                f'{within:g}" of a friendly {" ".join(keywords)} unit'
            )
    return result


def current_positions(game: Game, unit: Unit) -> dict[int, tuple[float, float, float]]:
    # Where the unit's models (on the battlefield) are now.
    placed = deployment.positions(game)
    return {
        m.id: (placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    }


def place(game: Game, placement: dict[int, tuple[float, float, float]]) -> None:
    # Puts the models where `placement` says (they're on the battlefield).
    placed = deployment.positions(game)
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation


def move_unit(
    game: Game,
    unit: Unit,
    kind: str,
    placement: dict[int, tuple[float, float, float]],
    take_to_skies: bool = False,
    mobile: bool = False,
) -> None:
    # Moves the unit, if it can make that move.
    result = check_move(game, unit, kind, placement, take_to_skies, mobile)
    if not result.valid:
        raise _bad_request("can't move it there: " + "; ".join(result.problems))
    # A Desperate Escape: a hazard roll for each model first (once a phase).
    if desperate(game, unit, kind):
        _desperate_escape(game, unit)
        placed = deployment.positions(game)
        placement = {i: xyr for i, xyr in placement.items() if i in placed}
        if not placement:
            return
    placed = deployment.positions(game)
    start = start_positions(game, unit)
    # How far its furthest-moved model is from where it started the phase
    # (e.g. for shooting: whether it moved less than 3", or not at all).
    bases = _start_bases(game, unit)
    pather = pathing.for_unit(game, unit, bases, 100)
    models = {m.id: m for m in unit.unit_models}

    def moved(i: int, x: float, y: float, rotation: float) -> float:
        end = deployment.base_at(models[i], x, y, rotation)
        return pather.distance(bases[i], end, cap=1000) or math.hypot(
            x - start[i][0], y - start[i][1]
        )

    distance = max(moved(i, *xyr) for i, xyr in placement.items())
    move = unit_move(game, unit)
    if move is None:
        move = GameUnitMove(
            unit_id=unit.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            kind=kind,
        )
        game.unit_moves.append(move)
    if not move.starts:
        move.starts = [
            GameUnitMoveStart(unit_model_id=i, x=x, y=y, rotation=rotation)
            for i, (x, y, rotation) in start.items()
        ]
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    # It may have rolled to Advance and then moved normally.
    move.kind = kind
    move.distance = round(distance, 3)
    move.completed = True
    mission_state.after_move(game, unit)
    if mobile:
        _super_heavy_walker(game, unit)
    # Enemy units it ended its move near that can react (e.g. Tactica
    # Obliqua). (Imported here: reactive_move imports this module.)
    from app.services.in_game import reactive_move

    reactive_move.after_enemy_move(game, unit)


def _desperate_escape(game: Game, unit: Unit) -> None:
    # A hazard roll for each model in the unit (06.03): each failed one, 1
    # mortal wound - 3 if every model is a MONSTER/VEHICLE. Once a phase.
    from app.services.combat import hazard_failed, hazard_wounds
    from app.services.in_game import casualties

    seat = deployment.owner(game, unit).seat
    if any(
        m.unit_id == unit.id and m.battle_round == game.battle_round
        and m.turn_seat == game.turn_seat
        for m in mission_state.marked(game, DESPERATE_ESCAPE, seat)
    ):
        return
    mission_state.mark(game, seat, DESPERATE_ESCAPE, unit.id)
    models = deployment.models_on_battlefield(game, unit)
    per = hazard_wounds([{k.name for k in m.model.keywords} for m in models])
    failed = sum(hazard_failed(random.randint(1, 6)) for _ in models)
    if failed:
        casualties.mortal_wounds(game, unit, failed * per)


def _super_heavy_walker(game: Game, unit: Unit) -> None:
    # A Super-heavy Walker that was MOBILE for its move rolls a D6 when it
    # ends: on a 1, it's Battle-shocked (24.35). Once a phase (moving it
    # again doesn't roll again).
    # (Imported here: battle_shock imports this module's users.)
    from app.services.in_game import battle_shock

    if not pathing.is_super_heavy_walker(unit):
        return
    seat = deployment.owner(game, unit).seat
    if any(
        m.unit_id == unit.id
        and m.battle_round == game.battle_round
        and m.turn_seat == game.turn_seat
        for m in mission_state.marked(game, SUPER_HEAVY_ROLL, seat)
    ):
        return
    mission_state.mark(game, seat, SUPER_HEAVY_ROLL, unit.id)
    roll = random.randint(1, 6)
    if roll == 1:
        battle_shock.battle_shock_outright(game, unit, pathing.SUPER_HEAVY_WALKER, roll)


def reset_move(game: Game, unit: Unit) -> None:
    # Puts the unit's models back where they started the phase, as if it
    # hadn't moved (an Advance roll stands).
    _check_unit(game, unit)
    move = unit_move(game, unit)
    if move is None or not move.completed:
        return
    placed = deployment.positions(game)
    for unit_model_id, (x, y, rotation) in start_positions(game, unit).items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    if move.advance_roll:
        move.kind = "advance"
        move.completed = False
        move.distance = None
        move.starts = []
    else:
        game.unit_moves.remove(move)
