from __future__ import annotations

from fastapi import HTTPException

from app.engine.state import Game, GamePlayer, GameScentingFear
from app.models import Unit
from app.services.in_game import deployment
from app.services.in_game.deployment import TOLERANCE, gap
from app.services.list_building import enhancements as enhancement_rules

# Scenting Fear (the Hunting Warpack detachment), in a game: once per battle
# round, in their Shooting phase, the player can select one visible enemy
# unit within 12" of a friendly WAR DOG unit - that enemy unit has +6"
# detection range (13.09: its hidden models can be seen from that much
# further away).
#
# Visible to, and within 12" of, one of the WAR DOG unit's models. The rules
# don't say how long it lasts: here, as Condemnatory Psalms, until the end of
# that Shooting phase.

RULE = "Scenting Fear"
KEYWORD = "WAR DOG"
RANGE = 12.0
DETECTION_BONUS = 6.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _now(game: Game, record) -> bool:
    return (record.battle_round, record.turn_seat, record.phase) == (
        game.battle_round, game.turn_seat, game.phase
    )


def has_rule(player: GamePlayer) -> bool:
    return any(r.name == RULE for d in player.army_list.detachments for r in d.rules)


def detection_bonus(game: Game, unit: Unit) -> float:
    # What's added to the unit's models' detection range now.
    if any(s.target_unit_id == unit.id and _now(game, s) for s in game.scented):
        return DETECTION_BONUS
    return 0.0


def cant_reason(game: Game, player: GamePlayer) -> str | None:
    # Why the player can't use Scenting Fear now (None: they can).
    if not has_rule(player):
        return "their army doesn't have Scenting Fear"
    if game.status != "in_progress" or game.phase != "shooting" or game.turn_seat != player.seat:
        return "it's used in their Shooting phase"
    if any(s.seat == player.seat and s.battle_round == game.battle_round for s in game.scented):
        return "it has already been used this battle round"
    return None


def _war_dogs(game: Game, player: GamePlayer) -> list[Unit]:
    return [
        u
        for u in deployment.deployable_units(player)
        if any(
            KEYWORD in enhancement_rules.model_keywords(u, m)
            for m in deployment.models_on_battlefield(game, u)
        )
    ]


def targets(game: Game, player: GamePlayer) -> list[Unit]:
    # The enemy units the player could select: visible to, and within 12" of,
    # one of their WAR DOG units (hidden models only within their detection
    # range).
    from app.services.in_game import shooting

    if cant_reason(game, player) is not None:
        return []
    dogs = _war_dogs(game, player)
    if not dogs:
        return []
    sight = shooting.Sight(game)
    own = [b for dog in dogs for b in shooting._bases(game, dog).values()]
    found = []
    for enemy in shooting.enemy_units(game, dogs[0]):
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


def select(game: Game, player: GamePlayer, target: Unit) -> None:
    if (reason := cant_reason(game, player)) is not None:
        raise _bad_request(f"can't use {RULE}: {reason}")
    if target.id not in {t.id for t in targets(game, player)}:
        raise _bad_request(
            f'{target.label} isn\'t a visible enemy unit within 12" of one of their WAR DOG units'
        )
    game.scented.append(
        GameScentingFear(
            seat=player.seat,
            target_unit_id=target.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            phase=game.phase,
        )
    )


def scented(game: Game) -> list[GameScentingFear]:
    # The units selected with it, still with their bonus now.
    return [s for s in game.scented if _now(game, s)]
