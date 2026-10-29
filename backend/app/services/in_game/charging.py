from __future__ import annotations

import math
import random

from fastapi import HTTPException

from app.models import Game, GameChargeTarget, GameUnitCharge, Unit
from app.seeds import factions as faction_seeds
from app.services.in_game import (
    actions,
    command_phase,
    deployment,
    mission_state,
    movement,
    pathing,
    shoot_scoot,
)
from app.services.list_building import detachment_rules
from app.services.list_building import enhancements as enhancement_rules
from app.services.in_game.deployment import TOLERANCE, Base, Placement, gap
from app.services.in_game.movement import ENGAGEMENT_RANGE

# Charging in the charge phase. In their turn's charge phase a player can
# charge with each of their units once - any unit on the battlefield can,
# but one that Advanced or Fell Back this turn (unless an ability selected in
# the Command phase lets it - see app/services/in_game/command_phase.py):
#
# - It declares a charge (11.02) - only if it's unengaged and within 12" of
#   an enemy unit - and rolls it: 2D6, kept for the phase (rolling again gives
#   the same roll).
# - Its charge targets (11.04) are one or more enemy units within 12" and
#   within the roll: one of its models within the roll of one of theirs, base
#   to base. If none is, the charge fails - it doesn't move.
# - Its models then move up to the roll each (how far its base's centre goes,
#   round terrain and enemy models - see app/services/in_game/movement.py),
#   each ending closer to a charge target. The unit must end engaged with
#   every charge target, and with no other enemy unit. Where they end up must
#   be on the battlefield, not overlapping other models or terrain features,
#   and in coherency (see app/services/in_game/deployment.py). A FLYING unit
#   can take to the skies: 2" less (none less with Hover), over models and
#   terrain.
#
# A detachment rule can add to the charge rolls of the units it reaches
# (faction_seeds.CHARGE_BONUSES - e.g. Death Blow: +1 for ADEPTUS ASTARTES
# TERMINATOR units).
#
# Some abilities let a unit re-roll its charge roll, once, before it charges
# (datasheet_abilities CHARGE_REROLLS); some make each enemy unit engaged with
# it after its charge move take a Battle-shock test (AFTER_CHARGE_BATTLE_SHOCK
# - e.g. the Deathwatch's Terminatus Assault: -1 unless it's IMPERIUM or
# CHAOS).

CHARGE_DICE = 2
# How close an enemy unit has to be to declare a charge, and to be a charge
# target.
CHARGE_RANGE = 12.0
# A re-rolled charge, this phase (kept as a marked unit - see
# app/services/in_game/mission_state.py).
CHARGE_REROLLED = "charge_rerolled"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def is_charge_phase(game: Game) -> bool:
    return game.status == "in_progress" and game.phase == "charge"


def unit_charge(game: Game, unit: Unit) -> GameUnitCharge | None:
    # The unit's charge this phase (rolled, or made), if any.
    return next(
        (
            c
            for c in game.unit_charges
            if c.unit_id == unit.id
            and c.battle_round == game.battle_round
            and c.turn_seat == game.turn_seat
        ),
        None,
    )


def charging_units(game: Game) -> list[Unit]:
    # The units the player whose turn it is has on the battlefield.
    if game.turn_seat is None:
        return []
    player = next(p for p in game.players if p.seat == game.turn_seat)
    placed = deployment.positions(game)
    return [
        u for u in deployment.deployable_units(player) if deployment.is_deployed(u, placed)
    ]


def _bases(game: Game, unit: Unit) -> dict[int, Base]:
    placed = deployment.positions(game)
    return {
        m.id: deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    }


def cant_charge_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't declare a charge this turn because of what it did
    # (an action, or it Advanced or Fell Back), or None.
    # (Imported here: shooting imports movement, which charging's callers use.)
    from app.services.in_game import embarked
    from app.services.in_game.shooting import move_status

    if (reason := actions.blocks(game, unit, "charge")) is not None:
        return reason
    if movement.is_aircraft(unit):
        return "AIRCRAFT units can't declare a charge"
    if (reason := embarked.no_charge(game, unit)) is not None:
        return reason
    if shoot_scoot.no_charge(game, unit):
        return "it moved after shooting this turn"
    status = move_status(game, unit)
    if status.advanced and not command_phase.eligible_after(game, unit, "advanced", "charge"):
        return "it Advanced this turn"
    if status.fell_back and not command_phase.eligible_after(game, unit, "fell_back", "charge"):
        return "it Fell Back this turn"
    return None


def declare_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't declare a charge now (11.01), or None: what it did
    # this turn (cant_charge_reason), or it's engaged, or no enemy unit is
    # within 12".
    if (reason := cant_charge_reason(game, unit)) is not None:
        return reason
    if movement.in_engagement_range(game, unit):
        return "it's engaged"
    if not any(
        distance(game, unit, enemy) <= CHARGE_RANGE + TOLERANCE for enemy in enemy_units(game, unit)
    ):
        return 'no enemy unit is within 12"'
    return None


