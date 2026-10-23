from __future__ import annotations

import math

from fastapi import HTTPException

from app.models import (
    Game,
    GamePileInDone,
    GameUnitConsolidation,
    GameUnitFight,
    GameUnitPileIn,
    Unit,
    UnitModel,
)
from app.services.in_game import deployment
from app.services.in_game.deployment import TOLERANCE, Base, Placement, Point, gap
from app.services.in_game.movement import ENGAGEMENT_RANGE
from app.services.in_game.game import other_seat
from app.services.in_game.shooting import WeaponReach
from app.services.in_game.terrain import area_polygon
from app.services.list_building.enhancements import granted_weapons

# The fight phase. It starts with piling in: the player whose turn it is
# piles in first, then their opponent - each says when they're done. Then
# the units fight (see "Fighting" below).
#
# - Only a unit within Engagement Range of an enemy model can pile in, once.
# - Its models in base contact with an enemy model stay where they are; each
#   other model can move up to 3" (how far its base's centre goes, as with
#   moving - see app/services/in_game/movement.py), ending closer to the
#   nearest enemy model - or not move at all.
# - Where they end up must be on the battlefield, not overlapping other
#   models or terrain features, and in coherency (see
#   app/services/in_game/deployment.py), with the unit still within
#   Engagement Range of an enemy.

PILE_IN = 3.0
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
    # opponent; None once both are done (or outside the fight phase).
    if not is_fight_phase(game):
        return None
    done = done_seats(game)
    for seat in (game.turn_seat, other_seat(game.turn_seat)):
        if seat not in done:
            return seat
    return None


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
    # Why the unit can't pile in now, or None if it can.
    seat = piling_seat(game)
    if seat is None:
        return "it isn't time to pile in"
    if deployment.owner(game, unit).seat != seat:
        return "it isn't that player's turn to pile in"
    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if piled_in(game, unit):
        return "it has already piled in"
    if not engaged(game, unit):
        return "it isn't within Engagement Range of an enemy unit"
    return None


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
    locked = locked_models(game, unit)
    problems = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )
    for model in models:
        found = []
        moved = math.hypot(
            bases[model.id].x - start[model.id].x, bases[model.id].y - start[model.id].y
        )
        if moved > TOLERANCE:
            if model.id in locked:
                found.append("is in base contact with an enemy model: it can't move")
            else:
                if moved > PILE_IN + TOLERANCE:
                    found.append(f'would move {moved:.1f}" (it can move 3")')
                if _nearest(bases[model.id], enemies) >= _nearest(
                    start[model.id], enemies
                ) - TOLERANCE:
                    found.append("must end closer to the nearest enemy model")
        problems[model.id] = found + problems[model.id]
    result = deployment.summarise(models, problems)
    if not any(
        _nearest(base, enemies) <= ENGAGEMENT_RANGE + TOLERANCE for base in bases.values()
    ):
        result.problems.append("The unit must end within Engagement Range of an enemy unit")
    return result


def pile_in(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # Moves the unit, if it can pile in like that.
    result = check_pile_in(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't pile in like that: " + "; ".join(result.problems))
    placed = deployment.positions(game)
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    game.unit_pile_ins.append(
        GameUnitPileIn(unit_id=unit.id, battle_round=game.battle_round, turn_seat=game.turn_seat)
    )


def finish_piling_in(game: Game, seat: int) -> None:
    # The player has finished piling in: their opponent's turn to (or the
    # fight goes on).
    if piling_seat(game) != seat:
        raise _bad_request("it isn't that player's turn to pile in")
    game.pile_ins_done.append(
        GamePileInDone(battle_round=game.battle_round, turn_seat=game.turn_seat, seat=seat)
    )


# --- fighting ---
#
# Once both players have piled in, every unit within Engagement Range of an
# enemy fights, once. Units with Fights First - those that charged this turn,
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
# Then it can consolidate (or not) before the next unit's picked: each model
# up to 3" - towards the unit it fought, if any of it is left; if not,
# towards the nearest enemy model, ending in Engagement Range of another
# enemy unit - or onto an objective (a terrain area - see TerrainObjective).
# (A unit it ends up engaged with that hasn't fought can then fight.)

FIGHTS_FIRST = "Fights First"
STEPS = ("pile_in", "consolidate", "fights_first", "remaining", "done")
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


def _eligible(game: Game) -> list[Unit]:
    # Every unit on the battlefield, of either player, that can still fight:
    # it hasn't, and it's within Engagement Range of an enemy.
    return [
        unit
        for seat in (1, 2)
        for unit in player_units(game, seat)
        if not fought(game, unit) and engaged(game, unit)
    ]


def fight_step(game: Game) -> str | None:
    # Where the fight phase is: piling in, the Fights First step, the
    # Remaining Combatants step, or done (None outside the fight phase).
    if not is_fight_phase(game):
        return None
    if piling_seat(game) is not None:
        return "pile_in"
    if consolidating(game) is not None:
        return "consolidate"
    eligible = _eligible(game)
    if any(has_fights_first(game, u) for u in eligible):
        return "fights_first"
    return "remaining" if eligible else "done"


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
    return preferred if preferred in seats else other_seat(preferred)


def cant_fight_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't fight now, or None if it can.
    step = fight_step(game)
    if step is None:
        return "units can only fight in the fight phase"
    if step == "pile_in":
        return "both players have to finish piling in first"
    if step == "consolidate":
        return "the unit that just fought has to consolidate (or not) first"
    if fought(game, unit):
        return "it has already fought this phase"
    if not engaged(game, unit):
        return "it isn't within Engagement Range of an enemy unit"
    if unit.id not in {u.id for u in step_units(game)}:
        return "it doesn't have Fights First: it fights after those that do"
    if deployment.owner(game, unit).seat != fighting_seat(game):
        return "it's the other player's turn to pick a unit to fight"
    return None


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
                weapon.id, WeaponReach(id=weapon.id, name=weapon.name, range=0)
            )
            entry.carried_by += 1
            entry.default = entry.default or i == 0
            if near:
                entry.in_range += 1
                firing.setdefault(unit_model.id, {})[weapon.id] = False
    return list(reaches.values()), firing


def check_fight(game: Game, unit: Unit, target: Unit, weapon_ids: set) -> dict:
    # That the unit can fight the target with those weapons now; which
    # weapons each of its models can fight with.
    if (reason := cant_fight_reason(game, unit)) is not None:
        raise _bad_request(f"it can't fight: {reason}")
    if target.id not in {t.id for t in fight_targets(game, unit)}:
        raise _bad_request("the target must be an enemy unit within Engagement Range")
    if not weapon_ids:
        raise _bad_request("choose at least one weapon to fight with")
    weapons, firing = fight_reach(game, unit, target)
    if not weapon_ids <= {w.id for w in weapons if w.in_range}:
        raise _bad_request("one or more of those weapons can't reach the target")
    return firing


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


# --- consolidating ---


def consolidating(game: Game) -> GameUnitFight | None:
    # The fight whose unit hasn't consolidated (or skipped it) yet - if that
    # unit's still on the battlefield.
    fights = _fights(game)
    if not fights or fights[-1].consolidation is not None:
        return None
    last = fights[-1]
    placed = deployment.positions(game)
    unit = next(
        (u for s in (1, 2) for u in player_units(game, s) if u.id == last.unit_id), None
    )
    return last if unit is not None and deployment.is_deployed(unit, placed) else None


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
    models, start: dict, bases: dict, distance, name: str
) -> dict[int, list[str]]:
    # Each moved model must end closer to something (`distance` from a base to
    # it) than it started - and no more than 3" from where it was.
    problems = {}
    for model in models:
        found = []
        moved = math.hypot(
            bases[model.id].x - start[model.id].x, bases[model.id].y - start[model.id].y
        )
        if moved > TOLERANCE:
            if moved > CONSOLIDATE + TOLERANCE:
                found.append(f'would move {moved:.1f}" (it can move 3")')
            if distance(bases[model.id]) >= distance(start[model.id]) - TOLERANCE:
                found.append(f"must end closer to {name}")
        problems[model.id] = found
    return problems


