from __future__ import annotations

from fastapi import HTTPException

from app.models import Game, GameModelPosition, Unit, UnitModel
from app.services.in_game import casualties, deployment
from app.services.in_game.deployment import BOARD, TOLERANCE, Base, Placement, gap

# Healing: a unit heals some wounds, one at a time - each restores a lost
# wound to a wounded model in it, or, if none is wounded, returns one of its
# destroyed models with 1 wound remaining (rules that heal like that - e.g.
# the Necrons' Reanimation Protocols, see
# app/seeds/factions/necrons/reanimation.py - use `heal`). A model returned
# this way doesn't take more of the wounds while there are destroyed models
# left to return: they spill over into the next.
#
# A returned model isn't on the battlefield until the player sets it up: in
# coherency with its unit, not overlapping other models or terrain features,
# and not within Engagement Range of an enemy model. Until every returned
# model is, the game stays at the end of the command phase (where models
# are returned now).

ENGAGEMENT_RANGE = 2.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def heal(game: Game, unit: Unit, wounds: int) -> tuple[int, int]:
    # The unit heals `wounds` wounds (see above): how many were restored to
    # wounded models, and how many destroyed models returned.
    # Wounds left over spill into the next destroyed model rather than
    # healing one just returned - those only heal once none are left to
    # return.
    records = casualties.damage(game)
    models = deployment.unit_models(unit)
    healed = returned = 0
    just_returned: set[int] = set()

    def wounded(m) -> bool:
        return m.id in records and not records[m.id].destroyed and records[m.id].wounds_lost > 0

    for _ in range(wounds):
        hurt = [m for m in models if wounded(m) and m.id not in just_returned]
        destroyed = [m for m in models if m.id in records and records[m.id].destroyed]
        if not hurt and not destroyed:
            hurt = [m for m in models if wounded(m)]
        if hurt:
            records[hurt[0].id].wounds_lost -= 1
            healed += 1
            continue
        if not destroyed:
            break
        record = records[destroyed[0].id]
        record.destroyed = False
        record.wounds_lost = destroyed[0].wounds - 1
        just_returned.add(destroyed[0].id)
        returned += 1
    return healed, returned


def to_place(game: Game, unit: Unit) -> list[UnitModel]:
    # The unit's returned models still to be set up: not destroyed, but off
    # the battlefield, while the rest of the unit is on it.
    placed = deployment.positions(game)
    if not deployment.is_deployed(unit, placed):
        return []
    records = casualties.damage(game)
    return [
        m
        for m in deployment.unit_models(unit)
        if m.id not in placed and m.id in records and not records[m.id].destroyed
    ]


def units_to_place(game: Game, seat: int) -> list[Unit]:
    player = next(p for p in game.players if p.seat == seat)
    return [u for u in deployment.deployable_units(player) if to_place(game, u)]


def placing(game: Game) -> bool:
    # Whether the game is waiting for returned models to be set up.
    return (
        game.status == "in_progress"
        and game.phase == "command"
        and bool(units_to_place(game, game.turn_seat))
    )


def _enemies(game: Game, unit: Unit) -> list[Base]:
    seat = deployment.owner(game, unit).seat
    return [b for p, _, b in deployment.placed_bases(game, unit) if p.seat != seat]


def suggested(game: Game, unit: Unit) -> dict[int, tuple[float, float, float]]:
    # Where to start the unit's returned models, for the player to arrange:
    # each at the nearest free spot to the middle of the rest of the unit.
    models = deployment.models_on_battlefield(game, unit)
    placed = deployment.positions(game)
    cx = sum(placed[m.id].x for m in models) / len(models)
    cy = sum(placed[m.id].y for m in models) / len(models)
    taken = [b for _, _, b in deployment.placed_bases(game, unit)] + [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in models
    ]
    enemies = _enemies(game, unit)
    features = deployment._features(game)

    def free(base: Base, in_zone: bool) -> bool:
        return (
            deployment.wholly_within(base, BOARD)
            and not any(deployment.overlaps(base, other) for other in taken)
            and deployment._feature_overlapped(base, features) is None
            and not any(gap(base, e) <= ENGAGEMENT_RANGE + TOLERANCE for e in enemies)
        )

    result = {}
    for model in to_place(game, unit):
        spot = deployment._nearest_free(model, (cx, cy), free) or (cx, cy)
        taken.append(deployment.base_at(model, *spot))
        result[model.id] = (round(spot[0], 3), round(spot[1], 3), 0.0)
    return result


def check_turn(game: Game, unit: Unit) -> None:
    # That the unit has returned models its owner can set up now.
    if not placing(game):
        raise _bad_request("there are no returned models to set up")
    if deployment.owner(game, unit).seat != game.turn_seat:
        raise _bad_request("only the player whose turn it is sets up their returned models")
    if not to_place(game, unit):
        raise _bad_request("that unit has no returned models to set up")


def check_return(
    game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]
) -> Placement:
    # Whether the unit's returned models could be set up at `placement` ((x, y,
    # rotation) by unit model id - each of them, and only those).
    returning = to_place(game, unit)
    if set(placement) != {m.id for m in returning}:
        raise _bad_request("place every returned model in the unit (and only those)")
    placed = deployment.positions(game)
    models = deployment.models_on_battlefield(game, unit) + returning
    bases = {
        m.id: (
            deployment.base_at(m, *placement[m.id])
            if m.id in placement
            else deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        )
        for m in models
    }
    others = deployment.placed_bases(game, unit)
    problems = deployment.physical_problems(game, models, bases, others)
    enemies = _enemies(game, unit)
    # Only the returned models' problems: the rest of the unit stays put.
    found = {}
    for model in returning:
        near = any(gap(bases[model.id], e) <= ENGAGEMENT_RANGE + TOLERANCE for e in enemies)
        found[model.id] = (
            ["is within Engagement Range of an enemy model"] if near else []
        ) + problems[model.id]
    return deployment.summarise(returning, found)


def place(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # Sets up the unit's returned models as placed, if they can be.
    check_turn(game, unit)
    result = check_return(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't set them up there: " + "; ".join(result.problems))
    for unit_model_id, (x, y, rotation) in placement.items():
        game.model_positions.append(
            GameModelPosition(unit_model_id=unit_model_id, x=x, y=y, rotation=rotation)
        )
