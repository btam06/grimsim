from __future__ import annotations

from fastapi import HTTPException

from app.models import Game, GameTeleportHomer, GameTeleportHomersDone, Unit
from app.services.in_game import deployment, regions
from app.services.in_game.deployment import TOLERANCE

# Teleport Homers: at the start of the battle, each of a player's units with
# the Teleport Homer ability can have one token set up anywhere on the
# battlefield (or none) - the game waits until both players are done. When
# that unit arrives from Strategic Reserves by Rapid Ingress, its player can
# use its token: the stratagem costs 1CP less, and the unit is set up with
# every model within 3" of the token (and, as ever, 8" from enemy models,
# but anywhere else) - then the token is removed. If an enemy unit ends a
# move within 1" of a token, it's removed.

TELEPORT_HOMER = "Teleport Homer"
HOMER_RANGE = 3.0
REMOVE_RANGE = 1.0
CP_DISCOUNT = 1
WIDTH, HEIGHT = deployment.BOARD[2]


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def has_homer(unit: Unit) -> bool:
    return any(a.name == TELEPORT_HOMER for m in unit.unit_models for a in m.model.abilities)


def homer_units(game: Game, seat: int) -> list[Unit]:
    # The player's units with the ability.
    player = next(p for p in game.players if p.seat == seat)
    return [u for u in deployment.deployable_units(player) if has_homer(u)]


def done(game: Game, seat: int) -> bool:
    return any(d.seat == seat for d in game.teleport_homers_done)


def waiting_seats(game: Game) -> list[int]:
    # The players still to set up their tokens, at the start of the battle.
    if game.status != "in_progress" or game.battle_round != 1:
        return []
    return [
        p.seat for p in game.players if homer_units(game, p.seat) and not done(game, p.seat)
    ]


def waiting(game: Game) -> bool:
    return bool(waiting_seats(game))


def token(game: Game, unit: Unit) -> GameTeleportHomer | None:
    # The unit's token on the battlefield, if it has one.
    return next(
        (h for h in game.teleport_homers if h.unit_id == unit.id and h.status == "placed"), None
    )


def place(game: Game, seat: int, unit: Unit, x: float, y: float) -> None:
    # The player sets up (or moves) the unit's token, at the start of the battle.
    if seat not in waiting_seats(game):
        raise _bad_request("Teleport Homer tokens are set up at the start of the battle")
    if deployment.owner(game, unit).seat != seat or not has_homer(unit):
        raise _bad_request("that unit has no Teleport Homer")
    if not (0 <= x <= WIDTH and 0 <= y <= HEIGHT):
        raise _bad_request("set the token up on the battlefield")
    existing = token(game, unit)
    if existing is not None:
        existing.x, existing.y = x, y
    else:
        game.teleport_homers.append(GameTeleportHomer(unit_id=unit.id, x=x, y=y))


def remove(game: Game, seat: int, unit: Unit) -> None:
    # Takes back a token set up at the start of the battle.
    if seat not in waiting_seats(game):
        raise _bad_request("Teleport Homer tokens are set up at the start of the battle")
    existing = token(game, unit)
    if existing is not None and deployment.owner(game, unit).seat == seat:
        game.teleport_homers.remove(existing)


def finish(game: Game, seat: int) -> None:
    # The player is done setting up their tokens.
    if seat not in waiting_seats(game):
        raise _bad_request("that player has no Teleport Homer tokens to set up now")
    game.teleport_homers_done.append(GameTeleportHomersDone(seat=seat))


def after_move(game: Game, unit: Unit) -> None:
    # A unit ended a move: its opponent's tokens within 1" of it are removed.
    seat = deployment.owner(game, unit).seat
    placed = deployment.positions(game)
    bases = [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    ]
    for homer in game.teleport_homers:
        if homer.status != "placed":
            continue
        owner = deployment.owner(game, deployment.find_unit(game, homer.unit_id)).seat
        if owner == seat:
            continue
        if any(
            regions.base_distance_to_point(b, (homer.x, homer.y)) <= REMOVE_RANGE + TOLERANCE
            for b in bases
        ):
            homer.status = "removed"


def homer_problems(game: Game, unit: Unit, base) -> list[str]:
    # What's wrong with a model of a unit arriving at its token: it has to be
    # within 3" of it.
    homer = token(game, unit)
    if homer is None:
        return ["has no Teleport Homer token on the battlefield"]
    if regions.base_distance_to_point(base, (homer.x, homer.y)) > HOMER_RANGE + TOLERANCE:
        return ['isn\'t within 3" of its Teleport Homer token']
    return []


def use(game: Game, unit: Unit) -> None:
    # The unit arrived at its token: it's removed.
    homer = token(game, unit)
    if homer is not None:
        homer.status = "used"
