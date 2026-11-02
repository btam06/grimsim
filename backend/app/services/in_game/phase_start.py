from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.combat_rules import PhaseStartAbility, Rule
from app.engine.state import Game, GamePhaseStartUse
from app.models import Unit
from app.services.in_game import deployment

# Abilities used at the start of an opponent's phase, in a game - e.g. Defend
# the Divine Work: at the start of their opponent's Shooting or Fight phase,
# once a battle, the player can give the unit a 4+ invulnerable save until
# the end of the phase (see datasheet_abilities PHASE_START_ABILITIES). The
# game waits for them to use them - or say they're done - before anything
# happens in the phase.


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


@dataclass
class Available:
    # An ability the player could use now: its unit, and its config.
    unit: Unit
    ability: str
    config: PhaseStartAbility


def _config() -> dict[str, PhaseStartAbility]:
    from app.seeds import datasheet_abilities

    return datasheet_abilities.PHASE_START_ABILITIES


def _opponent(game: Game) -> int | None:
    return next((p.seat for p in game.players if p.seat != game.turn_seat), None)


def _now(game: Game, record: GamePhaseStartUse) -> bool:
    return (record.battle_round, record.turn_seat, record.phase) == (
        game.battle_round, game.turn_seat, game.phase
    )


def available(game: Game) -> list[Available]:
    # What the player whose turn it isn't could use now: their units on the
    # battlefield with an ability for this phase not used yet (this phase -
    # or this battle, if it's once a battle).
    if game.status != "in_progress" or game.phase is None:
        return []
    seat = _opponent(game)
    if seat is None:
        return []
    config = _config()
    player = next(p for p in game.players if p.seat == seat)
    found = []
    for unit in deployment.deployable_units(player):
        models = deployment.models_on_battlefield(game, unit)
        for name in sorted({a.name for m in models for a in m.model.abilities} & set(config)):
            ability = config[name]
            if game.phase not in ability.phases:
                continue
            used = [
                r for r in game.phase_start_uses if r.unit_id == unit.id and r.ability == name
            ]
            if any(_now(game, r) for r in used) or (ability.once_per_battle and used):
                continue
            found.append(Available(unit, name, ability))
    return found


def done(game: Game, seat: int) -> bool:
    return any(
        _now(game, r) and r.seat == seat and r.unit_id is None for r in game.phase_start_uses
    )


def waiting(game: Game) -> int | None:
    # The player the game's waiting on to use (or not) their abilities for the
    # start of this phase, if any.
    seat = _opponent(game)
    if seat is None or done(game, seat) or not available(game):
        return None
    return seat


def use(game: Game, seat: int, unit_id: int, ability: str) -> None:
    if waiting(game) != seat:
        raise _bad_request("that player can't use an ability for the start of this phase now")
    match = next(
        (a for a in available(game) if a.unit.id == unit_id and a.ability == ability), None
    )
    if match is None:
        raise _bad_request(f"that unit can't use {ability} now")
    game.phase_start_uses.append(
        GamePhaseStartUse(
            seat=seat, battle_round=game.battle_round, turn_seat=game.turn_seat,
            phase=game.phase, unit_id=unit_id, ability=ability,
        )
    )


# The phases with a start where abilities are used (see also
# app/services/in_game/shooting_start.py).
START_PHASES = ("shooting", "fight")


def window_seat(game: Game) -> int | None:
    # For a program playing (see app/routers/agent.py), one decision at a
    # time: whose abilities for the start of this phase are to be used (or
    # not) now - the player whose turn it is's first, then their opponent's,
    # each until they say they're done. (In the browser, both can act at once.)
    from app.services.in_game import shooting_start

    if game.status != "in_progress" or game.phase not in START_PHASES:
        return None
    if not shooting_start.is_start(game):
        return None
    owners = {deployment.owner(game, a.unit).seat for a in shooting_start.available(game)}
    turn, other = game.turn_seat, _opponent(game)
    if turn in owners and not done(game, turn):
        return turn
    if other is not None and not done(game, other) and (other in owners or available(game)):
        return other
    return None


def finish(game: Game, seat: int) -> None:
    # The player's done with them for this phase.
    if game.status != "in_progress" or game.phase not in START_PHASES:
        raise _bad_request("there are no abilities for the start of this phase")
    if done(game, seat):
        raise _bad_request("that player's already done with them this phase")
    game.phase_start_uses.append(
        GamePhaseStartUse(
            seat=seat, battle_round=game.battle_round, turn_seat=game.turn_seat,
            phase=game.phase,
        )
    )


def active_rules(game: Game, unit: Unit) -> list[Rule]:
    # The rules its abilities used this phase give the unit now.
    config = _config()
    return [
        rule
        for r in game.phase_start_uses
        if r.unit_id == unit.id and _now(game, r) and r.ability in config
        for rule in config[r.ability].rules
    ]


def model_rules(game: Game, unit: Unit) -> dict[int, list[Rule]]:
    # The same, for each of its models (for attacks against them).
    rules = active_rules(game, unit)
    return {m.id: list(rules) for m in unit.unit_models} if rules else {}


def blocks(game: Game) -> str | None:
    # Why nothing else can happen in the phase yet, if the game's waiting.
    seat = waiting(game)
    if seat is None:
        return None
    return f"waiting for player {seat} to use (or not) their abilities for the start of the phase"
