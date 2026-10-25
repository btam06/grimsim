from __future__ import annotations

import math
import random

from fastapi import HTTPException

from app.models import Game, GameUnitCharge, Unit
from app.services.in_game import command_phase, deployment, pathing
from app.services.in_game.deployment import TOLERANCE, Base, Placement, gap
from app.services.in_game.movement import ENGAGEMENT_RANGE

# Charging in the charge phase. In their turn's charge phase a player can
# charge with each of their units once - any unit on the battlefield can,
# but one that Advanced or Fell Back this turn (unless an ability selected in
# the Command phase lets it - see app/services/in_game/command_phase.py):
#
# - Roll the charge first: 2D6, kept for the phase (rolling again gives the
#   same roll).
# - Its targets are the enemy units it could reach: one of its models within
#   the roll of one of theirs, base to base (terrain and other units aren't
#   in the way of that). If none is, the charge fails - it doesn't move.
# - Its models then move up to the roll each (how far its base's centre goes,
#   as with moving - see app/services/in_game/movement.py), into Engagement Range of
#   the target with every model they can: at least one must get there, and
#   each one that doesn't (no room, or no way through) must end closer to the
#   target than it started. Where they end up must be on the battlefield, not
#   overlapping other models or terrain features, and in coherency (see
#   app/services/in_game/deployment.py).

CHARGE_DICE = 2


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def is_charge_phase(game: Game) -> bool:
    return game.status == "in_progress" and game.phase == "charge"


def unit_charge(game: Game, unit: Unit) -> GameUnitCharge | None:
    # The unit's charge this phase (rolled, or made), if any.
    return next(
        (
            c
            for c in game.unit_charges
            if c.unit_id == unit.id
            and c.battle_round == game.battle_round
            and c.turn_seat == game.turn_seat
        ),
        None,
    )


def charging_units(game: Game) -> list[Unit]:
    # The units the player whose turn it is has on the battlefield.
    if game.turn_seat is None:
        return []
    player = next(p for p in game.players if p.seat == game.turn_seat)
    placed = deployment.positions(game)
    return [
        u for u in deployment.deployable_units(player) if deployment.is_deployed(u, placed)
    ]


def _bases(game: Game, unit: Unit) -> dict[int, Base]:
    placed = deployment.positions(game)
    return {
        m.id: deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    }


def cant_charge_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't declare a charge this turn because of how it moved
    # (it Advanced or Fell Back), or None.
    # (Imported here: shooting imports movement, which charging's callers use.)
    from app.services.in_game.shooting import move_status

    status = move_status(game, unit)
    if status.advanced and not command_phase.eligible_after(game, unit, "advanced"):
        return "it Advanced this turn"
    if status.fell_back and not command_phase.eligible_after(game, unit, "fell_back"):
        return "it Fell Back this turn"
    return None


def _check_unit(game: Game, unit: Unit) -> None:
    # That the unit can charge now: the charge phase of its owner's turn, it's
    # on the battlefield, it didn't Advance or Fall Back this turn, and it
    # hasn't charged yet this phase.
    if not is_charge_phase(game):
        raise _bad_request("units can only charge in the charge phase")
    if deployment.owner(game, unit).seat != game.turn_seat:
        raise _bad_request("only the player whose turn it is can charge with their units")
    if not deployment.is_deployed(unit, deployment.positions(game)):
        raise _bad_request("that unit isn't on the battlefield")
    charge = unit_charge(game, unit)
    if charge is not None and charge.completed:
        raise _bad_request("that unit has already charged this phase")
    if (reason := cant_charge_reason(game, unit)) is not None:
        raise _bad_request(f"it can't charge: {reason}")


