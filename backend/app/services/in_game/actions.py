from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.models import Game, GameAction, GameActionUnitTarget, Unit
from app.services.in_game import battle_shock, deployment, mission_state, objectives, regions
from app.services.in_game.terrain import area_polygon

# Actions (16): what a mission can have a unit do. In its turn's Shooting
# phase, a unit of the player whose turn it is can start an action one of
# their mission cards has (their primary mission's, or an active
# secondary's - e.g. Cleanse, Plunder, Decoy), on an objective, terrain area
# or enemy unit the action allows - unless it isn't on the battlefield, is an
# AIRCRAFT/FORTIFICATION unit, is Battle-shocked, has an OC of 0, is engaged
# (unless it's TITANIC), Advanced or Fell Back this turn, or started another
# action this turn.
#
# A unit that's started one can't shoot (unless it's TITANIC) or declare a
# charge for the rest of the turn (see `blocks` - where rules that let it act
# and shoot will go; and `can_act`, for acting after Advancing). If it makes
# a move (other than a pile-in or consolidation move), leaves the
# battlefield or becomes Battle-shocked before its action completes, the
# action fails (see `check_started`). An action completes
# straight away, or at the end of the turn if its condition is met then
# (otherwise it fails): its unit controls its objective (within range of it,
# and its player controls it), or no enemy units are within its terrain
# area. What completing does (placing an operation marker, a sensor sweep...)
# is in `complete`; missions score what was completed (see
# app/services/in_game/mission_cards.py).


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


@dataclass(frozen=True)
class Action:
    # An action: the mission cards that have it; what it's done on
    # ("objective", "area" or "unit"); when it completes ("immediately" or
    # "end_of_turn") and on what condition ("controls" its objective, or the
    # terrain area is "clear" of enemy units); its use limit (once a turn for
    # the player, and whether each unit doing it this phase needs a different
    # target); the first battle round it can be done; and what completing it
    # does ("marker": place an operation marker on its target; "remove":
    # remove one - a sensor sweep; "surveil": mark its enemy unit).
    name: str
    cards: tuple[str, ...]
    target: str
    completes: str
    condition: str = "controls"
    once_per_turn: bool = False
    different_targets: bool = False
    from_round: int = 1
    effect: str | None = None


ACTIONS = {
    a.name: a
    for a in (
        # Secondaries.
        Action("Cleanse", ("Cleanse",), "objective", "end_of_turn", different_targets=True),
        Action("Plunder", ("Plunder",), "area", "immediately", once_per_turn=True),
        # Primaries (the backs of their cards).
        Action(
            "Booby Trap", ("Death Trap",), "area", "immediately",
            different_targets=True, effect="marker",
        ),
        Action(
            "Sensor Sweep", ("Locate and Deny", "Extract Relic"), "objective", "end_of_turn",
            once_per_turn=True, effect="remove",
        ),
        Action(
            "Decoy", ("Smoke and Mirrors",), "objective", "end_of_turn",
            different_targets=True, effect="marker",
        ),
        Action("Sabotage", ("Sabotage",), "objective", "end_of_turn", different_targets=True),
        Action("Secure Asset", ("Secure Asset",), "objective", "end_of_turn", once_per_turn=True),
        Action(
            "Vanguard Operation", ("Vanguard Operation",), "area", "end_of_turn",
            condition="clear", once_per_turn=True,
        ),
        Action(
            "Maintain Control", ("Vital Link",), "objective", "end_of_turn",
            once_per_turn=True, effect="marker",
        ),
        Action(
            "Extract Intelligence", ("Gather Intel",), "objective", "end_of_turn",
            different_targets=True, from_round=2, effect="marker",
        ),
        Action("Surveil the Foe", ("Surveil the Foe",), "unit", "immediately", effect="surveil"),
        Action(
            "Triangulate", ("Triangulation",), "objective", "end_of_turn",
            once_per_turn=True, from_round=2, effect="marker",
        ),
    )
}

# Surveil the Foe: an enemy unit within this of the unit, and visible to it.
SURVEIL_RANGE = 18.0


def _this_turn(game: Game, record) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def unit_action(game: Game, unit: Unit) -> GameAction | None:
    # The action the unit started this turn, if any.
    return next((a for a in game.actions if a.unit_id == unit.id and _this_turn(game, a)), None)


