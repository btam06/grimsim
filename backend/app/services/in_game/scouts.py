from __future__ import annotations

import re

from fastapi import HTTPException

from app.models import (
    Game,
    GameScoutsDone,
    GameUnitMove,
    GameUnitMoveStart,
    Unit,
    UnitModel,
)
from app.services.in_game import deployment, movement
from app.services.in_game.deployment import Placement

# Scouts moves: at the start of the first battle round, before the first
# turn (its start-of-round step - see app/services/in_game/battle_round.py) -
# so once both armies are set up and who goes first is decided (see
# app/services/in_game/first_turn.py). A
# unit on the battlefield whose every model has Scouts X" - its own ability,
# or from its wargear (e.g. an Orbital Comms Array: "This unit has Scouts
# 6\"") - can make a Normal move of up to X": on the battlefield, not
# overlapping other models or terrain features, in coherency, and not ending
# within Engagement Range of an enemy model. The player going first makes
# theirs, then their opponent; each says when they're done (a player with no
# such unit is skipped), and the first turn waits for both. Until then, a
# unit can be moved again, measured from where it was set up.

SCOUTS = re.compile(r'^Scouts (\d+)"$')
# The kind of move (see GameUnitMove) a Scouts move is - recorded in battle
# round 0, apart from the first round's movement phases.
SCOUT = "scout"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _model_distance(unit: Unit, unit_model: UnitModel) -> int:
    # The model's Scouts distance: from its abilities, its wargear's, and
    # those of wargear in its unit that reach the bearer's unit.
    names = [a.name for a in unit_model.model.abilities] + [
        a.name
        for other in unit.unit_models
        for gear in other.wargear
        if other is unit_model or gear.scope == "bearers_unit"
        for a in gear.abilities
    ]
    # (A one-model unit's wargear is its unit's.)
    if len(unit.unit_models) == 1:
        names += [a.name for gear in unit_model.wargear for a in gear.abilities]
    return max((int(m.group(1)) for n in names if (m := SCOUTS.match(n))), default=0)


def distance(unit: Unit) -> int:
    # How far the unit can make a Scouts move: every model must have Scouts
    # (the shortest counts). 0 if it can't.
    return min((_model_distance(unit, m) for m in unit.unit_models), default=0)


def scout_units(game: Game, seat: int) -> list[Unit]:
    # The player's units on the battlefield that can make a Scouts move.
    player = next(p for p in game.players if p.seat == seat)
    placed = deployment.positions(game)
    return [
        u
        for u in deployment.deployable_units(player)
        if deployment.is_deployed(u, placed) and distance(u)
    ]


def done(game: Game, seat: int) -> bool:
    return any(d.seat == seat for d in game.scouts_done)


def scouting_seat(game: Game) -> int | None:
    # Who's making Scouts moves now: the player going first, then their
    # opponent - skipping one who's done or has no Scouts units. None once
    # neither has any to make (or before who goes first is decided).
    from app.services.in_game.battle_round import START_OF_ROUND

    if (
        game.status != "in_progress"
        or game.battle_round != 1
        or game.phase != START_OF_ROUND
        or game.first_seat is None
    ):
        return None
    for seat in (game.first_seat, 3 - game.first_seat):
        if not done(game, seat) and scout_units(game, seat):
            return seat
    return None


def waiting(game: Game) -> bool:
    return scouting_seat(game) is not None


def any_scouts(game: Game) -> bool:
    # Whether either player has a unit that can make a Scouts move.
    return any(scout_units(game, p.seat) for p in game.players)


def scout_move(game: Game, unit: Unit) -> GameUnitMove | None:
    # The unit's Scouts move, if it's made one.
    return next(
        (m for m in game.unit_moves if m.unit_id == unit.id and m.kind == SCOUT), None
    )


def start_positions(game: Game, unit: Unit) -> dict[int, tuple[float, float, float]]:
    # Where the unit's models were set up - where its Scouts move is measured
    # from.
    placed = deployment.positions(game)
    move = scout_move(game, unit)
    recorded = {s.unit_model_id: (s.x, s.y, s.rotation) for s in move.starts} if move else {}
    return {
        m.id: recorded.get(m.id, (placed[m.id].x, placed[m.id].y, placed[m.id].rotation))
        for m in unit.unit_models
        if m.id in placed
    }


def _check_unit(game: Game, seat: int, unit: Unit) -> None:
    if scouting_seat(game) != seat:
        raise _bad_request("it isn't that player's turn to make Scouts moves")
    if deployment.owner(game, unit).seat != seat:
        raise _bad_request("that isn't one of that player's units")
    if unit.id not in {u.id for u in scout_units(game, seat)}:
        raise _bad_request("every model in the unit must have Scouts")


def check(
    game: Game, seat: int, unit: Unit, placement: dict[int, tuple[float, float, float]]
) -> Placement:
    # Whether the unit could make a Scouts move to `placement`.
    _check_unit(game, seat, unit)
    return movement.check_free_move(
        game, unit, placement, start_positions(game, unit), float(distance(unit))
    )


def move(
    game: Game, seat: int, unit: Unit, placement: dict[int, tuple[float, float, float]]
) -> None:
    # Makes the unit's Scouts move, if it can.
    result = check(game, seat, unit, placement)
    if not result.valid:
        raise _bad_request("can't move it there: " + "; ".join(result.problems))
    start = start_positions(game, unit)
    record = scout_move(game, unit)
    if record is None:
        record = GameUnitMove(
            unit_id=unit.id, battle_round=0, turn_seat=seat, kind=SCOUT, completed=True
        )
        record.starts = [
            GameUnitMoveStart(unit_model_id=i, x=x, y=y, rotation=rotation)
            for i, (x, y, rotation) in start.items()
        ]
        game.unit_moves.append(record)
    movement.place(game, placement)


def finish(game: Game, seat: int) -> None:
    # The player is done making Scouts moves.
    if scouting_seat(game) != seat:
        raise _bad_request("it isn't that player's turn to make Scouts moves")
    game.scouts_done.append(GameScoutsDone(seat=seat))
