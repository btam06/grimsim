from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.combat_rules import PhaseStartAbility, Rule
from app.engine.state import PHASES, Game, GamePhaseStartUse
from app.models import Unit
from app.services.in_game import deployment

# The start step of a phase, in a game: before anything else happens in it,
# each player who has something to use "at the start of the phase" uses it -
# or says they're done; the player whose turn it is first, then their
# opponent. Nothing else in the phase can happen till then. What's used:
#
# - abilities used at the start of an opponent's phase - e.g. Defend the
#   Divine Work: at the start of their opponent's Shooting or Fight phase,
#   once a battle, the player can give the unit a 4+ invulnerable save until
#   the end of the phase (see datasheet_abilities PHASE_START_ABILITIES);
# - activated abilities for the start of the phase (activations.py "when":
#   "start" - e.g. Harbinger of Despair, Gravitic Pulse);
# - abilities for the start of the Shooting or Fight phase with a target
#   (shooting_start.py - e.g. Data-spike).
#
# A player with nothing to use as the phase begins is done with it then (see
# enter) - and once anything's happened in the phase (a unit's moved, shot,
# charged or fought), the step's over.


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


def _available_for(game: Game, seat: int | None) -> list[Available]:
    # What the player could use now: their units on the battlefield with an
    # ability for this phase not used yet (this phase - or this battle, if
    # it's once a battle) - in their own turn, only those usable then.
    if game.status != "in_progress" or game.phase is None or seat is None:
        return []
    own_turn = seat == game.turn_seat
    config = _config()
    player = next(p for p in game.players if p.seat == seat)
    found = []
    for unit in deployment.deployable_units(player):
        models = deployment.models_on_battlefield(game, unit)
        for name in sorted({a.name for m in models for a in m.model.abilities} & set(config)):
            ability = config[name]
            if game.phase not in ability.phases or (own_turn and not ability.either_player):
                continue
            used = [
                r for r in game.phase_start_uses if r.unit_id == unit.id and r.ability == name
            ]
            if any(_now(game, r) for r in used) or (ability.once_per_battle and used):
                continue
            found.append(Available(unit, name, ability))
    return found


def available(game: Game) -> list[Available]:
    # What the player the game's waiting on could use now (see waiting).
    return _available_for(game, waiting(game))


def done(game: Game, seat: int) -> bool:
    return any(
        _now(game, r) and r.seat == seat and r.unit_id is None for r in game.phase_start_uses
    )


def has_options(game: Game, seat: int | None) -> bool:
    # Whether the player has anything to use at the start of this phase.
    from app.services.in_game import activations, shooting_start

    if seat is None:
        return False
    if _available_for(game, seat) or activations.step_options(game, seat, "start"):
        return True
    return game.phase in ("shooting", "fight") and any(
        deployment.owner(game, a.unit).seat == seat for a in shooting_start.available(game)
    )


def begun(game: Game) -> bool:
    # Whether anything's happened in the phase yet (its start step's over).
    from app.services.in_game import movement, shooting_start

    if game.phase in ("shooting", "fight"):
        return not shooting_start.is_start(game)
    if game.phase == "movement":
        return any(movement._this_phase(game, m) for m in game.unit_moves)
    if game.phase == "charge":
        return any(
            (c.battle_round, c.turn_seat) == (game.battle_round, game.turn_seat)
            for c in game.unit_charges
        )
    return False


def step_open(game: Game, seat: int) -> bool:
    # Whether the player can still use things at the start of this phase.
    return (
        game.status == "in_progress"
        and game.phase in START_PHASES
        and not done(game, seat)
        and not begun(game)
    )


def enter(game: Game) -> None:
    # The phase begins: a player with nothing to use at its start is done
    # with it.
    if game.status != "in_progress" or game.phase not in START_PHASES:
        return
    for player in game.players:
        if not done(game, player.seat) and not has_options(game, player.seat):
            _finish(game, player.seat)


def waiting(game: Game) -> int | None:
    # The player the game's waiting on to use (or not) their abilities for the
    # start of this phase, if any - the player whose turn it is first (only
    # abilities usable in their own turn - e.g. The Emperor's Grace), then
    # their opponent.
    if game.status != "in_progress" or game.phase not in START_PHASES or begun(game):
        return None
    for seat in (game.turn_seat, _opponent(game)):
        if seat is not None and not done(game, seat) and has_options(game, seat):
            return seat
    return None


def use(game: Game, seat: int, unit_id: int, ability: str) -> None:
    if waiting(game) != seat:
        raise _bad_request("that player can't use an ability for the start of this phase now")
    match = next(
        (a for a in _available_for(game, seat) if a.unit.id == unit_id and a.ability == ability),
        None,
    )
    if match is None:
        raise _bad_request(f"that unit can't use {ability} now")
    game.phase_start_uses.append(
        GamePhaseStartUse(
            seat=seat, battle_round=game.battle_round, turn_seat=game.turn_seat,
            phase=game.phase, unit_id=unit_id, ability=ability,
        )
    )


# The phases with a start step: all of them.
START_PHASES = PHASES


def window_seat(game: Game) -> int | None:
    # For a program playing (see app/routers/agent.py), one decision at a
    # time: the player the start step's waiting on.
    return waiting(game)


def finish(game: Game, seat: int) -> None:
    # The player's done with them for this phase.
    if game.status != "in_progress" or game.phase not in START_PHASES:
        raise _bad_request("there are no abilities for the start of this phase")
    if done(game, seat):
        raise _bad_request("that player's already done with them this phase")
    _finish(game, seat)


def _finish(game: Game, seat: int) -> None:
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
    # The same, for each of its models (for attacks against them) - only the
    # model with the ability, for one that's its own (e.g. The Emperor's
    # Grace).
    config = _config()
    found: dict[int, list[Rule]] = {}
    for r in game.phase_start_uses:
        if r.unit_id != unit.id or not _now(game, r) or r.ability not in config:
            continue
        ability = config[r.ability]
        for m in unit.unit_models:
            if ability.model_only and r.ability not in {a.name for a in m.model.abilities}:
                continue
            found.setdefault(m.id, []).extend(ability.rules)
    return found


def blocks(game: Game) -> str | None:
    # Why nothing else can happen in the phase yet, if the game's waiting.
    seat = waiting(game)
    if seat is None:
        return None
    return f"waiting for player {seat} to use (or not) their abilities for the start of the phase"