def check_consolidation(
    game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]
) -> Placement:
    # Whether the unit could consolidate, its models ending at `placement`
    # ((x, y, rotation) by unit model id - every one it has left): towards the
    # unit it fought, if any of it's left; if not, towards the nearest enemy
    # model ending within Engagement Range, or onto an objective (each model
    # that moves ending closer to one, and one at least touching one).
    fight = consolidating(game)
    if fight is None or fight.unit_id != unit.id:
        raise _bad_request("it isn't that unit's turn to consolidate")
    models, bases = deployment.unit_bases(
        unit, placement, deployment.models_on_battlefield(game, unit)
    )
    start = _bases(game, unit)
    enemies = _enemy_bases(game, unit)
    target = _target(game, fight)
    physical = deployment.physical_problems(
        game, models, bases, deployment.placed_bases(game, unit)
    )

    def result_of(per_model: dict[int, list[str]], unit_problem: str | None) -> Placement:
        result = deployment.summarise(
            models, {i: per_model[i] + physical[i] for i in physical}
        )
        if unit_problem:
            result.problems.append(unit_problem)
        return result

    # Towards the enemy: the unit it fought, or (if that's gone) the nearest.
    towards = list(_bases(game, target).values()) if target is not None else enemies
    name = target.faction_unit.name if target is not None else "the nearest enemy model"
    engaging = result_of(
        _towards(models, start, bases, lambda b: _nearest(b, towards), name),
        None
        if any(_nearest(b, enemies) <= ENGAGEMENT_RANGE + TOLERANCE for b in bases.values())
        else "The unit must end within Engagement Range of an enemy unit",
    )
    objectives = objective_areas(game)
    if engaging.valid or target is not None or not objectives:
        return engaging

    # Or onto an objective.
    def to_objective(base: Base) -> float:
        return min(deployment.distance_to_polygon(base, area) for area in objectives)

    onto_objective = result_of(
        _towards(models, start, bases, to_objective, "the nearest objective"),
        None
        if any(to_objective(b) <= TOLERANCE for b in bases.values())
        else "No model ends on an objective",
    )
    if onto_objective.valid:
        return onto_objective
    # Neither: say what consolidating towards the enemy needs, and that an
    # objective would do instead.
    engaging.problems.append("(Or it can end on an objective, each model that moves closer to one)")
    return engaging


def consolidate(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # Moves the unit, if it can consolidate like that.
    result = check_consolidation(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't consolidate like that: " + "; ".join(result.problems))
    placed = deployment.positions(game)
    for unit_model_id, (x, y, rotation) in placement.items():
        position = placed[unit_model_id]
        position.x, position.y, position.rotation = x, y, rotation
    consolidating(game).consolidation = GameUnitConsolidation(moved=True)


def skip_consolidation(game: Game, unit: Unit) -> None:
    fight = consolidating(game)
    if fight is None or fight.unit_id != unit.id:
        raise _bad_request("it isn't that unit's turn to consolidate")
    fight.consolidation = GameUnitConsolidation(moved=False)
