from __future__ import annotations

import random

from fastapi import HTTPException

from app.models import Game, GameSurgeMove, Unit
from app.services.in_game import battle_shock, deployment, mission_state, movement, pathing
from app.services.in_game.deployment import TOLERANCE, Placement, gap

# Surge moves (21.02): a rule (an ability, enhancement or stratagem - e.g.
# a Necron unit that lost models to an enemy's shooting) lets a unit move up
# to a distance it states (rolled, for D6"). Its player says when the rule's
# been triggered; the unit can surge if it isn't Battle-shocked, is
# unengaged and hasn't moved this phase. Its surge target is the closest
# enemy unit (ignoring AIRCRAFT, unless it can FLY - 23.02). Each model that
# moves ends engaged with the target or closer to it, and the unit can't end
# engaged with any other enemy unit; then it can't move again this phase.
# (That each model ends engaged "if possible", and otherwise as close as
# possible, is left to the player.)

AIRCRAFT = "AIRCRAFT"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _this_phase(game: Game, record) -> bool:
    return (
        record.battle_round == game.battle_round
        and record.turn_seat == game.turn_seat
        and record.phase == game.phase
    )


def surge_of(game: Game, unit: Unit) -> GameSurgeMove | None:
    # The unit's surge move this phase, if a rule's let it make one.
    return next(
        (r for r in game.surge_moves if r.unit_id == unit.id and _this_phase(game, r)), None
    )


def _bases(game: Game, unit: Unit) -> dict:
    placed = deployment.positions(game)
    return {
        m.id: deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    }


def surge_target(game: Game, unit: Unit) -> Unit | None:
    # The closest enemy unit (not AIRCRAFT, unless the unit can FLY).
    from app.services.in_game.charging import distance, enemy_units

    flies = movement.can_fly(unit)
    candidates = [
        e
        for e in enemy_units(game, unit)
        if flies or not any(k.name == AIRCRAFT for m in e.unit_models for k in m.model.keywords)
    ]
    return min(candidates, key=lambda e: distance(game, unit, e), default=None)


def reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't start a surge move now, or None if it can.
    if game.status != "in_progress":
        return "the game isn't in progress"
    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if surge_of(game, unit) is not None:
        return "it has already surged this phase"
    if battle_shock.is_battle_shocked(game, unit):
        return "it's Battle-shocked"
    if movement.in_engagement_range(game, unit):
        return "it's engaged"
    move = movement.unit_move(game, unit)
    if game.phase == "movement" and move is not None and move.completed:
        return "it has moved this phase"
    if surge_target(game, unit) is None:
        return "there's no enemy unit to surge towards"
    return None


def start(game: Game, unit: Unit, distance: str) -> GameSurgeMove:
    # A rule lets the unit surge up to `distance` ("D6" - rolled now - or a
    # number of inches).
    if (why := reason(game, unit)) is not None:
        raise _bad_request(f"it can't make a surge move: {why}")
    if distance.upper() == "D6":
        inches = random.randint(1, 6)
    elif distance.isdigit():
        inches = int(distance)
    else:
        raise _bad_request('a surge move goes "D6" or a number of inches')
    record = GameSurgeMove(
        unit_id=unit.id,
        target_unit_id=surge_target(game, unit).id,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        phase=game.phase,
        distance=inches,
    )
    game.surge_moves.append(record)
    return record


def check(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> Placement:
    # Whether the unit could make its surge move to `placement`.
    record = surge_of(game, unit)
    if record is None or record.made:
        raise _bad_request("it has no surge move to make now")
    target = deployment.find_unit(game, record.target_unit_id)
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    start_bases = _bases(game, unit)
    problems = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    pather = pathing.for_unit(game, unit, start_bases, record.distance)
    theirs = list(_bases(game, target).values())
    seat = deployment.owner(game, unit).seat
    others = [
        b for p, m, b in deployment.placed_bases(game, unit)
        if p.seat != seat and m.unit_id != target.id
    ]

    def nearest(base) -> float:
        return min((gap(base, t) for t in theirs), default=0)

    for model in models:
        found = []
        start_, end = start_bases[model.id], bases[model.id]
        if (end.x, end.y) != (start_.x, start_.y):
            if problem := pathing.too_far(pather, start_, end, record.distance):
                found.append(problem)
            if (
                nearest(end) > movement.ENGAGEMENT_RANGE + TOLERANCE
                and nearest(end) >= nearest(start_) - TOLERANCE
            ):
                found.append(f"must end closer to {target.label}")
        if any(gap(end, o) <= movement.ENGAGEMENT_RANGE + TOLERANCE for o in others):
            found.append(f"would end engaged with an enemy unit other than {target.label}")
        problems[model.id] = found + problems[model.id]
    result = deployment.summarise(models, problems)
    result.paths = pather.bends(start_bases, bases)
    return result


def make(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # The unit makes its surge move, if it can move like that.
    result = check(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't surge there: " + "; ".join(result.problems))
    movement.place(game, placement)
    surge_of(game, unit).made = True
    mission_state.after_move(game, unit)


def available(game: Game) -> list[tuple[Unit, GameSurgeMove]]:
    # The surge moves waiting to be made this phase.
    return [
        (deployment.find_unit(game, r.unit_id), r)
        for r in game.surge_moves
        if _this_phase(game, r) and not r.made
    ]