def _check_unit(game: Game, unit: Unit, declaring: bool = False) -> None:
    # That the unit can charge now: the charge phase of its owner's turn, it's
    # on the battlefield, it didn't Advance or Fall Back this turn, and it
    # hasn't charged yet this phase.
    if not is_charge_phase(game):
        raise _bad_request("units can only charge in the charge phase")
    if deployment.owner(game, unit).seat != game.turn_seat:
        raise _bad_request("only the player whose turn it is can charge with their units")
    if not deployment.is_deployed(unit, deployment.positions(game)):
        raise _bad_request("that unit isn't on the battlefield")
    charge = unit_charge(game, unit)
    if charge is not None and charge.completed:
        raise _bad_request("that unit has already charged this phase")
    check = declare_reason if declaring else cant_charge_reason
    if (reason := check(game, unit)) is not None:
        raise _bad_request(f"it can't charge: {reason}")


def roll_charge(game: Game, unit: Unit) -> GameUnitCharge:
    # Rolls the unit's charge (2D6) - once a phase: if it's already rolled,
    # that roll stands. (Rolling is declaring it: it must be unengaged, with
    # an enemy unit within 12".)
    _check_unit(game, unit, declaring=unit_charge(game, unit) is None)
    if (charge := unit_charge(game, unit)) is not None:
        return charge
    first, second = (random.randint(1, 6) for _ in range(CHARGE_DICE))
    charge = GameUnitCharge(
        unit_id=unit.id,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        first_die=first,
        second_die=second,
        completed=False,
    )
    game.unit_charges.append(charge)
    return charge


def _abilities(unit: Unit) -> set[str]:
    return {a.name for m in unit.unit_models for a in m.model.abilities}


def _rerolled(game: Game, unit: Unit) -> bool:
    return any(
        m.unit_id == unit.id
        and m.battle_round == game.battle_round
        and m.turn_seat == game.turn_seat
        for m in mission_state.marked(game, CHARGE_REROLLED)
    )


def can_reroll(game: Game, unit: Unit) -> bool:
    # Whether the unit can re-roll its charge roll now: an ability lets it,
    # it's rolled but not charged, and it hasn't re-rolled already.
    from app.seeds import datasheet_abilities

    charge = unit_charge(game, unit)
    return (
        charge is not None
        and not charge.completed
        and bool(_abilities(unit) & datasheet_abilities.CHARGE_REROLLS)
        and not _rerolled(game, unit)
    )


def reroll_charge(game: Game, unit: Unit) -> GameUnitCharge:
    # Re-rolls the unit's charge roll (both dice), if it can.
    _check_unit(game, unit)
    if not can_reroll(game, unit):
        raise _bad_request("that unit can't re-roll its charge roll")
    charge = unit_charge(game, unit)
    charge.first_die, charge.second_die = (random.randint(1, 6) for _ in range(CHARGE_DICE))
    mission_state.mark(game, deployment.owner(game, unit).seat, CHARGE_REROLLED, unit.id)
    return charge


def _after_charge(game: Game, unit: Unit) -> None:
    # The unit ended a charge move: abilities that make the enemy units
    # engaged with it take a Battle-shock test.
    from app.seeds import datasheet_abilities
    from app.services.in_game import battle_shock

    config = datasheet_abilities.AFTER_CHARGE_BATTLE_SHOCK
    rules = [(name, config[name]) for name in _abilities(unit) if name in config]
    if not rules:
        return
    bases = list(_bases(game, unit).values())
    for enemy in enemy_units(game, unit):
        engaged = any(
            gap(b, e) <= ENGAGEMENT_RANGE + TOLERANCE
            for b in bases
            for e in _bases(game, enemy).values()
        )
        if not engaged or battle_shock.is_battle_shocked(game, enemy):
            continue
        if any(t.unit_id == enemy.id for t in battle_shock.pending(game)):
            continue
        name, (modifier, spared) = rules[0]
        keywords = {k.name for m in enemy.unit_models for k in m.model.keywords}
        battle_shock.require(game, enemy, name, 0 if keywords & set(spared) else modifier)


def charge_bonus(game: Game, unit: Unit) -> int:
    # What the unit's list's detachment rules, and its own abilities (e.g.
    # Optimised Gait - see movement.roll_bonus), add to its charge rolls.
    rules = enhancement_rules.list_rules(deployment.owner(game, unit).army_list)
    return sum(
        faction_seeds.CHARGE_BONUSES[rule.name]
        for rule in rules
        if rule.name in faction_seeds.CHARGE_BONUSES and detachment_rules.applies_to(rule, unit)
    ) + movement.roll_bonus(game, unit, "charge")


def charge_roll(game: Game, unit: Unit) -> int | None:
    # The unit's charge roll this phase, with any bonus - None if it hasn't
    # rolled.
    charge = unit_charge(game, unit)
    return charge.roll + charge_bonus(game, unit) if charge is not None else None


