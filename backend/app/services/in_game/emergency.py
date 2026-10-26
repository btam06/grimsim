from __future__ import annotations

import math
import random

from fastapi import HTTPException

from app.models import (
    Game,
    GameEmergencyDisembark,
    GameEmergencyRoll,
    GameModelPosition,
    GameTransportWreck,
    Unit,
    UnitModel,
)
from app.services.in_game import casualties, deployment
from app.services.in_game.deployment import BOARD, TOLERANCE, Base, Placement, gap

# Emergency disembarking: when a transport is destroyed with units embarked
# in it, each of them must disembark - set up within 3" of where the
# transport was (its wreck), not overlapping it, and touching it if they can.
# Models that can't be set up within 3" (the player leaves them out) are
# destroyed. Each model set up then takes a hazard roll. Once every unit
# that was inside is out, the transport explodes if it has Deadly Demise: one
# D6 for each of its models with it, and on a 6, each unit within 6" of it
# suffers its mortal wounds (1, D3 or D6 - rolled for each unit).
#
# Until every unit is out, the game waits (it can't advance) - the
# transport's owner sets them up, whoever's turn it is.

EMERGENCY_RANGE = 3.0
DEADLY_DEMISE_RANGE = 6.0
# How close a model has to be to the wreck to count as touching it.
TOUCHING = 0.1
DEADLY_DEMISE = "Deadly Demise "


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


# --- the transport being destroyed (see casualties._lose) ---


def carrying(game: Game, transport: Unit) -> list[int]:
    # The ids of the units embarked in the transport.
    return [
        f.unit_id
        for f in game.battle_formations
        if f.place == "embarked" and f.transport_unit_id == transport.id
    ]


def record_wreck(
    game: Game, transport: Unit, unit_model: UnitModel, position: GameModelPosition
) -> None:
    # One of a transport's models is being destroyed: if units are embarked
    # in it, where it was - and once it's the transport's last model, each of
    # those units must emergency disembark.
    inside = carrying(game, transport)
    if not inside:
        return
    game.transport_wrecks.append(
        GameTransportWreck(
            transport_unit_id=transport.id,
            unit_model_id=unit_model.id,
            x=position.x,
            y=position.y,
            rotation=position.rotation,
        )
    )
    placed = deployment.positions(game)
    if any(m.id in placed and m.id != unit_model.id for m in transport.unit_models):
        return
    already = {e.unit_id for e in game.emergency_disembarks}
    for unit_id in inside:
        if unit_id not in already:
            game.emergency_disembarks.append(
                GameEmergencyDisembark(transport_unit_id=transport.id, unit_id=unit_id)
            )


# --- what's waiting ---


def pending(game: Game) -> list[GameEmergencyDisembark]:
    # The units still to emergency disembark.
    return [e for e in game.emergency_disembarks if not e.placed]


def waiting(game: Game) -> bool:
    return bool(pending(game))


def _record(game: Game, unit: Unit) -> GameEmergencyDisembark:
    record = next((e for e in pending(game) if e.unit_id == unit.id), None)
    if record is None:
        raise _bad_request("that unit doesn't have to emergency disembark")
    return record


def wreck_bases(game: Game, transport_unit_id: int) -> list[Base]:
    models = {
        m.id: m for p in game.players for u in p.army_list.units for m in u.unit_models
    }
    return [
        deployment.base_at(models[w.unit_model_id], w.x, w.y, w.rotation)
        for w in game.transport_wrecks
        if w.transport_unit_id == transport_unit_id
    ]


def surviving_models(game: Game, unit: Unit) -> list[UnitModel]:
    destroyed = {d.unit_model_id for d in game.model_damage if d.destroyed}
    return [m for m in deployment.unit_models(unit) if m.id not in destroyed]


def _touching(base: Base, wrecks: list[Base]) -> bool:
    return any(gap(base, w) <= TOUCHING for w in wrecks)