# The moves a unit can make without failing the action it's started.
MOVES_KEEPING_ACTIONS = ("pile_in", "consolidate")


def _keywords(unit: Unit) -> set[str]:
    return {k.name for m in unit.unit_models for k in m.model.keywords}


def blocks(game: Game, unit: Unit, what: str) -> str | None:
    # Why the unit's action stops it doing `what` ("shoot" - unless it's
    # TITANIC - or "charge") this turn, or None. (Rules that let a unit act
    # and still shoot, say, would let it here.)
    action = unit_action(game, unit)
    if action is None:
        return None
    if what == "shoot" and "TITANIC" in _keywords(unit):
        return None
    return f"it started an action this turn ({action.action})"


def moved(game: Game, unit: Unit) -> None:
    # The unit made a move: an action it started that hasn't completed fails.
    for record in game.actions:
        if record.status == "started" and record.unit_id == unit.id:
            record.status = "failed"


def _act_after(unit: Unit) -> set[str]:
    # The moves the unit's abilities let it start an action after
    # (datasheet_abilities ACTION_AFTER).
    from app.seeds import datasheet_abilities

    config = datasheet_abilities.ACTION_AFTER
    return {
        move for m in unit.unit_models for a in m.model.abilities for move in config.get(a.name, ())
    }


def can_act(game: Game, unit: Unit) -> str | None:
    # Why the unit can't start an action now (whatever the action), or None.
    # (Imported here: shooting imports this module.)
    from app.services.in_game import movement, shooting

    if game.status != "in_progress" or game.phase != "shooting":
        return "actions are started in the Shooting phase"
    if deployment.owner(game, unit).seat != game.turn_seat:
        return "only the player whose turn it is can start actions"
    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if unit_action(game, unit) is not None:
        return "it has already started an action this turn"
    keywords = _keywords(unit)
    if keywords & {"AIRCRAFT", "FORTIFICATION"}:
        return "AIRCRAFT and FORTIFICATION units can't start actions"
    if battle_shock.is_battle_shocked(game, unit):
        return "it's Battle-shocked"
    if all(
        objectives.model_oc(game, m) <= 0 for m in deployment.models_on_battlefield(game, unit)
    ):
        return "its OC is 0"
    status = shooting.move_status(game, unit)
    # (An ability can let it anyway - e.g. Flexible Asset.)
    if status.advanced and "advanced" not in _act_after(unit):
        return "it Advanced this turn"
    if status.fell_back and "fell_back" not in _act_after(unit):
        return "it Fell Back this turn"
    if movement.in_engagement_range(game, unit) and "TITANIC" not in keywords:
        return "it's engaged"
    if battle_shock.is_battle_shocked(game, unit):
        return "it's Battle-shocked"
    return None


def _invalid(game: Game, unit: Unit) -> bool:
    # Whether a unit can no longer complete an action it started: it's left
    # the battlefield (or been destroyed), or it's Battle-shocked. (Making a
    # move fails it too - see `moved`.)
    return not deployment.is_deployed(
        unit, deployment.positions(game)
    ) or battle_shock.is_battle_shocked(game, unit)


def check_started(game: Game) -> None:
    # Actions waiting to complete whose unit can no longer complete them
    # fail (checked whenever that might have changed: a unit moved, a
    # Battle-shock test failed, the end of the turn).
    for record in game.actions:
        if record.status == "started" and _invalid(
            game, deployment.find_unit(game, record.unit_id)
        ):
            record.status = "failed"


def card_for(game: Game, seat: int, action: Action) -> str:
    # Which of the action's mission cards the player has.
    player = next(p for p in game.players if p.seat == seat)
    held = {s.mission.name for s in player.secondaries if s.status == "active"}
    if player.primary_mission is not None:
        held.add(player.primary_mission.name)
    return next((c for c in action.cards if c in held), action.cards[0])


def _has_card(game: Game, seat: int, cards: tuple[str, ...]) -> bool:
    player = next(p for p in game.players if p.seat == seat)
    mission = player.primary_mission
    return any(s.status == "active" and s.mission.name in cards for s in player.secondaries) or (
        mission is not None and mission.name in cards
    )


