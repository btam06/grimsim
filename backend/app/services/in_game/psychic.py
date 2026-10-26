from __future__ import annotations

import random

from fastapi import HTTPException

from app.models import Game, GamePsychicUse, Unit
from app.seeds import datasheet_abilities as datasheet_ability_seeds
from app.services.in_game import battle_shock, deployment

# Psychic abilities (e.g. the Space Marines' Librarius): a PSYKER unit has a
# psyker level (from an ability - datasheet_abilities PSYKER_LEVELS, e.g.
# Librarian: 1), and each psychic ability a psychic level (PSYCHIC_ABILITIES).
# In a battle round, a unit can use psychic abilities whose total level is
# at most its psyker level - while it isn't Battle-shocked. Using one is a
# psychic roll (one D6): on a 1, the unit is Battle-shocked; the ability
# takes effect either way.
#
# - Soul Sight: in its player's Shooting phase, pick one visible enemy unit -
#   ranged attacks that target it ignore cover until the end of the phase.
# - Shrouding: when an enemy unit targets it (the player uses it as an enemy
#   is about to attack it) - attacks that target it are -1 to hit until the
#   end of the phase (its "Shrouded" rule option).

SOUL_SIGHT = "Soul Sight"
SHROUDING = "Shrouding"
# When each can be used: "own_shooting" (its player's Shooting phase) or
# "targeted" (any phase an enemy unit could attack it).
WHEN = {SOUL_SIGHT: "own_shooting", SHROUDING: "targeted"}
# Phases an enemy unit can attack in (Fire Overwatch, in the movement phase).
ATTACK_PHASES = ("movement", "shooting", "fight")
# The rule option a psychic ability gives its unit, while it lasts.
OPTIONS = {SHROUDING: "Shrouded"}


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _names(unit: Unit) -> set[str]:
    return {a.name for m in unit.unit_models for a in m.model.abilities}


def psyker_level(unit: Unit) -> int:
    levels = datasheet_ability_seeds.PSYKER_LEVELS
    return max((levels[n] for n in _names(unit) if n in levels), default=0)


def abilities(unit: Unit) -> dict[str, int]:
    # The unit's psychic abilities and their levels.
    levels = datasheet_ability_seeds.PSYCHIC_ABILITIES
    return {n: levels[n] for n in sorted(_names(unit)) if n in levels}


def psykers(game: Game) -> list[Unit]:
    # Every unit on the battlefield with a psyker level and psychic abilities.
    placed = deployment.positions(game)
    return [
        u
        for p in game.players
        for u in deployment.deployable_units(p)
        if deployment.is_deployed(u, placed) and psyker_level(u) and abilities(u)
    ]


def uses_this_round(game: Game, unit: Unit) -> list[GamePsychicUse]:
    return [
        u for u in game.psychic_uses if u.unit_id == unit.id and u.battle_round == game.battle_round
    ]


def _this_phase(game: Game, use: GamePsychicUse) -> bool:
    return (
        use.battle_round == game.battle_round
        and use.turn_seat == game.turn_seat
        and use.phase == game.phase
    )


def unavailable_reason(game: Game, unit: Unit, ability: str) -> str | None:
    # Why the unit can't use the psychic ability now, or None if it can.
    if game.status != "in_progress":
        return "the game isn't in progress"
    level = abilities(unit).get(ability)
    if level is None:
        return f"it has no {ability}"
    if battle_shock.is_battle_shocked(game, unit):
        return "it's Battle-shocked"
    used = sum(abilities(unit).get(u.ability, 0) for u in uses_this_round(game, unit))
    if used + level > psyker_level(unit):
        return f"it's used psychic abilities up to its psyker level ({psyker_level(unit)}) this round"
    seat = deployment.owner(game, unit).seat
    when = WHEN.get(ability)
    if when == "own_shooting" and (game.phase != "shooting" or game.turn_seat != seat):
        return "it's used in its player's Shooting phase"
    if when == "targeted" and game.phase not in ATTACK_PHASES:
        return "it's used when an enemy unit targets it"
    return None


def soul_sight_targets(game: Game, unit: Unit) -> list[Unit]:
    # The enemy units it can see.
    from app.services.in_game import shooting

    return [t for t in shooting.enemy_units(game, unit) if shooting.reach(game, unit, t).visible]


def use(game: Game, unit: Unit, ability: str, target: Unit | None = None) -> GamePsychicUse:
    # The unit uses the psychic ability: its psychic roll (a 1 Battle-shocks
    # it), and - for Soul Sight - the visible enemy unit it picks.
    if (reason := unavailable_reason(game, unit, ability)) is not None:
        raise _bad_request(f"it can't use {ability}: {reason}")
    if ability == SOUL_SIGHT:
        if target is None or target.id not in {t.id for t in soul_sight_targets(game, unit)}:
            raise _bad_request("Soul Sight needs a visible enemy unit")
    elif target is not None:
        raise _bad_request(f"{ability} doesn't pick a unit")
    roll = random.randint(1, 6)
    record = GamePsychicUse(
        unit_id=unit.id,
        ability=ability,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        phase=game.phase,
        roll=roll,
        target_unit_id=target.id if target else None,
    )
    game.psychic_uses.append(record)
    if roll == 1:
        battle_shock.battle_shock_outright(game, unit, f"{ability}: psychic roll of 1", roll)
    return record


def soul_sighted(game: Game, target: Unit) -> bool:
    # Whether ranged attacks that target the unit ignore cover now (Soul
    # Sight picked it this phase).
    return any(
        u.ability == SOUL_SIGHT and u.target_unit_id == target.id and _this_phase(game, u)
        for u in game.psychic_uses
    )


def active_options(game: Game, unit: Unit) -> list[str]:
    # The rule options its psychic abilities give the unit now (e.g.
    # Shrouded, this phase).
    return [
        OPTIONS[u.ability]
        for u in game.psychic_uses
        if u.unit_id == unit.id and u.ability in OPTIONS and _this_phase(game, u)
    ]