def _touching_spots(model: UnitModel, wrecks: list[Base], free) -> list[tuple[float, float]]:
    # Spots round the wreck where the model would touch it and fits.
    spots = []
    radius = max(deployment.base_at(model, 0, 0).semi_axes)
    for wreck in wrecks:
        reach = max(wreck.semi_axes) + radius
        for i in range(48):
            angle = 2 * math.pi * i / 48
            dx, dy = math.cos(angle), math.sin(angle)

            def at(distance: float) -> Base:
                return deployment.base_at(model, wreck.x + dx * distance, wreck.y + dy * distance)

            # Bisect for where it just touches the wreck, then a hair out
            # (so rounding its position can't make them overlap).
            inside, outside = 0.0, reach + 1
            for _ in range(30):
                middle = (inside + outside) / 2
                if deployment.overlaps(at(middle), wreck):
                    inside = middle
                else:
                    outside = middle
            base = at(outside + 0.01)
            if _touching(base, [wreck]) and free(base):
                spots.append((base.x, base.y))
    return spots


def _free_check(game: Game, unit: Unit, taken: list[Base], wrecks: list[Base]):
    features = deployment._features(game)
    others = [b for _, _, b in deployment.placed_bases(game, unit)]

    def free(base: Base) -> bool:
        return (
            deployment.wholly_within(base, BOARD)
            and not any(deployment.overlaps(base, o) for o in others + taken + wrecks)
            and deployment._feature_overlapped(base, features) is None
        )

    return free


def suggested(game: Game, unit: Unit) -> dict[int, tuple[float, float, float]]:
    # Where to start the unit's models, for the player to arrange: touching
    # the wreck where there's room, then as near it as they fit within 3" -
    # any that don't fit are left out (they'd be destroyed).
    record = _record(game, unit)
    wrecks = wreck_bases(game, record.transport_unit_id)
    taken: list[Base] = []
    result = {}
    for model in surviving_models(game, unit):
        free = _free_check(game, unit, taken, wrecks)
        spots = _touching_spots(model, wrecks, free)
        spot = spots[0] if spots else None
        if spot is None:
            cx = sum(w.x for w in wrecks) / len(wrecks)
            cy = sum(w.y for w in wrecks) / len(wrecks)
            found = deployment._nearest_free(model, (cx, cy), lambda b, _: free(b))
            if found and any(
                gap(deployment.base_at(model, *found), w) <= EMERGENCY_RANGE + TOLERANCE
                for w in wrecks
            ):
                spot = found
        if spot is None:
            continue
        taken.append(deployment.base_at(model, *spot))
        result[model.id] = (round(spot[0], 3), round(spot[1], 3), 0.0)
    return result