@dataclass
class Target:
    kind: str  # "objective", "area" or "unit"
    id: int
    label: str


KIND_LABELS = {
    "attacker_home": "the attacker's home objective",
    "defender_home": "the defender's home objective",
    "expansion": "an expansion objective",
    "centre": "a central objective",
}


def _objective_label(objective) -> str:
    return KIND_LABELS.get(objective.kind, "an objective")


def _area_label(game: Game, area) -> str:
    objective = next(
        (o for o in game.layout.objectives if area.id in {a.id for a in o.areas}), None
    )
    name = area.shape.name if area.shape else "terrain area"
    return f"{name}" + (f" ({_objective_label(objective)})" if objective else "")


def _taken(game: Game, action: Action, kind: str) -> set[int]:
    # The targets other units already chose for this action this phase (for
    # an action each unit must do on a different one).
    if not action.different_targets:
        return set()
    return {
        (a.objective_id if kind == "objective" else a.area_id)
        for a in game.actions
        if a.action == action.name and _this_turn(game, a)
    }


def targets(game: Game, unit: Unit, action: Action) -> list[Target]:
    # What the unit could do the action on now.
    layout = game.layout
    if layout is None:
        return []
    seat = deployment.owner(game, unit).seat
    if action.target == "unit":
        return _surveil_targets(game, unit, seat)
    if action.target == "objective":
        taken = _taken(game, action, "objective")
        mine = mission_state.objectives_with_markers(game, seat)
        found = []
        for o in mission_state.unit_objectives(game, unit):
            if o.id in taken or objectives.is_home(game, o, seat):
                continue
            if action.name in ("Sensor Sweep", "Maintain Control") and not objectives.is_central(o):
                continue
            if action.name == "Decoy" and o.id in mission_state.objectives_with_markers(
                game, seat, "Decoy"
            ):
                continue
            if action.name == "Extract Intelligence" and o.id in mine:
                continue
            found.append(Target("objective", o.id, _objective_label(o)))
        return found
    taken = _taken(game, action, "area")
    territory = regions.territory(game, seat)
    opponents = regions.territory(game, next(p.seat for p in game.players if p.seat != seat))
    zone = regions.deployment_zone(game, seat)
    trapped = {
        m.area_id for m in mission_state.markers(game, seat) if m.source == "Booby Trap"
    }
    home_areas = {
        a.id for o in layout.objectives if objectives.is_home(game, o, seat) for a in o.areas
    }
    objective_areas = {a.id for o in layout.objectives for a in o.areas}
    found = []
    for a in mission_state.unit_areas(game, unit):
        if a.id in taken:
            continue
        if action.name == "Plunder" and mission_state.area_within(game, a, territory):
            continue
        if action.name == "Vanguard Operation" and not mission_state.area_within(
            game, a, opponents
        ):
            continue
        if action.name == "Booby Trap":
            on_objective = a.id in objective_areas and a.id not in home_areas
            if a.id in trapped or not (
                on_objective or not mission_state.area_within(game, a, zone)
            ):
                continue
        found.append(Target("area", a.id, _area_label(game, a)))
    return found


def _surveil_targets(game: Game, unit: Unit, seat: int) -> list[Target]:
    # Enemy units within 18" of the unit and visible to it, not surveilled
    # this turn.
    from app.services.in_game import shooting

    surveilled = {m.unit_id for m in mission_state.marked(game, "surveilled")}
    found = []
    for enemy in shooting.enemy_units(game, unit):
        if enemy.id in surveilled:
            continue
        reach = shooting.reach(game, unit, enemy)
        if reach.visible and reach.distance is not None and reach.distance <= SURVEIL_RANGE:
            found.append(Target("unit", enemy.id, enemy.faction_unit.name))
    return found


@dataclass
class Available:
    # An action the unit's player has: what it could be done on, or why the
    # unit can't do it now.
    action: Action
    targets: list[Target]
    reason: str | None = None


def _reason(game: Game, action: Action) -> str | None:
    # Why the action can't be started now, by anyone (its use limit, its
    # battle round, its restriction), or None.
    if game.battle_round < action.from_round:
        return f"it can't be done before battle round {action.from_round}"
    if action.once_per_turn and any(
        a.action == action.name and _this_turn(game, a) for a in game.actions
    ):
        return f"{action.name} has already been done this turn"
    if action.name == "Sensor Sweep" and len(mission_state.markers(game)) <= 1:
        return "there's only one operation marker (or none) on the battlefield"
    return None


