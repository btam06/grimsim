from __future__ import annotations

import math

from fastapi import HTTPException

from app.models import (
    Game,
    GameFightPass,
    GamePileInDone,
    GameUnitConsolidation,
    GameUnitFight,
    GameUnitPileIn,
    Unit,
    UnitModel,
)
from app.services import weapon_profiles
from app.services.in_game import deployment, duty_in_death, mission_state, pathing
from app.services.in_game.deployment import TOLERANCE, Base, Placement, Point, gap
from app.services.in_game.movement import ENGAGEMENT_RANGE
from app.services.in_game.game import other_seat
from app.services.in_game.shooting import WeaponReach
from app.services.in_game.terrain import area_polygon, within
from app.services.list_building.enhancements import granted_weapons

# The fight phase. It starts with piling in: the player whose turn it is
# piles in first, then their opponent - each says when they're done. A player
# with no unit to pile in (none within Engagement Range that hasn't) is
# skipped; if neither has one, the fighting starts straight away. Then
# the units fight (see "Fighting" below).
#
# - Only a unit that's engaged, or made a charge move this turn, can pile in
#   (12.03), once. Its pile-in targets: the enemy units it's engaged with -
#   or, if it isn't engaged, those within 5" of it.
# - Its models in base contact with an enemy model stay where they are; each
#   other model can move up to 3" (how far its base's centre goes, as with
#   moving - see app/services/in_game/movement.py), ending closer to the
#   closest pile-in target - or not move at all.
# - Where they end up must be on the battlefield, not overlapping other
#   models or terrain features, and in coherency (see
#   app/services/in_game/deployment.py), with the unit engaged - each model
#   that started engaged with an enemy unit still engaged with it.

PILE_IN = 3.0
# How close an unengaged unit's pile-in targets have to be (12.03).
PILE_IN_TARGETS = 5.0
# Units engaged at the start of the Fight step (kept as marked units - see
# app/services/in_game/mission_state.py), and those that made an overrun
# fight's pile-in move.
ENGAGED_AT_FIGHT = "engaged_at_fight"
# Once the Fight step starts, the Pile In step is over - even if more units
# could pile in then (e.g. engaged by an overrun fight's pile-in): recorded
# as "seat 0" finishing piling in.
FIGHT_STEP_STARTED = 0
OVERRUN = "overrun_pile_in"
# Bases this close count as in base contact (positions come from dragging on
# screen: 0.1" is 2 pixels).
BASE_CONTACT = 0.1


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def is_fight_phase(game: Game) -> bool:
    return game.status == "in_progress" and game.phase == "fight"


def _this_phase(game: Game, record) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def done_seats(game: Game) -> set[int]:
    # The players who've finished piling in this fight phase.
    return {d.seat for d in game.pile_ins_done if _this_phase(game, d)}


def piling_seat(game: Game) -> int | None:
    # Whose turn it is to pile in: the player whose turn it is, then their
    # opponent - skipping one who's done, or has no unit to pile in; None once
    # neither has any to (or outside the fight phase).
    if not is_fight_phase(game):
        return None
    done = done_seats(game)
    if FIGHT_STEP_STARTED in done:
        return None
    for seat in (game.turn_seat, other_seat(game.turn_seat)):
        if seat not in done and _has_unit_to_pile_in(game, seat):
            return seat
    return None


def can_pile_in(game: Game, unit: Unit) -> bool:
    # It's engaged, or it made a charge move this turn.
    return engaged(game, unit) or charged(game, unit)


def _has_unit_to_pile_in(game: Game, seat: int) -> bool:
    # A unit that could pile in that hasn't yet.
    return any(
        can_pile_in(game, unit) and not piled_in(game, unit) for unit in player_units(game, seat)
    )


def piled_in(game: Game, unit: Unit) -> bool:
    return any(p.unit_id == unit.id and _this_phase(game, p) for p in game.unit_pile_ins)


def player_units(game: Game, seat: int) -> list[Unit]:
    # A player's units on the battlefield.
    player = next(p for p in game.players if p.seat == seat)
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


def _enemy_bases(game: Game, unit: Unit) -> list[Base]:
    seat = deployment.owner(game, unit).seat
    return [b for p, _, b in deployment.placed_bases(game, unit) if p.seat != seat]


def _nearest(base: Base, enemies: list[Base]) -> float:
    return min((gap(base, e) for e in enemies), default=math.inf)


def _remember(game: Game, key, compute):
    # `compute()`, worked out once for as long as no model on the battlefield
    # moves or is taken off - working out who's engaged with whom is slow
    # (oval bases are compared point by point), and deciding who fights next
    # asks again and again.
    placed = tuple((p.unit_model_id, p.x, p.y, p.rotation) for p in game.model_positions)
    cache = game.__dict__.setdefault("_battlefield_cache", {})
    if cache.get("placed") != placed:
        cache.clear()
        cache["placed"] = placed
    if key not in cache:
        cache[key] = compute()
    return cache[key]


