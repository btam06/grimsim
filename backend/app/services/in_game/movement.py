from __future__ import annotations

import math
import random

from fastapi import HTTPException

from app.models import Game, GameUnitMove, Unit, UnitModel
from app.services.in_game import deployment
from app.services.in_game.deployment import TOLERANCE, Placement

# Moving units in the movement phase. In their turn's movement phase a player
# can move each of their units once - or leave it where it is (it remains
# stationary). Not every model in a unit has to move. A unit can:
#
# - make a Normal move: each model up to its Movement characteristic (M);
# - Advance: up to M plus a D6. The D6 is rolled before the unit moves, and
#   kept for the phase: the player can still choose a Normal move instead, but
#   advancing again uses the same roll;
# - Fall Back: up to M - only a unit that starts within Engagement Range of an
#   enemy model, which can't make a Normal move or Advance (so a unit can only
#   leave Engagement Range by Falling Back).
#
# How far a model moved is how far its base's centre is from where it started
# (paths aren't checked). Where the unit ends up must be on the battlefield,
# not overlapping other models or terrain features, and in coherency (see
# app/services/in_game/deployment.py) - and no model within Engagement Range of an
# enemy model.

# Within 2" (base to base) of an enemy model.
ENGAGEMENT_RANGE = 2.0
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


def _start_bases(game: Game, unit: Unit) -> dict[int, deployment.Base]:
    # Where the unit's models are now (where a move starts from).
    placed = deployment.positions(game)
    return {
        m.id: deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
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


def allowed_kinds(game: Game, unit: Unit) -> list[str]:
    # The moves the unit can make: Fall Back if it's within Engagement Range,
    # otherwise a Normal move or Advance; none once it's moved.
    move = unit_move(game, unit)
    if move is not None and move.completed:
        return []
    return ["fall_back"] if in_engagement_range(game, unit) else ["normal", "advance"]


def allowance(model: UnitModel, kind: str, move: GameUnitMove | None) -> float:
    # How far a model can move: its M, plus the D6 if it's Advancing.
    extra = move.advance_roll if kind == "advance" and move and move.advance_roll else 0
    return float(model.model.movement + extra)


def _check_unit(game: Game, unit: Unit) -> None:
    # That the unit can move now: it's the movement phase of its owner's turn,
    # it's on the battlefield, and it hasn't moved yet this phase.
    if not is_movement_phase(game):
        raise _bad_request("units can only move in the movement phase")
    if deployment.owner(game, unit).seat != game.turn_seat:
        raise _bad_request("only the player whose turn it is can move their units")
    if not deployment.is_deployed(unit, deployment.positions(game)):
        raise _bad_request("that unit isn't on the battlefield")
    move = unit_move(game, unit)
    if move is not None and move.completed:
        raise _bad_request("that unit has already moved this phase")


def roll_advance(game: Game, unit: Unit) -> GameUnitMove:
    # Rolls the unit's Advance D6, before it moves - once a phase: if it's
    # already rolled, that roll stands.
    _check_unit(game, unit)
    if "advance" not in allowed_kinds(game, unit):
        raise _bad_request("that unit can't Advance")
    if (move := unit_move(game, unit)) is not None:
        return move
    move = GameUnitMove(
        unit_id=unit.id,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        kind="advance",
        advance_roll=random.randint(1, 6),
        completed=False,
    )
    game.unit_moves.append(move)
    return move


def check_move(
    game: Game, unit: Unit, kind: str, placement: dict[int, tuple[float, float, float]]
) -> Placement:
    # Whether the unit could make a `kind` move to `placement` ((x, y,
    # rotation) by unit model id - every model in it, moved or not).
    _check_unit(game, unit)
    kinds = allowed_kinds(game, unit)
    if kind not in kinds:
        if kinds == ["fall_back"]:
            raise _bad_request("that unit is within Engagement Range: it can only Fall Back")
        raise _bad_request("only a unit within Engagement Range can Fall Back")
    if kind == "advance" and unit_move(game, unit) is None:
        raise _bad_request("roll for the Advance before moving")
    # Every model it has left (destroyed ones are off the battlefield).
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    move = unit_move(game, unit)
    start = _start_bases(game, unit)
    problems = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    enemies = _enemy_bases(game, unit)
    for model in models:
        found = []
        moved = math.hypot(
            bases[model.id].x - start[model.id].x, bases[model.id].y - start[model.id].y
        )
        limit = allowance(model, kind, move)
        if moved > limit + TOLERANCE:
            found.append(f'would move {moved:.1f}" (it can move {limit:g}")')
        if any(
            deployment.gap(bases[model.id], enemy) <= ENGAGEMENT_RANGE + TOLERANCE
            for enemy in enemies
        ):
            found.append("would end within Engagement Range of an enemy model")
        problems[model.id] = found + problems[model.id]
    return deployment.summarise(models, problems)


def move_unit(
    game: Game, unit: Unit, kind: str, placement: dict[int, tuple[float, float, float]]
) -> None:
    # Moves the unit, if it can make that move.
    result = check_move(game, unit, kind, placement)
    if not result.valid:
        raise _bad_request("can't move it there: " + "; ".join(result.problems))
    placed = deployment.positions(game)
    # How far its furthest-moved model goes (e.g. for shooting: whether it
    # moved less than 3", or not at all).
    distance = max(
        math.hypot(x - placed[i].x, y - placed[i].y) for i, (x, y, _) in placement.items()
    )
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    move = unit_move(game, unit)
    if move is None:
        move = GameUnitMove(
            unit_id=unit.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            kind=kind,
        )
        game.unit_moves.append(move)
    # It may have rolled to Advance and then moved normally.
    move.kind = kind
    move.distance = round(distance, 3)
    move.completed = True