def check(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> Placement:
    # Whether the unit could emergency disembark with these of its models
    # where placed (any it leaves out are destroyed).
    record = _record(game, unit)
    survivors = surviving_models(game, unit)
    if not set(placement) <= {m.id for m in survivors}:
        raise _bad_request("place only the unit's models that aren't destroyed")
    models = [m for m in survivors if m.id in placement]
    if not models:
        return Placement(problems=[], models={})
    models, bases = deployment.unit_bases(unit, placement, models)
    wrecks = wreck_bases(game, record.transport_unit_id)
    others = deployment.placed_bases(game, unit)
    problems = deployment.physical_problems(game, models, bases, others)
    for model in models:
        base = bases[model.id]
        found = []
        if not any(gap(base, w) <= EMERGENCY_RANGE + TOLERANCE for w in wrecks):
            found.append('isn\'t within 3" of its transport')
        if any(deployment.overlaps(base, w) for w in wrecks):
            found.append("overlaps its transport")
        elif not _touching(base, wrecks):
            # Touching it if it can: is there a free spot touching it?
            rest = [bases[o.id] for o in models if o.id != model.id]
            if _touching_spots(model, wrecks, _free_check(game, unit, rest, wrecks)):
                found.append("could be touching its transport")
        problems[model.id] = found + problems[model.id]
    return deployment.summarise(models, problems)


def _hazard(game: Game, record: GameEmergencyDisembark, unit: Unit, unit_model: UnitModel) -> None:
    # A set-up model's hazard roll: on a failure it suffers mortal wounds by
    # its keywords (see app/services/combat.py), each negated by its Feel No
    # Pain against mortal wounds on a success.
    from app.services.combat import hazard_failed, hazard_wounds
    from app.services.list_building.enhancements import model_keywords

    roll = random.randint(1, 6)
    wounds = 0
    if hazard_failed(roll):
        for _ in range(hazard_wounds(model_keywords(unit, unit_model))):
            if not casualties.resists(unit_model):
                wounds += 1
    game.emergency_rolls.append(
        GameEmergencyRoll(
            transport_unit_id=record.transport_unit_id,
            unit_model_id=unit_model.id,
            kind="hazard",
            roll=roll,
            wounds=wounds,
        )
    )
    if wounds:
        casualties._lose(game, unit_model, wounds)


def _dice(amount: str) -> int:
    if amount == "D3":
        return random.randint(1, 3)
    if amount == "D6":
        return random.randint(1, 6)
    return int(amount)


def _explode(game: Game, transport_unit_id: int) -> None:
    # Every unit that was inside is out: each of the transport's models with
    # Deadly Demise rolls a D6 - on a 6, each unit within 6" suffers its
    # mortal wounds.
    transport = deployment.find_unit(game, transport_unit_id)
    wrecks = {
        w.unit_model_id: w for w in game.transport_wrecks if w.transport_unit_id == transport.id
    }
    placed = deployment.positions(game)
    for unit_model in transport.unit_models:
        amount = next(
            (
                a.name[len(DEADLY_DEMISE):]
                for a in unit_model.model.abilities
                if a.name.startswith(DEADLY_DEMISE)
            ),
            None,
        )
        wreck = wrecks.get(unit_model.id)
        if amount is None or wreck is None:
            continue
        roll = random.randint(1, 6)
        game.emergency_rolls.append(
            GameEmergencyRoll(transport_unit_id=transport.id, kind="deadly_demise", roll=roll)
        )
        if roll != 6:
            continue
        # Each unit within 6" suffers its own roll's mortal wounds.
        here = deployment.base_at(unit_model, wreck.x, wreck.y, wreck.rotation)
        for player in game.players:
            for unit in deployment.deployable_units(player):
                models = [m for m in unit.unit_models if m.id in placed]
                bases = [
                    deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
                    for m in models
                ]
                if not any(gap(here, b) <= DEADLY_DEMISE_RANGE + TOLERANCE for b in bases):
                    continue
                wounds = _dice(amount)
                game.emergency_rolls.append(
                    GameEmergencyRoll(
                        transport_unit_id=transport.id,
                        unit_model_id=models[0].id,
                        kind="deadly_demise_wounds",
                        roll=wounds,
                        wounds=wounds,
                    )
                )
                casualties.mortal_wounds(game, unit, wounds)
                placed = deployment.positions(game)


def disembark(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # The unit emergency disembarks as placed, if it can: the models left out
    # are destroyed, those set up take hazard rolls - and if it was the last
    # unit inside, the transport explodes (if it has Deadly Demise).
    record = _record(game, unit)
    result = check(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't set it up there: " + "; ".join(result.problems))
    survivors = surviving_models(game, unit)
    left = casualties.damage(game)
    for unit_model in survivors:
        if unit_model.id in placement:
            x, y, rotation = placement[unit_model.id]
            game.model_positions.append(
                GameModelPosition(unit_model_id=unit_model.id, x=x, y=y, rotation=rotation)
            )
    for unit_model in survivors:
        if unit_model.id not in placement:
            lost = left[unit_model.id].wounds_lost if unit_model.id in left else 0
            casualties._lose(game, unit_model, unit_model.wounds - lost)
    formation = deployment.battle_formation(game, unit)
    if formation is not None:
        game.battle_formations.remove(formation)
    record.placed = True
    for unit_model in survivors:
        if unit_model.id in placement:
            _hazard(game, record, unit, unit_model)
    if not any(e.transport_unit_id == record.transport_unit_id for e in pending(game)):
        _explode(game, record.transport_unit_id)


def rolls(game: Game, transport_unit_id: int) -> list[GameEmergencyRoll]:
    return [r for r in game.emergency_rolls if r.transport_unit_id == transport_unit_id]
