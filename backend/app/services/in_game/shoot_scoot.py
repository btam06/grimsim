from __future__ import annotations

from fastapi import HTTPException

from app.models import Game, Unit
from app.services.in_game import deployment, mission_state, movement
from app.services.in_game.deployment import Placement

# Moving after shooting (shoot and scoot): some abilities let a unit, in its
# player's Shooting phase, after it has shot, if it isn't within Engagement
# Range of an enemy unit, make a Normal move (see movement.check_free_move) -
# once a turn. Each faction's abilities say how (datasheet_abilities
# SHOOT_SCOOT: {ability name: {"reach": inches, "further": (inches, keywords,
# inches) - further, if every model ends wholly within that of a friendly
# unit with those keywords - "no_charge": whether it then can't declare a
# charge this turn}} - e.g. Ride the Thermals).

# The unit moved after shooting this turn (kept as a marked unit - see
# app/services/in_game/mission_state.py).
SCOOTED = "shoot_scoot"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def move_of(unit: Unit) -> tuple[str, dict] | None:
    # The unit's ability that lets it move after shooting, and how, if any.
    from app.seeds import datasheet_abilities

    config = datasheet_abilities.SHOOT_SCOOT
    return next(
        (
            (a.name, config[a.name])
            for m in unit.unit_models
            for a in m.model.abilities
            if a.name in config
        ),
        None,
    )


def reach(unit: Unit) -> float | None:
    # The furthest the unit can move after shooting, if it can.
    found = move_of(unit)
    if found is None:
        return None
    further = found[1].get("further")
    return further[0] if further else found[1]["reach"]


def _scoot(game: Game, unit: Unit):
    return next(
        (
            m
            for m in mission_state.marked(game, SCOOTED)
            if m.unit_id == unit.id
            and m.battle_round == game.battle_round
            and m.turn_seat == game.turn_seat
        ),
        None,
    )


def moved(game: Game, unit: Unit) -> bool:
    # Whether the unit moved after shooting this turn.
    return _scoot(game, unit) is not None


def no_charge(game: Game, unit: Unit) -> bool:
    # Whether moving after shooting this turn stops the unit declaring a
    # charge.
    found = move_of(unit)
    return moved(game, unit) and found is not None and found[1].get("no_charge", False)


def reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't move after shooting now, or None if it can.
    # (Imported here: shooting imports what imports this.)
    from app.services.in_game import shooting

    found = move_of(unit)
    if found is None:
        return "it has no ability to move after shooting"
    if not shooting.is_shooting_phase(game) or deployment.owner(game, unit).seat != game.turn_seat:
        return f"{found[0]} is used in its player's Shooting phase"
    if shooting.unit_shot(game, unit) is None:
        return f"{found[0]} is used after it has shot"
    if moved(game, unit):
        return "it has already moved after shooting this turn"
    if movement.in_engagement_range(game, unit):
        return "it's within Engagement Range of an enemy unit"
    return None


def check(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> Placement:
    # Whether the unit could move after shooting to `placement`.
    if (why := reason(game, unit)) is not None:
        raise _bad_request(f"it can't move after shooting: {why}")
    name, how = move_of(unit)
    return movement.check_reach_or_further(
        game, unit, placement, how["reach"], how.get("further"), name
    )


def scoot(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # The unit moves after shooting, if it can move like that.
    result = check(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't move it there: " + "; ".join(result.problems))
    movement.place(game, placement)
    mission_state.mark(game, deployment.owner(game, unit).seat, SCOOTED, unit.id)
    mission_state.after_move(game, unit)
