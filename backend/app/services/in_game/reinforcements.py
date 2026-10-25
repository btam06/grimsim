from __future__ import annotations

from fastapi import HTTPException

from app.models import (
    Game,
    GameModelDamage,
    GameModelPosition,
    GameMovementEnded,
    GameUnitMove,
    Unit,
)
from app.models.game import RESERVES_DESTROYED
from app.services.in_game import deployment
from app.services.in_game.deployment import TOLERANCE, Base, Placement, gap

# Bringing units in from Strategic Reserves (see
# app/services/in_game/battle_formations.py). In their movement phase, from
# the second battle round, a player can set up their units from Reserves -
# each counts as having made a Normal move (it can't move again that phase):
#
# - every model at least 8" from every enemy model;
# - in the second battle round, wholly within 6" of a battlefield edge, and
#   not in the opponent's deployment zone; from the third, wholly within 6"
#   of a battlefield edge;
# - a unit whose every model has Deep Strike can be set up anywhere (still 8"
#   from enemy models);
# - on the battlefield, not overlapping other models or terrain features, and
#   in coherency, as when deploying (see app/services/in_game/deployment.py).
#
# At the end of their opponent's movement phase (once they've finished
# moving), a player can use the Rapid Ingress stratagem to set up a unit
# from Reserves the same way. A Strategic Reserves unit that hasn't arrived by
# the end of the third battle round is destroyed.

FIRST_ROUND = 2
LAST_ROUND = 3
ENEMY_DISTANCE = 8.0
EDGE_DISTANCE = 6.0
DEEP_STRIKE = "Deep Strike"
RAPID_INGRESS = "Rapid Ingress"
# The kind of move (see GameUnitMove) a unit's arrival counts as.
ARRIVED = "reinforcements"
BOARD_WIDTH, BOARD_HEIGHT = 60.0, 44.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def in_reserves(game: Game, unit: Unit) -> bool:
    f = deployment.battle_formation(game, unit)
    return f is not None and f.place == "reserves"


def reserve_units(game: Game, seat: int) -> list[Unit]:
    # The player's units still in Strategic Reserves.
    player = next(p for p in game.players if p.seat == seat)
    return [u for u in deployment.deployable_units(player) if in_reserves(game, u)]


def has_deep_strike(unit: Unit) -> bool:
    return all(any(a.name == DEEP_STRIKE for a in m.model.abilities) for m in unit.unit_models)


def movement_ended(game: Game) -> bool:
    # Whether the player whose turn it is has finished moving this movement
    # phase (it's the end of the phase: Rapid Ingress time).
    return any(
        m.battle_round == game.battle_round and m.turn_seat == game.turn_seat
        for m in game.movements_ended
    )


def end_movement(game: Game) -> None:
    game.movements_ended.append(
        GameMovementEnded(battle_round=game.battle_round, turn_seat=game.turn_seat)
    )


def arrival_round(game: Game) -> bool:
    # Whether units can arrive from Reserves this battle round.
    return game.battle_round >= FIRST_ROUND


def _extent(base: Base) -> tuple[float, float, float, float]:
    points = deployment.outline(base)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def near_an_edge(base: Base) -> bool:
    # Wholly within 6" of a battlefield edge.
    x0, y0, x1, y1 = _extent(base)
    d = EDGE_DISTANCE + TOLERANCE
    return x1 <= d or x0 >= BOARD_WIDTH - d or y1 <= d or y0 >= BOARD_HEIGHT - d


def check_turn(game: Game, unit: Unit, rapid_ingress: bool = False) -> None:
    # That the unit can arrive now: it's in Strategic Reserves, it's the
    # movement phase of a battle round units can arrive in, and it's its
    # owner's turn to move (and they haven't finished) - or, with Rapid
    # Ingress, it's the end of their opponent's.
    if game.status != "in_progress" or game.phase != "movement":
        raise _bad_request("units arrive from Reserves in the movement phase")
    if not in_reserves(game, unit):
        raise _bad_request("that unit isn't in Strategic Reserves")
    if not arrival_round(game):
        raise _bad_request("units can't arrive from Reserves in the first battle round")
    seat = deployment.owner(game, unit).seat
    if rapid_ingress:
        if seat == game.turn_seat:
            raise _bad_request("Rapid Ingress is used in the opponent's movement phase")
        if not movement_ended(game):
            raise _bad_request("Rapid Ingress is used at the end of the movement phase")
    else:
        if seat != game.turn_seat:
            raise _bad_request("only the player whose turn it is can bring units in")
        if movement_ended(game):
            raise _bad_request("the movement phase is over")


def check_arrival(
    game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]
) -> Placement:
    # Whether the unit could arrive with its models at `placement`.
    models, bases = deployment.unit_bases(unit, placement)
    others = deployment.placed_bases(game, unit)
    seat = deployment.owner(game, unit).seat
    enemies = [b for p, _, b in others if p.seat != seat]
    problems = deployment.physical_problems(game, models, bases, others)
    deep_strike = has_deep_strike(unit)
    layout = game.layout
    side = "attacker" if seat == game.attacker_seat else "defender"
    enemy_side = "defender" if side == "attacker" else "attacker"
    enemy_zone = layout.deployment.zone(enemy_side) if layout and layout.deployment else None
    for model in models:
        base = bases[model.id]
        found = []
        if any(gap(base, e) < ENEMY_DISTANCE - TOLERANCE for e in enemies):
            found.append('is within 8" of an enemy model')
        if not deep_strike:
            if not near_an_edge(base):
                found.append('isn\'t wholly within 6" of a battlefield edge')
            elif (
                game.battle_round == FIRST_ROUND
                and enemy_zone
                and deployment.distance_to_polygon(base, enemy_zone) <= TOLERANCE
            ):
                found.append("is in the enemy deployment zone")
        problems[model.id] = found + problems[model.id]
    return deployment.summarise(models, problems)


def bring_in(
    game: Game,
    unit: Unit,
    placement: dict[int, tuple[float, float, float]],
    rapid_ingress: bool = False,
) -> None:
    # Sets the unit up from Reserves, if it can arrive like that. Brought in in
    # its own movement phase, it counts as having made a Normal move.
    check_turn(game, unit, rapid_ingress)
    result = check_arrival(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't bring it in there: " + "; ".join(result.problems))
    for unit_model_id, (x, y, rotation) in placement.items():
        game.model_positions.append(
            GameModelPosition(unit_model_id=unit_model_id, x=x, y=y, rotation=rotation)
        )
    game.battle_formations.remove(deployment.battle_formation(game, unit))
    if not rapid_ingress:
        game.unit_moves.append(
            GameUnitMove(
                unit_id=unit.id,
                battle_round=game.battle_round,
                turn_seat=game.turn_seat,
                kind=ARRIVED,
                completed=True,
            )
        )


def destroy_unarrived(game: Game) -> None:
    # At the end of the third battle round: every unit still in Strategic
    # Reserves is destroyed.
    for player in game.players:
        for unit in reserve_units(game, player.seat):
            deployment.battle_formation(game, unit).place = RESERVES_DESTROYED
            # Destroyed off the battlefield: not a kill for missions (it isn't
            # in the turn record - see app/services/in_game/turn_record.py).
            for unit_model in unit.unit_models:
                game.model_damage.append(
                    GameModelDamage(
                        unit_model_id=unit_model.id,
                        wounds_lost=unit_model.model.wounds,
                        destroyed=True,
                    )
                )
