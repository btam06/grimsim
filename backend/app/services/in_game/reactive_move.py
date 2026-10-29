from __future__ import annotations

import random

from fastapi import HTTPException

from app.models import Game, GameReactiveMove, Unit
from app.services.in_game import deployment, mission_state, movement, reinforcements
from app.services.in_game.deployment import TOLERANCE, Placement, gap

# Reactive moves: some abilities let a unit move in its opponent's Movement
# phase, when an enemy unit ends a move within a distance of it, if it isn't
# within Engagement Range of an enemy unit (datasheet_abilities
# REACTIVE_MOVES: {ability name: {"trigger_range": inches, "reach": a D6
# roll ("D6") or inches, "further": (inches, keywords, inches) - up to that,
# if every model ends wholly within the last inches of a friendly unit with
# those keywords}} - e.g. Tactica Obliqua). Once a phase each: the move
# waits until its player makes it (rolling for how far first), or the
# phase ends.


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def move_of(unit: Unit) -> tuple[str, dict] | None:
    # The unit's ability that lets it make a reactive move, and how, if any.
    from app.seeds import datasheet_abilities

    config = datasheet_abilities.REACTIVE_MOVES
    return next(
        (
            (a.name, config[a.name])
            for m in unit.unit_models
            for a in m.model.abilities
            if a.name in config
        ),
        None,
    )


def _this_phase(game: Game, record) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def offer(game: Game, unit: Unit) -> GameReactiveMove | None:
    # The unit's reactive move this phase, if it has one (made or not).
    return next(
        (r for r in game.reactive_moves if r.unit_id == unit.id and _this_phase(game, r)), None
    )


def after_enemy_move(game: Game, mover: Unit) -> None:
    # The unit ended a move in its player's Movement phase: their opponent's
    # units with a reactive move it ended within range of can make it (once
    # a phase).
    if game.phase != "movement":
        return
    seat = deployment.owner(game, mover).seat
    placed = deployment.positions(game)
    bases = list(_bases(game, mover))
    for player in game.players:
        if player.seat == seat:
            continue
        for unit in deployment.deployable_units(player):
            found = move_of(unit)
            if found is None or offer(game, unit) is not None:
                continue
            if not deployment.is_deployed(unit, placed):
                continue
            reach = found[1]["trigger_range"]
            if any(gap(b, o) <= reach + TOLERANCE for b in bases for o in _bases(game, unit)):
                game.reactive_moves.append(
                    GameReactiveMove(
                        unit_id=unit.id,
                        trigger_unit_id=mover.id,
                        battle_round=game.battle_round,
                        turn_seat=game.turn_seat,
                    )
                )


def _bases(game: Game, unit: Unit):
    placed = deployment.positions(game)
    return [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    ]


def available(game: Game) -> list[tuple[Unit, str, dict, GameReactiveMove]]:
    # The reactive moves that can be made now: (unit, ability, how, offer).
    if game.status != "in_progress" or game.phase != "movement":
        return []
    found = []
    for record in game.reactive_moves:
        if record.made or not _this_phase(game, record):
            continue
        unit = deployment.find_unit(game, record.unit_id)
        how = move_of(unit)
        if how is not None and reason(game, unit) is None:
            found.append((unit, how[0], how[1], record))
    return found


def reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't make its reactive move now, or None if it can.
    record = offer(game, unit)
    if game.phase != "movement" or record is None:
        return "no enemy unit has ended a move close enough to it this phase"
    if record.made:
        return "it has already made its reactive move this phase"
    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if movement.in_engagement_range(game, unit):
        return "it's within Engagement Range of an enemy unit"
    if reinforcements.ingressed(game, unit):
        return "it made an ingress move: no other move until the Charge phase"
    return None


def _reach(how: dict, record: GameReactiveMove) -> float:
    return float(record.roll if how["reach"] == "D6" else how["reach"])


def roll(game: Game, unit: Unit) -> GameReactiveMove:
    # Rolls for how far the unit's reactive move can go (once).
    if (why := reason(game, unit)) is not None:
        raise _bad_request(f"it can't make a reactive move: {why}")
    record = offer(game, unit)
    if record.roll is None:
        _, how = move_of(unit)
        record.roll = random.randint(1, 6) if how["reach"] == "D6" else int(how["reach"])
    return record


def check(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> Placement:
    # Whether the unit could make its reactive move to `placement` (once it's
    # rolled for it).
    record = roll(game, unit)
    name, how = move_of(unit)
    return movement.check_reach_or_further(
        game, unit, placement, _reach(how, record), how.get("further"), name
    )


def make(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # The unit makes its reactive move, if it can move like that.
    result = check(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't move it there: " + "; ".join(result.problems))
    movement.place(game, placement)
    offer(game, unit).made = True
    mission_state.after_move(game, unit)
