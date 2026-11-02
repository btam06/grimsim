from __future__ import annotations


from fastapi import HTTPException

from app.models import Unit
from app.engine.state import PHASES, Game, GameReanimation, GameResurrection
from app.services import dice
from app.services.in_game import deployment, heal

# The Necrons' Reanimation Protocols, in a game. At the end of a player's
# command phase, each of their units on the battlefield with the ability
# heals D3 wounds (see app/services/in_game/heal.py: restoring lost wounds,
# or returning destroyed models for the player to set up).
#
# A unit with a Resurrection Orb (a model with the ability, or wargear that
# gives it) can resurrect, once a battle, at the end of any phase: its
# Reanimation Protocols activate, healing D6 wounds instead. Its player
# declares it during the phase (and can take that back), and it happens as
# the phase ends - one unit a turn, for each player.

REANIMATION_PROTOCOLS = "Reanimation Protocols"
HEAL_DICE = 3
# A friendly model with it within 3": an additional D3 wounds healed each time
# a unit's Reanimation Protocols activate.
NANOSCARAB_BEAM = "Nanoscarab Reanimation Beam (Aura)"
BEAM_RANGE = 3.0
RESURRECTION_ORB = "Resurrection Orb"
RESURRECT_DICE = 6


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


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
        roll = dice.randint(1, HEAL_DICE) + beam_bonus(game, unit)
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


# --- Resurrection Orbs ---


def has_orb(game: Game, unit: Unit) -> bool:
    # A model of the unit on the battlefield has a Resurrection Orb (the
    # ability, or wargear that gives it).
    return any(
        a.name == RESURRECTION_ORB
        for m in deployment.models_on_battlefield(game, unit)
        for a in list(m.model.abilities) + [a for g in m.wargear for a in g.abilities]
    )


def _now(game: Game, record: GameResurrection) -> bool:
    return (record.battle_round, record.turn_seat, record.phase) == (
        game.battle_round, game.turn_seat, game.phase
    )


def resurrections(game: Game) -> list[GameResurrection]:
    # The resurrections declared (or resolved) this phase.
    return [r for r in game.resurrections if _now(game, r)]


def cant_resurrect(game: Game, unit: Unit) -> str | None:
    # Why the unit can't resurrect at the end of this phase, or None.
    if game.status != "in_progress" or game.phase not in PHASES:
        return "units resurrect at the end of a phase"
    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if not has_orb(game, unit) or not has_reanimation_protocols(unit):
        return "it has no Resurrection Orb"
    if any(r.unit_id == unit.id for r in game.resurrections):
        return "it has used its Resurrection Orb (once a battle)"
    seat = deployment.owner(game, unit).seat
    if any(
        r.seat == seat and (r.battle_round, r.turn_seat) == (game.battle_round, game.turn_seat)
        for r in game.resurrections
    ):
        return "its player has resurrected a unit this turn"
    return None


def resurrectable(game: Game) -> list[Unit]:
    # Every unit that could resurrect at the end of this phase.
    placed = deployment.positions(game)
    return [
        u
        for p in game.players
        for u in deployment.deployable_units(p)
        if deployment.is_deployed(u, placed) and cant_resurrect(game, u) is None
    ]


def declare(game: Game, seat: int, unit: Unit) -> None:
    # The unit will resurrect at the end of this phase.
    if deployment.owner(game, unit).seat != seat:
        raise _bad_request("that isn't one of that player's units")
    if (why := cant_resurrect(game, unit)) is not None:
        raise _bad_request(f"it can't resurrect: {why}")
    game.resurrections.append(
        GameResurrection(
            seat=seat, unit_id=unit.id, battle_round=game.battle_round,
            turn_seat=game.turn_seat, phase=game.phase,
        )
    )


def cancel(game: Game, seat: int, unit: Unit) -> None:
    # Taken back, before the phase ends.
    record = next(
        (r for r in resurrections(game) if r.unit_id == unit.id and r.roll is None), None
    )
    if record is None or record.seat != seat:
        raise _bad_request("that unit isn't resurrecting at the end of this phase")
    game.resurrections.remove(record)


def resurrect(game: Game) -> None:
    # The end of the phase: each unit declared resurrects - if it still has
    # its orb on the battlefield - healing D6 wounds.
    for record in resurrections(game):
        if record.roll is not None:
            continue
        unit = deployment.find_unit(game, record.unit_id)
        if not deployment.is_deployed(unit, deployment.positions(game)) or not has_orb(game, unit):
            game.resurrections.remove(record)
            continue
        record.roll = dice.randint(1, RESURRECT_DICE) + beam_bonus(game, unit)
        record.healed, record.returned = heal.heal(game, unit, record.roll)


def beam_bonus(game: Game, unit: Unit) -> int:
    # The additional wounds the unit heals as its Reanimation Protocols
    # activate: a D3 if a friendly model with a Nanoscarab Reanimation Beam
    # is within 3" of it (its own included).
    from app.services.in_game.deployment import TOLERANCE, gap

    seat = deployment.owner(game, unit).seat
    player = next(p for p in game.players if p.seat == seat)
    placed = deployment.positions(game)

    def base(m):
        p = placed[m.id]
        return deployment.base_at(m, p.x, p.y, p.rotation)

    mine = [base(m) for m in deployment.models_on_battlefield(game, unit)]
    for other in deployment.deployable_units(player):
        for m in deployment.models_on_battlefield(game, other):
            if not any(a.name == NANOSCARAB_BEAM for a in m.model.abilities):
                continue
            source = base(m)
            if any(gap(source, b) <= BEAM_RANGE + TOLERANCE for b in mine):
                return dice.randint(1, 3)
    return 0
