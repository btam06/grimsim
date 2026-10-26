from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException

from app.models import Game, Unit
from app.services.in_game import deployment, regions
from app.services.in_game.deployment import TOLERANCE

# Tokens a rule has a unit set up on the battlefield (e.g. a Teleport Homer -
# see app/seeds/factions/space_marines/teleport_homer.py): one per unit, at a
# point, with a `status` - "placed" while it's on the battlefield, then
# "used" (the rule used it) or "removed" (e.g. an enemy unit came too close).
# The rule keeps its tokens in its own table (each row has unit_id, x, y and
# status) and passes them in.

PLACED, USED, REMOVED = "placed", "used", "removed"
WIDTH, HEIGHT = deployment.BOARD[2]


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def token(tokens: list, unit: Unit):
    # The unit's token on the battlefield, if it has one.
    return next((t for t in tokens if t.unit_id == unit.id and t.status == PLACED), None)


def place(tokens: list, unit: Unit, x: float, y: float, make: Callable) -> None:
    # Sets up (or moves) the unit's token at (x, y), which must be on the
    # battlefield; `make(unit_id=, x=, y=)` makes a new row, added to `tokens`.
    if not (0 <= x <= WIDTH and 0 <= y <= HEIGHT):
        raise _bad_request("set the token up on the battlefield")
    existing = token(tokens, unit)
    if existing is not None:
        existing.x, existing.y = x, y
    else:
        tokens.append(make(unit_id=unit.id, x=x, y=y))


def take_back(tokens: list, unit: Unit) -> None:
    # Takes the unit's token off the battlefield, as if it had never been set
    # up.
    existing = token(tokens, unit)
    if existing is not None:
        tokens.remove(existing)


def within(base, placed_token, reach: float) -> bool:
    # Whether a model's base is within `reach` inches of the token.
    return (
        regions.base_distance_to_point(base, (placed_token.x, placed_token.y))
        <= reach + TOLERANCE
    )


def remove_near(game: Game, tokens: list, unit: Unit, reach: float) -> None:
    # The unit ended a move: its opponent's tokens within `reach` inches of
    # any of its models are removed.
    seat = deployment.owner(game, unit).seat
    placed = deployment.positions(game)
    bases = [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    ]
    for placed_token in tokens:
        if placed_token.status != PLACED:
            continue
        owner = deployment.owner(game, deployment.find_unit(game, placed_token.unit_id)).seat
        if owner != seat and any(within(b, placed_token, reach) for b in bases):
            placed_token.status = REMOVED


def use(tokens: list, unit: Unit) -> None:
    # The rule has used the unit's token: it's gone from the battlefield.
    existing = token(tokens, unit)
    if existing is not None:
        existing.status = USED
