from __future__ import annotations

from fastapi import HTTPException

from app.models import Game, Unit
from app.services import weapon_profiles
from app.services.in_game import deployment, movement, reinforcements
from app.services.in_game import shooting
from app.services.in_game.deployment import TOLERANCE
from app.services.in_game.shooting import TargetReach

# Fire Overwatch, at the end of the movement phase (see
# app/services/in_game/reinforcements.py, which marks it: once the player
# whose turn it is has finished moving). Their opponent can use the
# stratagem to have one of their units shoot an enemy unit it can see within
# 24" - snap shooting: every Hit roll needs an unmodified 6, can't be
# re-rolled and triggers nothing (no Sustained or Lethal Hits), though
# Torrent weapons still hit automatically and Rapid Fire still adds attacks
# (see app/services/combat.py).
#
# The shooting unit is one of theirs on the battlefield, with ranged
# weapons, not within Engagement Range of an enemy unit. Each of its models
# fires the weapons it can at the target as when shooting (a visible target
# model in range - see app/services/in_game/shooting.py).

OVERWATCH = "Fire Overwatch"
OVERWATCH_RANGE = 24.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def overwatch_seat(game: Game) -> int | None:
    # Who can Fire Overwatch now: at the end of the movement phase, the
    # opponent of the player whose turn it is.
    if game.status != "in_progress" or game.phase != "movement":
        return None
    if not reinforcements.movement_ended(game):
        return None
    return 2 if game.turn_seat == 1 else 1


def overwatch_units(game: Game, seat: int) -> list[Unit]:
    # The player's units on the battlefield.
    player = next(p for p in game.players if p.seat == seat)
    placed = deployment.positions(game)
    return [u for u in deployment.deployable_units(player) if deployment.is_deployed(u, placed)]


def cant_overwatch_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't Fire Overwatch now, or None if it can.
    seat = overwatch_seat(game)
    if seat is None:
        return "Fire Overwatch is used at the end of the opponent's movement phase"
    if deployment.owner(game, unit).seat != seat:
        return "only the opponent of the player whose turn it is can Fire Overwatch"
    return _cant_shoot(game, unit)


def _cant_shoot(game: Game, unit: Unit) -> str | None:
    # Why the unit couldn't shoot (whenever it is), or None if it could.
    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if movement.in_engagement_range(game, unit):
        return "it's within Engagement Range of an enemy unit"
    if not any(shooting.ranged_weapons(m) for m in deployment.models_on_battlefield(game, unit)):
        return "it has no ranged weapons"
    return None


def within_range(result: TargetReach) -> bool:
    # Whether the target is visible within 24".
    return (
        result.visible
        and result.distance is not None
        and result.distance <= OVERWATCH_RANGE + TOLERANCE
    )


def targets(game: Game, unit: Unit) -> list[TargetReach]:
    # Each enemy unit on the battlefield, and what the unit can do to it.
    return [shooting.reach(game, unit, t) for t in shooting.enemy_units(game, unit)]


def can_overwatch(game: Game, seat: int) -> bool:
    # Whether any of the player's units could Fire Overwatch at something:
    # an enemy unit visible within 24" that one of its weapons reaches.
    for unit in overwatch_units(game, seat):
        if _cant_shoot(game, unit) is not None:
            continue
        if any(within_range(r) and any(w.in_range for w in r.weapons) for r in targets(game, unit)):
            return True
    return False


def check_overwatch(game: Game, unit: Unit, target: Unit, weapon_ids: set) -> TargetReach:
    # That the unit can Fire Overwatch at the target with those weapons (each
    # in range of it for at least one model); what it can do to it.
    if (reason := cant_overwatch_reason(game, unit)) is not None:
        raise _bad_request(f"it can't Fire Overwatch: {reason}")
    if target.id not in {u.id for u in shooting.enemy_units(game, unit)}:
        raise _bad_request("the target must be an enemy unit on the battlefield")
    result = shooting.reach(game, unit, target)
    if not result.visible:
        raise _bad_request("none of its models can see the target")
    if not within_range(result):
        raise _bad_request('the target must be within 24"')
    if not weapon_ids:
        raise _bad_request("choose at least one weapon to shoot with")
    if (conflict := weapon_profiles.unit_conflict(unit, weapon_ids)) is not None:
        raise _bad_request(conflict)
    usable = {w.id for w in result.weapons if w.in_range}
    if not weapon_ids <= usable:
        raise _bad_request("one or more of those weapons can't reach the target")
    return result