def engaged(game: Game, unit: Unit) -> bool:
    # Whether any of its models is within Engagement Range of an enemy model.
    def compute() -> bool:
        enemies = _enemy_bases(game, unit)
        return any(
            _nearest(base, enemies) <= ENGAGEMENT_RANGE + TOLERANCE
            for base in _bases(game, unit).values()
        )

    return _remember(game, ("engaged", unit.id), compute)


def locked_models(game: Game, unit: Unit) -> set[int]:
    # Its models in base contact with an enemy model: they can't pile in.
    enemies = _enemy_bases(game, unit)
    return {
        i for i, base in _bases(game, unit).items() if _nearest(base, enemies) <= BASE_CONTACT
    }


def cant_pile_in_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't pile in now, or None if it can: in the Pile In step,
    # or as an overrun fight's pile-in (see "Fighting" below).
    if overrun_due(game, unit):
        return None
    seat = piling_seat(game)
    if seat is None:
        return "it isn't time to pile in"
    if deployment.owner(game, unit).seat != seat:
        return "it isn't that player's turn to pile in"
    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if piled_in(game, unit):
        return "it has already piled in"
    if not can_pile_in(game, unit):
        return "it isn't engaged, and didn't charge this turn"
    return None


def pile_in_targets(game: Game, unit: Unit) -> list[Unit]:
    # Its pile-in targets: the enemy units it's engaged with - or if it isn't
    # engaged, those within 5" of it.
    engaged_with = fight_targets(game, unit)
    if engaged_with:
        return engaged_with
    from app.services.in_game.charging import distance, enemy_units

    return [
        e for e in enemy_units(game, unit)
        if distance(game, unit, e) <= PILE_IN_TARGETS + TOLERANCE
    ]


def check_pile_in(
    game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]
) -> Placement:
    # Whether the unit could pile in, its models ending at `placement` ((x, y,
    # rotation) by unit model id - every one it has left, moved or not).
    if (reason := cant_pile_in_reason(game, unit)) is not None:
        raise _bad_request(f"it can't pile in: {reason}")
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    start = _bases(game, unit)
    enemies = _enemy_bases(game, unit)
    targets = [b for t in pile_in_targets(game, unit) for b in _bases(game, t).values()]
    locked = locked_models(game, unit)
    problems = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    pather = pathing.for_unit(game, unit, start, PILE_IN)
    for model in models:
        found = []
        moved = math.hypot(
            bases[model.id].x - start[model.id].x, bases[model.id].y - start[model.id].y
        )
        if moved > TOLERANCE:
            if model.id in locked:
                found.append("is in base contact with an enemy model: it can't move")
            else:
                # Round dense terrain, unless it can go through it.
                if problem := pathing.too_far(pather, start[model.id], bases[model.id], PILE_IN):
                    found.append(problem)
                if _nearest(bases[model.id], targets) >= _nearest(
                    start[model.id], targets
                ) - TOLERANCE:
                    found.append("must end closer to the closest pile-in target")
        problems[model.id] = found + problems[model.id]
    result = deployment.summarise(models, problems)
    result.paths = pather.bends(start, bases)
    if not any(
        _nearest(base, enemies) <= ENGAGEMENT_RANGE + TOLERANCE for base in bases.values()
    ):
        result.problems.append("The unit must end within Engagement Range of an enemy unit")
    result.problems += _still_engaged(game, unit, start, bases)
    return result


def _still_engaged(game: Game, unit: Unit, start: dict, bases: dict) -> list[str]:
    # Each model that started engaged with an enemy unit must end still
    # engaged with it (12.03, 12.08).
    seat = deployment.owner(game, unit).seat
    found = []
    for s_ in (1, 2):
        if s_ == seat:
            continue
        for enemy in player_units(game, s_):
            theirs = list(_bases(game, enemy).values())
            for i, before in start.items():
                if i not in bases:
                    continue
                if (
                    _nearest(before, theirs) <= ENGAGEMENT_RANGE + TOLERANCE
                    and _nearest(bases[i], theirs) > ENGAGEMENT_RANGE + TOLERANCE
                ):
                    found.append(f"A model engaged with {enemy.label} must stay engaged with it")
                    break
    return found


