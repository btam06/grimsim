from __future__ import annotations

from fastapi import HTTPException

from app.models import Unit
from app.engine.state import Game, GameCondemnation
from app.services.in_game import deployment
from app.services.in_game.deployment import TOLERANCE, gap
from app.services.list_building import enhancements as enhancement_rules

# Angelic Judgement (the Chorus of Condemnation detachment), in a game: its
# army's ADEPTA SORORITAS INFANTRY FLY units have Condemnatory Psalms - in
# their player's Shooting phase, each can select one visible enemy unit within
# 12": that unit is condemned, with +3" detection range (13.09: its hidden
# models can be seen from that much further away).
#
# The rules don't say how long a unit stays condemned: here, until the end of
# that Shooting phase - the phase the selecting unit's army shoots in.

DETACHMENT = "Chorus of Condemnation"
KEYWORDS = {"ADEPTA SORORITAS", "INFANTRY", "FLY"}
RANGE = 12.0
DETECTION_BONUS = 3.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _now(game: Game, record) -> bool:
    return (record.battle_round, record.turn_seat, record.phase) == (
        game.battle_round, game.turn_seat, game.phase
    )


def condemned(game: Game, unit: Unit) -> bool:
    return any(c.target_unit_id == unit.id and _now(game, c) for c in game.condemnations)


def detection_bonus(game: Game, unit: Unit) -> float:
    # What's added to the unit's models' detection range now.
    return DETECTION_BONUS if condemned(game, unit) else 0.0


def has_psalms(game: Game, unit: Unit) -> bool:
    # Whether the unit has Condemnatory Psalms: its army has the detachment,
    # and its models are ADEPTA SORORITAS INFANTRY FLY.
    army_list = deployment.owner(game, unit).army_list
    if not any(d.name == DETACHMENT for d in army_list.detachments):
        return False
    models = deployment.models_on_battlefield(game, unit)
    return bool(models) and all(
        KEYWORDS <= enhancement_rules.model_keywords(unit, m) for m in models
    )


def cant_reason(game: Game, unit: Unit) -> str | None:
    if not has_psalms(game, unit):
        return "it doesn't have Condemnatory Psalms"
    if game.phase != "shooting" or game.turn_seat != deployment.owner(game, unit).seat:
        return "it's used in its player's Shooting phase"
    if any(c.unit_id == unit.id and _now(game, c) for c in game.condemnations):
        return "it has already used it this phase"
    return None


def targets(game: Game, unit: Unit) -> list[Unit]:
    # The enemy units the unit could condemn: visible to one of its models
    # (hidden models only within their detection range), within 12".
    from app.services.in_game import shooting

    if cant_reason(game, unit) is not None:
        return []
    sight = shooting.Sight(game)
    own = list(shooting._bases(game, unit).values())
    found = []
    for enemy in shooting.enemy_units(game, unit):
        hidden = shooting.hidden_models(game, enemy, sight)
        detection = shooting.detection_range(game, enemy)
        for model_id, base in shooting._bases(game, enemy).items():
            if any(
                gap(b, base) <= RANGE + TOLERANCE
                and sight.sees(b, base)
                and (model_id not in hidden or gap(b, base) <= detection + TOLERANCE)
                for b in own
            ):
                found.append(enemy)
                break
    return found


def condemn(game: Game, unit: Unit, target: Unit) -> None:
    if (reason := cant_reason(game, unit)) is not None:
        raise _bad_request(f"{unit.label} can't use Condemnatory Psalms: {reason}")
    if target.id not in {t.id for t in targets(game, unit)}:
        raise _bad_request(f'{target.label} isn\'t a visible enemy unit within 12" of it')
    game.condemnations.append(
        GameCondemnation(
            seat=deployment.owner(game, unit).seat,
            unit_id=unit.id,
            target_unit_id=target.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            phase=game.phase,
        )
    )
