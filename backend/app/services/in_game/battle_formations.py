from __future__ import annotations

from fastapi import HTTPException

from app.models import Game, GameBattleFormation, GameFormationsDone, GamePlayer, Unit
from app.models.game import FORMATION_PLACES
from app.services.in_game import deployment

# Declaring battle formations, at the start of deployment: each player says
# which of their units won't be set up on the battlefield -
#
# - In Strategic Reserves: up to half their army's points (by its units'
#   points) can be.
# - Embarked in a transport: in one of their TRANSPORT units (which can't
#   itself embark). It doesn't count towards Strategic Reserves. (Transport
#   capacity, and what can embark in what, aren't checked.)
#
# Neither is deployed. Each player says when they're done; once both are,
# deployment begins (see app/services/in_game/deployment.py).

RESERVES_SHARE = 0.5
TRANSPORT = "TRANSPORT"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def is_transport(unit: Unit) -> bool:
    return any(k.name == TRANSPORT for m in unit.unit_models for k in m.model.keywords)


def army_points(game: Game, player: GamePlayer) -> int:
    return sum(u.points for u in deployment.deployable_units(player))


def reserves_limit(game: Game, player: GamePlayer) -> int:
    # How many points can be in Strategic Reserves: half the army's.
    return int(army_points(game, player) * RESERVES_SHARE)


def reserves_points(game: Game, player: GamePlayer) -> int:
    return sum(
        u.points
        for u in deployment.deployable_units(player)
        if (f := deployment.battle_formation(game, u)) is not None and f.place == "reserves"
    )


def done(game: Game, seat: int) -> bool:
    return any(d.seat == seat for d in game.formations_done)


def _player(game: Game, seat: int) -> GamePlayer:
    return next(p for p in game.players if p.seat == seat)


def set_formation(
    game: Game, seat: int, unit: Unit, place: str | None, transport: Unit | None = None
) -> None:
    # Puts the player's unit in Strategic Reserves, embarks it in a transport,
    # or (place None) back on the battlefield.
    if deployment.deployment_step(game) != "formations":
        raise _bad_request("battle formations are declared at the start of deployment")
    if done(game, seat):
        raise _bad_request("that player has already declared their battle formations")
    player = _player(game, seat)
    units = {u.id for u in deployment.deployable_units(player)}
    if unit.id not in units:
        raise _bad_request("that isn't one of that player's units")
    if place is not None and place not in FORMATION_PLACES:
        raise _bad_request(f"unknown place {place!r}")

    if place == "embarked":
        if transport is None or transport.id not in units:
            raise _bad_request("choose one of the player's transports to embark in")
        if not is_transport(transport):
            raise _bad_request(f"{transport.faction_unit.name} isn't a TRANSPORT")
        if is_transport(unit):
            raise _bad_request("a TRANSPORT can't embark in another")
    if place == "reserves":
        current = deployment.battle_formation(game, unit)
        already = current is not None and current.place == "reserves"
        total = reserves_points(game, player) + (0 if already else unit.points)
        limit = reserves_limit(game, player)
        if total > limit:
            raise _bad_request(
                f"that would put {total} points in Strategic Reserves (at most {limit}: "
                "half the army's points)"
            )

    existing = deployment.battle_formation(game, unit)
    if existing is not None:
        game.battle_formations.remove(existing)
    if place is not None:
        game.battle_formations.append(
            GameBattleFormation(
                unit_id=unit.id,
                place=place,
                transport_unit_id=transport.id if place == "embarked" else None,
            )
        )


def declare(game: Game, seat: int) -> None:
    # The player has declared their battle formations.
    if deployment.deployment_step(game) != "formations":
        raise _bad_request("battle formations are declared at the start of deployment")
    if done(game, seat):
        raise _bad_request("that player has already declared their battle formations")
    game.formations_done.append(GameFormationsDone(seat=seat))