def roll_charge(game: Game, unit: Unit) -> GameUnitCharge:
    # Rolls the unit's charge (2D6) - once a phase: if it's already rolled,
    # that roll stands.
    _check_unit(game, unit)
    if (charge := unit_charge(game, unit)) is not None:
        return charge
    first, second = (random.randint(1, 6) for _ in range(CHARGE_DICE))
    charge = GameUnitCharge(
        unit_id=unit.id,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        first_die=first,
        second_die=second,
        completed=False,
    )
    game.unit_charges.append(charge)
    return charge


def enemy_units(game: Game, unit: Unit) -> list[Unit]:
    seat = deployment.owner(game, unit).seat
    placed = deployment.positions(game)
    return [
        u
        for player in game.players
        if player.seat != seat
        for u in deployment.deployable_units(player)
        if deployment.is_deployed(u, placed)
    ]


def distance(game: Game, unit: Unit, target: Unit) -> float:
    # The closest any of the unit's models is to any of the target's, base to
    # base.
    targets = list(_bases(game, target).values())
    return min(
        (gap(base, t) for base in _bases(game, unit).values() for t in targets),
        default=math.inf,
    )


def in_reach(game: Game, unit: Unit, target: Unit, roll: int) -> bool:
    # Whether the unit can charge the target with that roll.
    return distance(game, unit, target) <= roll + TOLERANCE


def failed(game: Game, unit: Unit) -> bool:
    # It's rolled, and no enemy unit is in reach: the charge fails.
    charge = unit_charge(game, unit)
    return (
        charge is not None
        and not charge.completed
        and not any(in_reach(game, unit, t, charge.roll) for t in enemy_units(game, unit))
    )


def _nearest(base: Base, targets: list[Base]) -> float:
    return min(gap(base, t) for t in targets)


def check_charge(
    game: Game, unit: Unit, target: Unit, placement: dict[int, tuple[float, float, float]]
) -> Placement:
    # Whether the unit could charge the target, its models ending at
    # `placement` ((x, y, rotation) by unit model id - every one it has left,
    # moved or not).
    _check_unit(game, unit)
    charge = unit_charge(game, unit)
    if charge is None:
        raise _bad_request("roll the charge first")
    if target.id not in {u.id for u in enemy_units(game, unit)}:
        raise _bad_request("the target must be an enemy unit on the battlefield")
    if not in_reach(game, unit, target, charge.roll):
        raise _bad_request(
            f"{target.faction_unit.name} is out of reach: the closest model is "
            f'{distance(game, unit, target):.1f}" away (rolled {charge.roll})'
        )
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    start = _bases(game, unit)
    targets = list(_bases(game, target).values())
    problems = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    engaged = 0
    # Round dense terrain, unless it can go through it.
    pather = pathing.for_unit(game, unit, start, charge.roll)
    for model in models:
        found = []
        if problem := pathing.too_far(pather, start[model.id], bases[model.id], charge.roll):
            found.append(problem)
        before = _nearest(start[model.id], targets)
        after = _nearest(bases[model.id], targets)
        if after <= ENGAGEMENT_RANGE + TOLERANCE:
            engaged += 1
        elif before <= ENGAGEMENT_RANGE + TOLERANCE:
            found.append(f"would leave Engagement Range of {target.faction_unit.name}")
        elif after >= before - TOLERANCE:
            found.append(f"must end closer to {target.faction_unit.name}")
        problems[model.id] = found + problems[model.id]
    result = deployment.summarise(models, problems)
    result.paths = pather.bends(start, bases)
    if not engaged:
        result.problems.append(
            f"No model ends within Engagement Range (2\") of {target.faction_unit.name}"
        )
    return result


def make_charge(
    game: Game, unit: Unit, target: Unit, placement: dict[int, tuple[float, float, float]]
) -> None:
    # Moves the unit into the charge, if it can.
    result = check_charge(game, unit, target, placement)
    if not result.valid:
        raise _bad_request("can't charge like that: " + "; ".join(result.problems))
    placed = deployment.positions(game)
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    charge = unit_charge(game, unit)
    charge.target_unit_id = target.id
    charge.completed = True