def pile_in(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # Moves the unit, if it can pile in like that.
    result = check_pile_in(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't pile in like that: " + "; ".join(result.problems))
    overrun = overrun_due(game, unit)
    placed = deployment.positions(game)
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    if overrun:
        # An overrun fight's pile-in, before it fights.
        mission_state.mark(game, deployment.owner(game, unit).seat, OVERRUN, unit.id)
    else:
        game.unit_pile_ins.append(
            GameUnitPileIn(
                unit_id=unit.id, battle_round=game.battle_round, turn_seat=game.turn_seat
            )
        )
    mission_state.after_move(game, unit, "pile_in")
    if not overrun:
        start_fight_step(game)


def finish_piling_in(game: Game, seat: int) -> None:
    # The player has finished piling in: their opponent's turn to (or the
    # fight goes on).
    if piling_seat(game) != seat:
        raise _bad_request("it isn't that player's turn to pile in")
    game.pile_ins_done.append(
        GamePileInDone(battle_round=game.battle_round, turn_seat=game.turn_seat, seat=seat)
    )
    start_fight_step(game)


def _marked_this_phase(game: Game, kind: str) -> set[int]:
    return {
        m.unit_id
        for m in mission_state.marked(game, kind)
        if m.battle_round == game.battle_round and m.turn_seat == game.turn_seat
    }


def start_fight_step(game: Game) -> None:
    # Once piling in is done: which units are engaged at the start of the
    # Fight step (they're eligible to fight even if that changes). Once.
    if not is_fight_phase(game) or piling_seat(game) is not None:
        return
    if FIGHT_STEP_STARTED in done_seats(game):
        return
    game.pile_ins_done.append(
        GamePileInDone(
            battle_round=game.battle_round, turn_seat=game.turn_seat, seat=FIGHT_STEP_STARTED
        )
    )
    for seat in (1, 2):
        for unit in player_units(game, seat):
            if engaged(game, unit):
                mission_state.mark(game, seat, ENGAGED_AT_FIGHT, unit.id)


def engaged_at_fight_start(game: Game, unit: Unit) -> bool:
    return unit.id in _marked_this_phase(game, ENGAGED_AT_FIGHT)


# --- fighting ---
#
# Once both players have piled in, every unit eligible to fight fights, once:
# one that's engaged, was engaged at the start of the Fight step, or made a
# charge move this turn (12.04). One that's eligible but not engaged when
# it's picked first makes an overrun fight's pile-in move (12.06) - then
# fights. A player whose every eligible unit is more than 5" from every enemy
# unit can pass instead; if both do in succession (or one does when the other
# has nothing eligible) the Fight step ends. Units with Fights First - those that charged this turn,
# or whose every model has the Fights First ability - fight first (the Fights
# First step); then the rest (the Remaining Combatants step). The players
# take turns to pick a unit to fight with: the player whose turn it is first,
# then whoever didn't pick last - unless they have no unit that can fight in
# this step, when the other player picks again. So if only one player has
# Fights First units, they fight one after another; then, since that player
# picked last, their opponent picks first in the next step.
#
# A unit fights an enemy unit within Engagement Range with its melee weapons,
# resolved by the combat calculator (app/services/combat.py): only its models
# within Engagement Range of the target attack.
#
# Once every unit that can fight has, the units that fought consolidate (or
# not) - the Consolidate step, the player whose turn it is first, then their
# opponent, each unit in whatever order its player likes: each model up to 3"
# - towards the unit it fought, if any of it is left; if not, towards the
# nearest enemy model, ending in Engagement Range of another enemy unit - or
# onto an objective (a terrain area - see TerrainObjective). A unit that
# couldn't get anywhere doing that is passed over. A stratagem can let it go
# further (e.g. Priority Reclamation: 6", provided it ends within range of
# its Acquisition objective marker - see
# app/services/in_game/stratagem_actions.py).

FIGHTS_FIRST = "Fights First"
STEPS = ("pile_in", "fights_first", "remaining", "consolidate", "done")
CONSOLIDATE = 3.0


def _fights(game: Game) -> list[GameUnitFight]:
    return [f for f in game.unit_fights if _this_phase(game, f)]


def fought(game: Game, unit: Unit) -> bool:
    return any(f.unit_id == unit.id for f in _fights(game))


def charged(game: Game, unit: Unit) -> bool:
    # It made a charge this turn.
    return any(
        c.unit_id == unit.id and c.completed and _this_phase(game, c) for c in game.unit_charges
    )


def has_fights_first(game: Game, unit: Unit) -> bool:
    # It charged this turn, or every model in it has Fights First.
    models = deployment.models_on_battlefield(game, unit)
    return charged(game, unit) or (
        bool(models)
        and all(any(a.name == FIGHTS_FIRST for a in m.model.abilities) for m in models)
    )


def eligible_to_fight(game: Game, unit: Unit) -> bool:
    # It hasn't fought this phase, and it's engaged, was engaged at the start
    # of the Fight step, or made a charge move this turn (12.04) - or an
    # engaging consolidation made it a new foe (12.08).
    return not fought(game, unit) and (
        engaged(game, unit)
        or engaged_at_fight_start(game, unit)
        or charged(game, unit)
        or new_foe(game, unit)
    )


def new_foe(game: Game, unit: Unit) -> bool:
    return unit.id in _marked_this_phase(game, NEW_FOE)


def _eligible(game: Game) -> list[Unit]:
    # Every unit on the battlefield, of either player, that can still fight -
    # once the players have passed the Fight step to its end, only new foes
    # (see NEW_FOE).
    passed = _step_passed(game)
    return [
        unit
        for seat in (1, 2)
        for unit in player_units(game, seat)
        if eligible_to_fight(game, unit) and not (passed and not new_foe(game, unit))
    ]


def overrun_due(game: Game, unit: Unit) -> bool:
    # Whether the unit, picked to fight next but unengaged, can make an
    # overrun fight's pile-in move now (12.06): it's its player's turn to
    # pick, it's eligible to fight, and it hasn't made that move yet.
    return (
        fight_step(game) in ("fights_first", "remaining")
        and deployment.owner(game, unit).seat == fighting_seat(game)
        and unit.id in {u.id for u in step_units(game)}
        and not engaged(game, unit)
        and unit.id not in _marked_this_phase(game, OVERRUN)
    )


# --- passing (Eligible to Fight, but Unable to Fight) ---
#
# When it's a player's turn to pick a unit to fight, if every unit of theirs
# that's eligible to fight is more than 5" from every enemy unit, they can
# pass: their opponent picks instead. If both pass in succession, or one
# passes when their opponent has no unit eligible to fight, the Fight step
# ends.

PASS_RANGE = 5.0


def _passes(game: Game) -> list[GameFightPass]:
    return [p for p in game.fight_passes if _this_phase(game, p)]


def can_pass(game: Game, seat: int) -> bool:
    from app.services.in_game.charging import distance, enemy_units

    if fighting_seat(game) != seat:
        return False
    mine = [u for u in step_units(game) if deployment.owner(game, u).seat == seat]
    return bool(mine) and all(
        distance(game, u, e) > PASS_RANGE + TOLERANCE
        for u in mine
        for e in enemy_units(game, u)
    )


def pass_fight(game: Game, seat: int) -> None:
    if not can_pass(game, seat):
        raise _bad_request(
            "a player can only pass when each of their units eligible to fight is more than "
            '5" from every enemy unit'
        )
    game.fight_passes.append(
        GameFightPass(
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            seat=seat,
            fights=len(_fights(game)),
        )
    )


def _step_passed(game: Game) -> bool:
    # Whether the players have passed the Fight step to its end: both in
    # succession, or one when the other had no unit eligible to fight.
    passes = _passes(game)
    if not passes:
        return False
    last = passes[-1]
    if last.fights != len(_fights(game)):
        return False
    if len(passes) >= 2 and passes[-2].fights == last.fights and passes[-2].seat != last.seat:
        return True
    others = [
        u
        for u in player_units(game, other_seat(last.seat))
        if eligible_to_fight(game, u)
    ]
    return not others


def fight_step(game: Game) -> str | None:
    # Where the fight phase is: piling in, the Fights First step, the
    # Remaining Combatants step, or done (None outside the fight phase).
    if not is_fight_phase(game):
        return None
    if piling_seat(game) is not None:
        return "pile_in"
    eligible = _eligible(game)
    if any(has_fights_first(game, u) for u in eligible):
        return "fights_first"
    if eligible:
        return "remaining"
    return "consolidate" if _unconsolidated(game) else "done"


def step_units(game: Game) -> list[Unit]:
    # The units that can fight in the current step.
    step = fight_step(game)
    if step not in ("fights_first", "remaining"):
        return []
    eligible = _eligible(game)
    if step == "fights_first":
        return [u for u in eligible if has_fights_first(game, u)]
    return eligible


def fighting_seat(game: Game) -> int | None:
    # Who picks the next unit to fight: whoever didn't pick last (the player
    # whose turn it is, to start with) - if they have a unit that can fight
    # in this step; otherwise the other player.
    units = step_units(game)
    if not units:
        return None
    seats = {deployment.owner(game, u).seat for u in units}
    fights = _fights(game)
    preferred = game.turn_seat if not fights else other_seat(fights[-1].seat)
    # A player who just passed: their opponent picks.
    passes = [p for p in game.fight_passes if _this_phase(game, p)]
    if passes and passes[-1].fights == len(fights):
        preferred = other_seat(passes[-1].seat)
    return preferred if preferred in seats else other_seat(preferred)


def cant_fight_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't fight now, or None if it can.
    step = fight_step(game)
    if step is None:
        return "units can only fight in the fight phase"
    if step == "pile_in":
        return "both players have to finish piling in first"
    if fought(game, unit):
        return "it has already fought this phase"
    if not eligible_to_fight(game, unit):
        return "it isn't engaged, wasn't at the start of the Fight step, and didn't charge"
    if not engaged(game, unit):
        if overrun_due(game, unit):
            return "it makes its overrun fight's pile-in move first"
        return "it isn't engaged with an enemy unit"
    if unit.id not in {u.id for u in step_units(game)}:
        return "it doesn't have Fights First: it fights after those that do"
    if deployment.owner(game, unit).seat != fighting_seat(game):
        return "it's the other player's turn to pick a unit to fight"
    return None


def melee_targets(game: Game, unit: Unit) -> list[Unit]:
    # The enemy units it can make melee attacks against: those it's engaged
    # with - only FLYING ones for an AIRCRAFT, and AIRCRAFT only for a FLYING
    # unit (23.04).
    from app.services.in_game.movement import can_fly, is_aircraft

    flies, aircraft = can_fly(unit), is_aircraft(unit)
    return [
        t
        for t in fight_targets(game, unit)
        if (not aircraft or can_fly(t)) and (flies or not is_aircraft(t))
    ]


def fight_targets(game: Game, unit: Unit) -> list[Unit]:
    # The enemy units within Engagement Range of it.
    seat = deployment.owner(game, unit).seat
    bases = list(_bases(game, unit).values())
    return [
        enemy
        for s in (1, 2)
        if s != seat
        for enemy in player_units(game, s)
        if any(
            _nearest(base, list(_bases(game, enemy).values())) <= ENGAGEMENT_RANGE + TOLERANCE
            for base in bases
        )
    ]


def melee_weapons(unit_model: UnitModel) -> list:
    # Its melee weapons: its own, and any its enhancement gives it.
    return [
        w
        for w in list(unit_model.weapons) + granted_weapons(unit_model)
        if w.weapon_type == "melee"
    ]


def fight_reach(game: Game, unit: Unit, target: Unit) -> tuple[list[WeaponReach], dict]:
    # Each melee weapon the unit has against the target: how many models
    # carry it, how many can fight with it (within Engagement Range of a
    # target model), and whether it's chosen to start with; and which weapons
    # each model can fight with ({unit model id: {weapon id: False}} - see
    # app/services/combat.py's `firing`).
    targets = list(_bases(game, target).values())
    reaches: dict[object, WeaponReach] = {}
    firing: dict[int, dict] = {}
    for unit_model in deployment.models_on_battlefield(game, unit):
        weapons = melee_weapons(unit_model)
        if not weapons:
            continue
        near = _nearest(_bases(game, unit)[unit_model.id], targets) <= (
            ENGAGEMENT_RANGE + TOLERANCE
        )
        for i, weapon in enumerate(weapons):
            entry = reaches.setdefault(
                weapon.id,
                WeaponReach(
                    id=weapon.id,
                    name=weapon.name,
                    range=0,
                    attacks=str(weapon.attacks),
                    extra_attacks=extra_attacks(weapon),
                ),
            )
            entry.carried_by += 1
            entry.default = entry.default or i == 0 or entry.extra_attacks
            if near:
                entry.in_range += 1
                firing.setdefault(unit_model.id, {})[weapon.id] = False
    return list(reaches.values()), firing


EXTRA_ATTACKS = "Extra Attacks"


def extra_attacks(weapon) -> bool:
    return any(a.name == EXTRA_ATTACKS for a in weapon.abilities)


def _fixed_attacks(weapon) -> int | None:
    # Its Attacks characteristic, if it isn't random.
    return int(weapon.attacks) if str(weapon.attacks).isdigit() else None


def selected_weapons(unit: Unit, weapon_ids: set) -> set:
    # The weapons the unit's models fight with (04.01, 24.11): those chosen,
    # and every [EXTRA ATTACKS] weapon its models have. Each model can only
    # have one other melee weapon chosen.
    chosen = set(weapon_ids)
    for unit_model in unit.unit_models:
        weapons = melee_weapons(unit_model)
        chosen |= {w.id for w in weapons if extra_attacks(w)}
        others = [w for w in weapons if not extra_attacks(w) and w.id in weapon_ids]
        if len({w.name for w in others}) > 1:
            raise _bad_request(
                "each model fights with one melee weapon (besides [EXTRA ATTACKS] ones): "
                + " or ".join(sorted({w.name for w in others}))
            )
    return chosen


def check_fight(
    game: Game,
    unit: Unit,
    target: Unit,
    weapon_ids: set,
    splits: dict[tuple, int] | None = None,
) -> list[tuple[Unit, dict, dict]]:
    # That the unit can fight now with those weapons: each against the
    # target - or, for those in `splits` ({(weapon, target id): attacks}),
    # with its attacks split between the targets given (04.02). The units it
    # attacks, the target first: each with which weapons each model can fight
    # it with (see fight_reach), and how many attacks each weapon makes
    # against it at most (see app/services/combat.py's `attack_limits`).
    if (reason := cant_fight_reason(game, unit)) is not None:
        raise _bad_request(f"it can't fight: {reason}")
    engaged_with = {t.id: t for t in melee_targets(game, unit)}
    splits = dict(splits or {})
    if target.id not in engaged_with or any(t not in engaged_with for _, t in splits):
        raise _bad_request("each target must be an enemy unit within Engagement Range")
    if not weapon_ids:
        raise _bad_request("choose at least one weapon to fight with")
    if (conflict := weapon_profiles.unit_conflict(unit, weapon_ids)) is not None:
        raise _bad_request(conflict)
    chosen = selected_weapons(unit, weapon_ids)
    split_weapons = {w for w, _ in splits}
    if not split_weapons <= chosen:
        raise _bad_request("only chosen weapons can split their attacks")
    targets = [target] + [
        engaged_with[t] for t in dict.fromkeys(t for _, t in splits) if t != target.id
    ]
    reaches = {t.id: fight_reach(game, unit, t) for t in targets}
    weapons = {
        w.id: w
        for unit_model in deployment.models_on_battlefield(game, unit)
        for w in melee_weapons(unit_model)
    }
    # Each weapon not split reaches the target (all but [EXTRA ATTACKS] ones,
    # which fight whatever they can).
    in_reach = {w.id for w in reaches[target.id][0] if w.in_range}
    if not (set(weapon_ids) - split_weapons) <= in_reach:
        raise _bad_request("one or more of those weapons can't reach the target")
    for key in split_weapons:
        weapon = weapons[key]
        attacks = _fixed_attacks(weapon)
        mine = {t: n for (w, t), n in splits.items() if w == key}
        if attacks is None:
            raise _bad_request(f"{weapon.name}'s attacks can't be split: they're random")
        if any(n < 1 for n in mine.values()):
            raise _bad_request("declare at least one attack against each target")
        carriers = {
            t: next(w.in_range for w in reaches[t][0] if w.id == key)
            if any(w.id == key for w in reaches[t][0])
            else 0
            for t in mine
        }
        for t, n in mine.items():
            if n > attacks * carriers[t]:
                raise _bad_request(
                    f"{weapon.name} can't make {n} attacks against {engaged_with[t].label}"
                )
        carried_by = max(w.carried_by for r in reaches.values() for w in r[0] if w.id == key)
        if len(mine) > attacks or sum(mine.values()) > attacks * carried_by:
            raise _bad_request(f"{weapon.name} doesn't have that many attacks")
    found = []
    for t in targets:
        firing = {
            model_id: {w: half for w, half in can.items() if w in chosen}
            for model_id, can in reaches[t.id][1].items()
        }
        # Split weapons make the attacks declared against each target; the
        # rest only fight the target.
        limits = {
            key: splits.get((key, t.id), 0)
            for key in chosen
            if key in split_weapons or t.id != target.id
        }
        found.append((t, firing, limits))
    return found


def record_fight(
    game: Game,
    unit: Unit,
    target: Unit,
    fights_first: bool,
    total_damage: int,
    models_destroyed: int,
) -> None:
    game.unit_fights.append(
        GameUnitFight(
            unit_id=unit.id,
            target_unit_id=target.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            seat=deployment.owner(game, unit).seat,
            fights_first=fights_first,
            total_damage=total_damage,
            models_destroyed=models_destroyed,
        )
    )
    # It has fought: its models left on the battlefield by Duty in Death go.
    duty_in_death.remove(game, unit)


# --- consolidating ---


def _unconsolidated(game: Game) -> list[GameUnitFight]:
    # Each unit that fought this phase and hasn't consolidated (or skipped it)
    # yet - its latest fight - if it's still on the battlefield and could
    # consolidate: it's within Engagement Range of an enemy, or could get
    # there or onto an objective with its 3".
    latest: dict[int, GameUnitFight] = {}
    for f in _fights(game):
        latest[f.unit_id] = f
    placed = deployment.positions(game)
    found = []
    for fight in latest.values():
        if fight.consolidation is not None:
            continue
        unit = next(
            (u for s in (1, 2) for u in player_units(game, s) if u.id == fight.unit_id), None
        )
        if unit is not None and deployment.is_deployed(unit, placed) and could_consolidate(
            game, unit
        ):
            found.append(fight)
    return found


def consolidating_seat(game: Game) -> int | None:
    # Who consolidates now (in the Consolidate step): the player whose turn
    # it is, while they have a unit to; then their opponent.
    if fight_step(game) != "consolidate":
        return None
    seats = {f.seat for f in _unconsolidated(game)}
    return game.turn_seat if game.turn_seat in seats else other_seat(game.turn_seat)


def consolidations(game: Game) -> list[GameUnitFight]:
    # The fights whose units can consolidate now: the consolidating player's.
    seat = consolidating_seat(game)
    return [f for f in _unconsolidated(game) if f.seat == seat]


def unconsolidated_fight(game: Game, unit: Unit) -> GameUnitFight | None:
    # The unit's fight this phase, if it hasn't consolidated (or skipped it)
    # since - even if it couldn't with 3" (a stratagem could let it go
    # further).
    fights = [f for f in _fights(game) if f.unit_id == unit.id]
    if not fights or fights[-1].consolidation is not None:
        return None
    return fights[-1]


def consolidation_of(game: Game, unit: Unit) -> GameUnitFight | None:
    # The unit's fight, if it can consolidate now.
    return next((f for f in consolidations(game) if f.unit_id == unit.id), None)


def consolidation_reach(game: Game, unit: Unit) -> tuple[float, str | None]:
    # How far the unit's models can consolidate: 3" - or further, with a
    # stratagem (e.g. Priority Reclamation), provided it then ends within
    # range of one of its player's selected objectives (that selection's name).
    # (Imported here: stratagem_actions imports this module.)
    from app.services.in_game import stratagem_actions

    return stratagem_actions.consolidation(game, unit)


# The consolidation modes (12.08), the first that applies:
# - ongoing: the unit's engaged - with every enemy unit it's engaged with.
#   Models in base contact with an enemy model can't move; each that moves
#   ends closer to the closest of them; each that started engaged with an
#   enemy unit ends still engaged with it.
# - engaging: one or more enemy units are within 3" of it - those the player
#   picks. Each model that moves ends closer to the closest of them, and the
#   unit ends engaged with all of them. Enemy units it's then engaged with
#   that haven't fought this phase can fight it (see NEW_FOE).
# - objective: an objective is within 3" of it - the one the player picks.
#   Each model that moves ends within range of it or closer to it, and the
#   unit ends within range of it.
# Otherwise it can't consolidate. (A stratagem letting it move further - see
# consolidation_reach - reaches further for its enemy units and objectives.)
ONGOING, ENGAGING, OBJECTIVE = "ongoing", "engaging", "objective"
# Enemy units an engaging consolidation ended engaged with that hadn't fought
# yet (kept as marked units): each becomes eligible to fight.
NEW_FOE = "new_foe"


def _objective_distance(game: Game, objective, base: Base) -> float:
    return min(deployment.distance_to_polygon(base, area_polygon(a)) for a in objective.areas)


def consolidation_mode(game: Game, unit: Unit) -> tuple[str, list] | None:
    # Which consolidation mode the unit makes, and the enemy units (or
    # objectives) it can pick from - all of them, for an ongoing
    # consolidation. None if it can't consolidate.
    from app.services.in_game.charging import distance, enemy_units

    engaged_with = fight_targets(game, unit)
    if engaged_with:
        return ONGOING, engaged_with
    reach, _ = consolidation_reach(game, unit)
    near = [e for e in enemy_units(game, unit) if distance(game, unit, e) <= reach + TOLERANCE]
    if near:
        return ENGAGING, near
    bases = list(_bases(game, unit).values())
    layout = game.layout
    objectives = [
        o
        for o in (layout.objectives if layout is not None else [])
        if o.areas
        and any(_objective_distance(game, o, b) <= reach + TOLERANCE for b in bases)
    ]
    if objectives:
        return OBJECTIVE, objectives
    return None


def could_consolidate(game: Game, unit: Unit) -> bool:
    return consolidation_mode(game, unit) is not None


def _target(game: Game, fight: GameUnitFight) -> Unit | None:
    # The unit it fought, if any of it is left.
    return next(
        (u for s in (1, 2) for u in player_units(game, s) if u.id == fight.target_unit_id), None
    )


def objective_areas(game: Game) -> list[list[Point]]:
    # The terrain areas that are objectives (see TerrainObjective).
    layout = game.layout
    if layout is None:
        return []
    return [area_polygon(a) for o in layout.objectives for a in o.areas]


def _towards(
    models,
    start: dict,
    bases: dict,
    distance,
    name: str,
    pather: pathing.Pather,
    reach: float = CONSOLIDATE,
    locked: set | None = None,
) -> dict[int, list[str]]:
    # Each moved model must end closer to something (`distance` from a base to
    # it) than it started - or at it (a distance of 0) - and no more than
    # `reach` (3") from where it was. `locked` models can't move.
    problems = {}
    for model in models:
        found = []
        moved = math.hypot(
            bases[model.id].x - start[model.id].x, bases[model.id].y - start[model.id].y
        )
        if moved > TOLERANCE:
            if locked and model.id in locked:
                found.append("is in base contact with an enemy model, so can't move")
            if problem := pathing.too_far(pather, start[model.id], bases[model.id], reach):
                found.append(problem)
            after = distance(bases[model.id])
            if after > TOLERANCE and after >= distance(start[model.id]) - TOLERANCE:
                found.append(f"must end closer to {name}")
        problems[model.id] = found
    return problems


def _picked(mode: str, options: list, picks: list[int] | None) -> list:
    # The enemy units (or objective) the player picked, from `options` - by
    # default, the first (the closest unit, for engaging).
    if mode == ONGOING:
        return options
    by_id = {o.id: o for o in options}
    if picks:
        if any(i not in by_id for i in picks):
            raise _bad_request(
                "pick enemy units within 3\" of it" if mode == ENGAGING
                else "pick an objective within 3\" of it"
            )
        chosen = [by_id[i] for i in dict.fromkeys(picks)]
    else:
        chosen = options[:1]
    if mode == OBJECTIVE and len(chosen) > 1:
        raise _bad_request("pick one objective")
    return chosen


def check_consolidation(
    game: Game,
    unit: Unit,
    placement: dict[int, tuple[float, float, float]],
    picks: list[int] | None = None,
) -> Placement:
    # Whether the unit could consolidate, its models ending at `placement`
    # ((x, y, rotation) by unit model id - every one it has left), in its
    # consolidation mode - towards the enemy units (or the objective) in
    # `picks` (ids), for engaging and objective consolidations.
    fight = consolidation_of(game, unit)
    found = consolidation_mode(game, unit)
    if fight is None or found is None:
        raise _bad_request("it can't consolidate now")
    mode, options = found
    chosen = _picked(mode, options, picks)
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    start = _bases(game, unit)
    physical = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    reach, ending_within = consolidation_reach(game, unit)
    # Round dense terrain, unless it can go through it.
    pather = pathing.for_unit(game, unit, start, reach)
    # Further than 3": only ending within range of one of those objectives.
    further = ending_within is not None and any(
        pathing.too_far(pather, start[m.id], bases[m.id], CONSOLIDATE) for m in models
    )
    unit_problems = []
    if further and not _ends_within_selected(game, unit, bases, ending_within):
        unit_problems.append(
            f'Moving more than {CONSOLIDATE:g}", the unit must end within range of its '
            f"{ending_within} objective marker"
        )
    if mode == OBJECTIVE:
        [objective] = chosen

        def distance(base: Base) -> float:
            return _objective_distance(game, objective, base)

        per_model = _towards(models, start, bases, distance, "the objective", pather, reach)
        if not any(distance(b) <= TOLERANCE for b in bases.values()):
            unit_problems.append("The unit must end within range of the objective")
    else:
        targets = [b for t in chosen for b in _bases(game, t).values()]
        name = chosen[0].label if len(chosen) == 1 else "the closest of those enemy units"
        per_model = _towards(
            models,
            start,
            bases,
            lambda b: _nearest(b, targets),
            name,
            pather,
            reach,
            locked=locked_models(game, unit) if mode == ONGOING else None,
        )
        if mode == ONGOING:
            unit_problems += _still_engaged(game, unit, start, bases)
        else:
            for t in chosen:
                theirs = list(_bases(game, t).values())
                if not any(
                    _nearest(b, theirs) <= ENGAGEMENT_RANGE + TOLERANCE for b in bases.values()
                ):
                    unit_problems.append(f"The unit must end engaged with {t.label}")
    result = deployment.summarise(models, {i: per_model[i] + physical[i] for i in physical})
    result.problems += unit_problems
    result.paths = pather.bends(start, bases)
    return result


def _ends_within_selected(game: Game, unit: Unit, bases: dict[int, Base], name: str) -> bool:
    # Whether the unit, its models at `bases`, would be within range of one of
    # its player's `name` selected objectives.
    from app.services.in_game import selected_objectives

    seat = deployment.owner(game, unit).seat
    ids = selected_objectives.objective_ids(game, seat, name)
    layout = game.layout
    return any(
        within(base, area_polygon(a))
        for o in (layout.objectives if layout is not None else [])
        if o.id in ids
        for a in o.areas
        for base in bases.values()
    )


def consolidate(
    game: Game,
    unit: Unit,
    placement: dict[int, tuple[float, float, float]],
    picks: list[int] | None = None,
) -> None:
    # Moves the unit, if it can consolidate like that. After an engaging
    # consolidation, each enemy unit it's engaged with that hasn't fought this
    # phase becomes eligible to fight (and fights next - see NEW_FOE).
    result = check_consolidation(game, unit, placement, picks)
    if not result.valid:
        raise _bad_request("can't consolidate like that: " + "; ".join(result.problems))
    mode, _ = consolidation_mode(game, unit)
    fight = consolidation_of(game, unit)
    placed = deployment.positions(game)
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    fight.consolidation = GameUnitConsolidation(moved=True)
    mission_state.after_move(game, unit, "consolidate")
    if mode == ENGAGING:
        for enemy in fight_targets(game, unit):
            if not fought(game, enemy):
                mission_state.mark(game, deployment.owner(game, enemy).seat, NEW_FOE, enemy.id)


def skip_consolidation(game: Game, unit: Unit) -> None:
    fight = consolidation_of(game, unit)
    if fight is None:
        raise _bad_request("it can't consolidate now")
    fight.consolidation = GameUnitConsolidation(moved=False)