def enemy_units(game: Game, unit: Unit) -> list[Unit]:
    seat = deployment.owner(game, unit).seat
    placed = deployment.positions(game)
    return [
        u
        for player in game.players
        if player.seat != seat
        for u in deployment.deployable_units(player)
        if deployment.is_deployed(u, placed)
    ]


def distance(game: Game, unit: Unit, target: Unit) -> float:
    # The closest any of the unit's models is to any of the target's, base to
    # base.
    targets = list(_bases(game, target).values())
    return min(
        (gap(base, t) for base in _bases(game, unit).values() for t in targets),
        default=math.inf,
    )


def in_reach(game: Game, unit: Unit, target: Unit, roll: int) -> bool:
    # Whether the target can be a charge target with that roll: within it,
    # and within 12".
    return distance(game, unit, target) <= min(roll, CHARGE_RANGE) + TOLERANCE


def failed(game: Game, unit: Unit) -> bool:
    # It's rolled, and no enemy unit is in reach: the charge fails.
    charge = unit_charge(game, unit)
    return (
        charge is not None
        and not charge.completed
        and not any(
            in_reach(game, unit, t, charge_roll(game, unit)) for t in enemy_units(game, unit)
        )
    )


def _nearest(base: Base, targets: list[Base]) -> float:
    return min(gap(base, t) for t in targets)


def check_charge(
    game: Game,
    unit: Unit,
    targets: list[Unit],
    placement: dict[int, tuple[float, float, float]],
    take_to_skies: bool = False,
) -> Placement:
    # Whether the unit could charge the targets, its models ending at
    # `placement` ((x, y, rotation) by unit model id - every one it has left,
    # moved or not) - taking to the skies, if it says so and can FLY.
    _check_unit(game, unit)
    charge = unit_charge(game, unit)
    if charge is None:
        raise _bad_request("roll the charge first")
    if not targets:
        raise _bad_request("select one or more charge targets")
    roll = charge_roll(game, unit)
    enemies_now = {u.id for u in enemy_units(game, unit)}
    for target in targets:
        if target.id not in enemies_now:
            raise _bad_request("each charge target must be an enemy unit on the battlefield")
        if movement.is_aircraft(target) and not movement.can_fly(unit):
            raise _bad_request("only FLYING units can charge AIRCRAFT")
        if not in_reach(game, unit, target, roll):
            raise _bad_request(
                f"{target.label} can't be a charge target: the closest model is "
                f'{distance(game, unit, target):.1f}" away (rolled {roll}; at most 12")'
            )
    take_to_skies = take_to_skies and movement.can_fly(unit)
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    start = _bases(game, unit)
    target_bases = [b for t in targets for b in _bases(game, t).values()]
    problems = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    pather = pathing.for_unit(game, unit, start, roll, "all" if take_to_skies else "none")
    for model in models:
        found = []
        limit = roll - (2 if take_to_skies and not movement._hovers(model) else 0)
        if problem := pathing.too_far(pather, start[model.id], bases[model.id], limit):
            found.append(problem)
        # Each model ends closer to a charge target - if it doesn't end
        # engaged with one.
        before = _nearest(start[model.id], target_bases)
        after = _nearest(bases[model.id], target_bases)
        if after > ENGAGEMENT_RANGE + TOLERANCE and after >= before - TOLERANCE:
            found.append("must end closer to a charge target")
        problems[model.id] = found + problems[model.id]
    result = deployment.summarise(models, problems)
    result.paths = pather.bends(start, bases)
    # Engaged with every charge target - and no other enemy unit.
    for target in targets:
        theirs = list(_bases(game, target).values())
        if not any(_nearest(b, theirs) <= ENGAGEMENT_RANGE + TOLERANCE for b in bases.values()):
            result.problems.append(f"The unit must end engaged with {target.label}")
    chosen = {t.id for t in targets}
    for enemy in enemy_units(game, unit):
        if enemy.id in chosen:
            continue
        theirs = list(_bases(game, enemy).values())
        if any(_nearest(b, theirs) <= ENGAGEMENT_RANGE + TOLERANCE for b in bases.values()):
            result.problems.append(
                f"The unit can't end engaged with {enemy.label}, which isn't a charge target"
            )
    return result


def make_charge(
    game: Game,
    unit: Unit,
    targets: list[Unit],
    placement: dict[int, tuple[float, float, float]],
    take_to_skies: bool = False,
) -> None:
    # Moves the unit into the charge, if it can.
    result = check_charge(game, unit, targets, placement, take_to_skies)
    if not result.valid:
        raise _bad_request("can't charge like that: " + "; ".join(result.problems))
    placed = deployment.positions(game)
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    charge = unit_charge(game, unit)
    charge.target_unit_id = targets[0].id
    charge.extra_targets = [GameChargeTarget(unit_id=t.id) for t in targets[1:]]
    charge.completed = True
    mission_state.after_move(game, unit)
    _after_charge(game, unit)
