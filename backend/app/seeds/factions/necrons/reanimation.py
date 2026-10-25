from __future__ import annotations

import random

from app.models import Game, GameReanimation, Unit
from app.services.in_game import deployment, heal

# The Necrons' Reanimation Protocols, in a game. At the end of a player's
# command phase, each of their units on the battlefield with the ability
# heals D3 wounds (see app/services/in_game/heal.py: restoring lost wounds,
# or returning destroyed models for the player to set up).

REANIMATION_PROTOCOLS = "Reanimation Protocols"
HEAL_DICE = 3


def _this_turn(game: Game, record) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def has_reanimation_protocols(unit: Unit) -> bool:
    return any(
        a.name == REANIMATION_PROTOCOLS for m in unit.unit_models for a in m.model.faction_abilities
    )


def reanimating_units(game: Game, seat: int) -> list[Unit]:
    # The player's units on the battlefield with Reanimation Protocols.
    player = next(p for p in game.players if p.seat == seat)
    placed = deployment.positions(game)
    return [
        u
        for u in deployment.deployable_units(player)
        if deployment.is_deployed(u, placed) and has_reanimation_protocols(u)
    ]


def reanimations(game: Game) -> list[GameReanimation]:
    # The Reanimation Protocols activated at the end of this turn's command
    # phase.
    return [r for r in game.reanimations if _this_turn(game, r)]


def reanimate(game: Game) -> None:
    # The end of the command phase: each of the player whose turn it is's
    # units with Reanimation Protocols heals D3 wounds (once a turn).
    if reanimations(game):
        return
    for unit in reanimating_units(game, game.turn_seat):
        roll = random.randint(1, HEAL_DICE)
        healed, returned = heal.heal(game, unit, roll)
        game.reanimations.append(
            GameReanimation(
                unit_id=unit.id,
                battle_round=game.battle_round,
                turn_seat=game.turn_seat,
                roll=roll,
                healed=healed,
                returned=returned,
            )
        )
