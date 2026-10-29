from __future__ import annotations

import random

from fastapi import HTTPException

from app.models import Game, GameFirstTurnRoll

# Who goes first: once both armies are set up (see
# app/services/in_game/deployment.py), the players roll off - each rolls one
# D6, and the highest goes first; if they tie, both roll again. Then come
# redeploys (no rule asks for one yet), pre-battle abilities - Scouts (see
# app/services/in_game/scouts.py) - and the battle. A
# game made with who goes first already decided skips the roll.

SEATS = (1, 2)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def waiting(game: Game) -> bool:
    # Whether the game is waiting for the roll-off.
    from app.services.in_game import deployment

    return (
        game.status == "deployment"
        and game.first_seat is None
        and deployment.formations_declared(game)
        and deployment.deploying_seat(game) is None
    )


def roll(game: Game) -> int:
    # Rolls off (re-rolling ties) - every roll recorded - and the highest goes
    # first. The seat that does.
    if game.first_seat is not None:
        raise _bad_request("who goes first has already been decided")
    attempt = 0
    while True:
        attempt += 1
        rolls = {seat: random.randint(1, 6) for seat in SEATS}
        for seat, value in rolls.items():
            game.first_turn_rolls.append(
                GameFirstTurnRoll(attempt=attempt, seat=seat, roll=value)
            )
        if rolls[1] != rolls[2]:
            game.first_seat = max(rolls, key=rolls.get)
            return game.first_seat