def available(game: Game, unit: Unit) -> list[Available]:
    # The actions the unit's player's mission cards have, for this unit now.
    seat = deployment.owner(game, unit).seat
    found = []
    unit_reason = can_act(game, unit)
    for action in ACTIONS.values():
        if not _has_card(game, seat, action.cards):
            continue
        reason = unit_reason or _reason(game, action)
        options = targets(game, unit, action) if reason is None else []
        if reason is None and not options:
            reason = {
                "objective": "it isn't within range of an objective it can do it on",
                "area": "it isn't within a terrain area it can do it in",
                "unit": 'no enemy unit it can see within 18" (not surveilled yet)',
            }[action.target]
        found.append(Available(action, options, reason))
    return found


def start(game: Game, unit: Unit, name: str, target_id: int) -> GameAction:
    # The unit starts the action on that objective, terrain area or enemy
    # unit (done at once, if it completes immediately).
    action = ACTIONS.get(name)
    if action is None:
        raise _bad_request(f"there's no action {name!r}")
    option = next((a for a in available(game, unit) if a.action.name == name), None)
    if option is None:
        raise _bad_request(f"none of that player's mission cards has the {name} action")
    if option.reason:
        raise _bad_request(f"it can't do {name}: {option.reason}")
    if target_id not in {t.id for t in option.targets}:
        raise _bad_request(f"it can't do {name} there")
    record = GameAction(
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        phase=game.phase,
        unit_id=unit.id,
        action=name,
        objective_id=target_id if action.target == "objective" else None,
        area_id=target_id if action.target == "area" else None,
        status="started",
    )
    if action.target == "unit":
        record.unit_target = GameActionUnitTarget(unit_id=target_id)
    game.actions.append(record)
    if action.completes == "immediately":
        complete(game, record)
    return record


def complete(game: Game, record: GameAction) -> None:
    # The action completes: what it does.
    action = ACTIONS[record.action]
    seat = deployment.owner(game, deployment.find_unit(game, record.unit_id)).seat
    record.status = "completed"
    if action.effect == "marker":
        mission_state.place_marker(
            game, seat, action.name, objective_id=record.objective_id, area_id=record.area_id
        )
    elif action.effect == "remove":
        mission_state.prompt_sensor_sweep(game, seat, record.id)
    elif action.effect == "surveil":
        mission_state.mark(game, seat, "surveilled", record.target_unit_id)


def end_of_turn(game: Game) -> None:
    # Actions that complete at the end of the turn: completed if their
    # condition is met (and their unit can still complete them), failed
    # otherwise.
    check_started(game)
    control = {c.objective.id: c for c in objectives.control(game)}
    for record in game.actions:
        if record.status != "started" or not _this_turn(game, record):
            continue
        action = ACTIONS[record.action]
        unit = deployment.find_unit(game, record.unit_id)
        seat = deployment.owner(game, unit).seat
        if action.condition == "clear":
            area = next(a for a in game.layout.areas if a.id == record.area_id)
            enemy = next(p for p in game.players if p.seat != seat)
            placed = deployment.positions(game)
            met = not any(
                regions.unit_within(game, u, area_polygon(area))
                for u in deployment.deployable_units(enemy)
                if deployment.is_deployed(u, placed)
            )
        else:
            held = control.get(record.objective_id)
            met = (
                held is not None
                and held.controller == seat
                and any(
                    regions.unit_within(game, unit, area_polygon(a)) for a in held.objective.areas
                )
            )
        if met:
            complete(game, record)
        else:
            record.status = "failed"


def completed(game: Game, seat: int, name: str, battle_round: int, turn_seat: int) -> list:
    # The player's actions of that name completed in that turn.
    return [
        a
        for a in game.actions
        if a.action == name
        and a.status == "completed"
        and a.battle_round == battle_round
        and a.turn_seat == turn_seat
        and deployment.owner(game, deployment.find_unit(game, a.unit_id)).seat == seat
    ]
