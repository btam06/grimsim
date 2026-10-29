from __future__ import annotations

import re

from fastapi import HTTPException

from app.models import (
    Game,
    GameModelPosition,
    GameScoutsDone,
    GameUnitMove,
    GameUnitMoveStart,
    Unit,
    UnitModel,
)
from app.services.in_game import deployment, movement
from app.services.in_game.deployment import Placement

# Scouts (24.31-24.32): in the Resolve Pre-battle Abilities step - once both
# armies are set up and who goes first is decided (see
# app/services/in_game/first_turn.py), before the first battle round - each
# unit whose every model has Scouts X" (its own ability, or from its wargear,
# e.g. an Orbital Comms Array's "This unit has Scouts 6\"") can:
# - if it's wholly within its deployment zone, make a scout move: up to X",
#   ending more than 8" from every enemy unit (and on the battlefield, not
#   overlapping other models or terrain features, in coherency);
# - if it's in Strategic Reserves, be set up anywhere wholly within its
#   deployment zone instead;
# - if it's embarked in a DEDICATED TRANSPORT wholly within its deployment
#   zone, and every model embarked in it has Scouts, have that transport make
#   the scout move (the shortest X of those inside).
# The player going first makes theirs, then their opponent; each says when
# they're done (a player with no such unit is skipped), and the battle waits
# for both. Until then, a unit can be moved again, measured from where it was
# set up.
# The kind of move (see GameUnitMove) a Scouts move is - recorded in battle
# round 0, before the battle.
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


ENEMY_CLEARANCE = 8.0
DEDICATED_TRANSPORT = "DEDICATED TRANSPORT"


def _passengers(game: Game, transport: Unit) -> list[Unit]:
    from app.services.in_game import embarked

    seat = deployment.owner(game, transport).seat
    return [u for u, carrier in embarked.embarked_units(game, seat) if carrier.id == transport.id]


def scout_distance(game: Game, unit: Unit) -> int:
    # How far the unit can make a scout move now: its own Scouts - or, for a
    # DEDICATED TRANSPORT, its passengers' (if every one has it). 0 if none.
    if distance(unit):
        return distance(unit)
    keywords = {k.name for m in unit.unit_models for k in m.model.keywords}
    if DEDICATED_TRANSPORT not in keywords:
        return 0
    inside = _passengers(game, unit)
    distances = [distance(u) for u in inside]
    return min(distances) if inside and all(distances) else 0


def in_reserves(game: Game, unit: Unit) -> bool:
    f = deployment.battle_formation(game, unit)
    return f is not None and f.place == "reserves"


def _wholly_in_zone(game: Game, unit: Unit) -> bool:
    layout = game.layout
    if layout is None or layout.deployment is None:
        return True
    zone = layout.deployment.zone(deployment._side(game, deployment.owner(game, unit)))
    placed = deployment.positions(game)
    start = start_positions(game, unit)
    models = {m.id: m for m in unit.unit_models}
    return all(
        deployment.wholly_inside(deployment.base_at(models[i], *xyr), zone)
        for i, xyr in start.items()
        if i in placed
    )


def scout_units(game: Game, seat: int) -> list[Unit]:
    # The player's units that can use Scouts: on the battlefield wholly
    # within their deployment zone (themselves, or a DEDICATED TRANSPORT of
    # Scouts), or in Strategic Reserves.
    player = next(p for p in game.players if p.seat == seat)
    placed = deployment.positions(game)
    found = []
    for u in deployment.deployable_units(player):
        if deployment.is_deployed(u, placed):
            if scout_distance(game, u) and _wholly_in_zone(game, u):
                found.append(u)
        elif in_reserves(game, u) and distance(u):
            found.append(u)
    return found


def done(game: Game, seat: int) -> bool:
    return any(d.seat == seat for d in game.scouts_done)


def scouting_seat(game: Game) -> int | None:
    # Who's making Scouts moves now: the player going first, then their
    # opponent - skipping one who's done or has no Scouts units. None once
    # neither has any to make (or before who goes first is decided).
    if deployment.deployment_step(game) != "pre_battle":
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
    # Whether the unit could make a Scouts move to `placement` - or, from
    # Strategic Reserves, be set up there (wholly within its deployment zone).
    _check_unit(game, seat, unit)
    if in_reserves(game, unit):
        return deployment.check_placement(game, unit, placement)
    result = movement.check_free_move(
        game, unit, placement, start_positions(game, unit), float(scout_distance(game, unit))
    )
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    enemies = [
        b for p, _, b in deployment.placed_bases(game, unit) if p.seat != seat
    ]
    if any(
        deployment.gap(b, e) <= ENEMY_CLEARANCE + deployment.TOLERANCE
        for b in bases.values()
        for e in enemies
    ):
        result.problems.append('It must end more than 8" from every enemy unit')
    return result


def move(
    game: Game, seat: int, unit: Unit, placement: dict[int, tuple[float, float, float]]
) -> None:
    # Makes the unit's Scouts move, if it can.
    result = check(game, seat, unit, placement)
    if not result.valid:
        raise _bad_request("can't move it there: " + "; ".join(result.problems))
    if in_reserves(game, unit):
        # Set up from Strategic Reserves, as when deploying.
        game.battle_formations.remove(deployment.battle_formation(game, unit))
        for unit_model_id, (x, y, rotation) in placement.items():
            game.model_positions.append(
                GameModelPosition(unit_model_id=unit_model_id, x=x, y=y, rotation=rotation)
            )
        return
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
