from __future__ import annotations

from app.engine.state import PHASES, Game, GamePhaseEnd
from app.services.in_game import deployment, reinforcements

# The end of a phase, for a program playing (see app/routers/agent.py) - one
# decision at a time, like the start of a phase (see phase_start.py
# window_seat). What's declared for the end of a phase - a Resurrection Orb
# (any phase), a unit going into Strategic Reserves at the end of the turn
# (Tunnelling Horrors, the Fight phase - the last) - is declared when the
# player whose turn it is ends the phase: theirs first, then their
# opponent's, each until they say they're done; then the phase ends. (In the
# browser, both declare them during the phase.)


def _now(game: Game, record: GamePhaseEnd) -> bool:
    return (record.battle_round, record.turn_seat, record.phase) == (
        game.battle_round, game.turn_seat, game.phase
    )


def has_options(game: Game, seat: int) -> bool:
    # Whether the player has anything to declare for the end of this phase.
    from app.seeds.factions.necrons import reanimation

    # (A unit declared already: none of its player's can be, this turn.)
    if any(deployment.owner(game, u).seat == seat for u in reanimation.resurrectable(game)):
        return True
    return game.phase == PHASES[-1] and any(
        not declared and deployment.owner(game, u).seat == seat
        for u, declared in reinforcements.turn_end_units(game)
    )


def opened(game: Game) -> bool:
    return any(_now(game, r) and r.seat is None for r in game.phase_end_windows)


def done(game: Game, seat: int) -> bool:
    return any(_now(game, r) and r.seat == seat for r in game.phase_end_windows)


def to_open(game: Game) -> bool:
    # Whether ending the phase opens the window: someone has something to
    # declare, and it hasn't been opened yet.
    if game.status != "in_progress" or game.phase not in PHASES or opened(game):
        return False
    return any(has_options(game, p.seat) for p in game.players)


def window_seat(game: Game) -> int | None:
    # Whose declarations for the end of the phase are to be made (or not)
    # now, once it's opened - None when they're all done.
    if game.status != "in_progress" or game.phase not in PHASES or not opened(game):
        return None
    turn = game.turn_seat
    other = next((p.seat for p in game.players if p.seat != turn), None)
    for seat in (turn, other):
        if seat is not None and not done(game, seat) and has_options(game, seat):
            return seat
    return None


def open(game: Game) -> None:
    game.phase_end_windows.append(
        GamePhaseEnd(battle_round=game.battle_round, turn_seat=game.turn_seat, phase=game.phase)
    )


def finish(game: Game, seat: int) -> None:
    # The player's done declaring them for the end of this phase.
    game.phase_end_windows.append(
        GamePhaseEnd(
            battle_round=game.battle_round, turn_seat=game.turn_seat, phase=game.phase, seat=seat
        )
    )
