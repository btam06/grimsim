from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Game, GameObjectiveControl, GameSecuredObjective, Unit, UnitModel
from app.models.terrain import TerrainObjective
from app.services.in_game import battle_shock, deployment
from app.services.in_game.terrain import area_polygon, within

# Objective control. Objectives are terrain areas (see TerrainObjective): a
# model is on an objective if any part of its base is over one of its areas.
# Each player's Objective Control there is the sum of the OC of their models
# on it (see model_oc - rules can change a model's OC, and a Battle-shocked
# unit's models have 0); the player with more controls it, and in a tie
# neither does. Who controls it is determined at the end of each phase and
# turn (14.02), and stays so until the next: control(game) is that; with
# `live`, who would if it were determined now (a preview).
#
# An objective's kind is the layout's: a home objective (the attacker's or
# the defender's), an expansion objective, or a central one.
#
# Some rules secure an objective at a moment of their own (datasheet_abilities
# SECURES_OBJECTIVES - e.g. Raise the Banner: at the end of your Movement
# phase, objectives this unit is controlling; Objective Scouted: at the end of
# your Command phase). A secured objective remains under its player's control
# - even with none of their models there - until their opponent's OC on it is
# greater than theirs at the end of a phase; then it's no longer secured, and
# its control is worked out as usual.

HOME_KINDS = {"attacker": "attacker_home", "defender": "defender_home"}


def model_oc(game: Game, unit_model: UnitModel, shocked: set[int] | None = None) -> int:
    # A model's Objective Control characteristic in this game now: 0 if its
    # unit is Battle-shocked (`shocked`: those units' ids, if worked out
    # already). Other rules that change it go here.
    if shocked is None:
        shocked = battle_shock.battle_shocked_ids(game)
    if unit_model.unit_id in shocked:
        return 0
    return unit_model.model.oc or 0


@dataclass
class ObjectiveControl:
    # One objective: its kind, its terrain areas, each player's total OC on
    # it (by seat), and who controls it (None: no one - a tie).
    objective: TerrainObjective
    oc: dict[int, int] = field(default_factory=dict)
    controller: int | None = None
    # The player who's secured it, if anyone has (and it still is).
    secured_by: int | None = None
    # Who would control it if it were determined now.
    live_controller: int | None = None


def objectives(game: Game) -> list[TerrainObjective]:
    return list(game.layout.objectives) if game.layout is not None else []


def _official(game: Game) -> dict[int, int | None]:
    return {c.objective_id: c.seat for c in game.objective_controls}


def determine(game: Game) -> None:
    # The end of a phase or turn: who controls each objective is determined
    # (14.02).
    live = {c.objective.id: c.controller for c in control(game, live=True)}
    records = {c.objective_id: c for c in game.objective_controls}
    for objective_id, seat in live.items():
        if objective_id in records:
            records[objective_id].seat = seat
        else:
            game.objective_controls.append(
                GameObjectiveControl(objective_id=objective_id, seat=seat)
            )


def control(game: Game, live: bool = False) -> list[ObjectiveControl]:
    # Each objective on the battlefield, each player's OC on it now, and who
    # controls it - as determined at the end of the last phase or turn, or
    # with `live`, as it would be now.
    placed = deployment.positions(game)
    models = [
        (player.seat, unit_model)
        for player in game.players
        for unit in deployment.deployable_units(player)
        for unit_model in unit.unit_models
        if unit_model.id in placed
    ]
    bases = {
        m.id: deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for _, m in models
    }
    shocked = battle_shock.battle_shocked_ids(game)
    official = _official(game)
    found = []
    for objective in objectives(game):
        areas = [area_polygon(a) for a in objective.areas]
        oc = {p.seat: 0 for p in game.players}
        for seat, unit_model in models:
            if any(within(bases[unit_model.id], area) for area in areas):
                oc[seat] += model_oc(game, unit_model, shocked)
        best = max(oc.values(), default=0)
        leaders = [seat for seat, total in oc.items() if total == best]
        controller = leaders[0] if best > 0 and len(leaders) == 1 else None
        holder = secured_by(game, objective.id)
        now = holder if holder is not None else controller
        found.append(
            ObjectiveControl(
                objective=objective,
                oc=oc,
                controller=now if live else official.get(objective.id),
                secured_by=holder,
                live_controller=now,
            )
        )
    return found


def _opponent_oc(oc: dict[int, int], seat: int) -> int:
    return sum(total for s, total in oc.items() if s != seat)


def secured_by(game: Game, objective_id: int) -> int | None:
    # The player who's secured the objective, if anyone has.
    return next(
        (s.seat for s in game.secured_objectives if s.objective_id == objective_id), None
    )


def secure(game: Game, objective_id: int, seat: int) -> None:
    # The player secures the objective (in place of anyone else).
    for existing in [s for s in game.secured_objectives if s.objective_id == objective_id]:
        game.secured_objectives.remove(existing)
    game.secured_objectives.append(GameSecuredObjective(objective_id=objective_id, seat=seat))


def refresh_secured(game: Game) -> None:
    # The end of a phase: secured objectives whose holder's opponent has more
    # OC on them than they do are no longer secured.
    if not game.secured_objectives:
        return
    by_id = {c.objective.id: c for c in control(game, live=True)}
    for record in list(game.secured_objectives):
        current = by_id.get(record.objective_id)
        if current is None or _opponent_oc(current.oc, record.seat) > current.oc.get(
            record.seat, 0
        ):
            game.secured_objectives.remove(record)


def unit_controls(game: Game, unit: Unit, current: ObjectiveControl) -> bool:
    # Whether the unit is controlling the objective: its player controls it,
    # and one of its models is on it.
    seat = deployment.owner(game, unit).seat
    if current.controller != seat:
        return False
    placed = deployment.positions(game)
    areas = [area_polygon(a) for a in current.objective.areas]
    return any(
        any(
            within(deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation), a)
            for a in areas
        )
        for m in unit.unit_models
        if m.id in placed
    )


def secure_at_end_of(game: Game, phase: str) -> None:
    # The end of the turn player's `phase`: their units with an ability that
    # secures objectives then (e.g. Raise the Banner, the Movement phase)
    # secure those they're controlling.
    from app.seeds import datasheet_abilities as datasheet_ability_seeds

    timings = datasheet_ability_seeds.SECURES_OBJECTIVES
    player = next(p for p in game.players if p.seat == game.turn_seat)
    securing = [
        unit
        for unit in deployment.deployable_units(player)
        if any(
            timings.get(a.name) == phase for m in unit.unit_models for a in m.model.abilities
        )
    ]
    if not securing:
        return
    # (Controlling at the end of the phase: as determined then.)
    current = control(game, live=True)
    for unit in securing:
        for objective in current:
            if unit_controls(game, unit, objective):
                secure(game, objective.objective.id, player.seat)


def controlled_by(game: Game, seat: int) -> list[ObjectiveControl]:
    return [c for c in control(game) if c.controller == seat]


def is_home(game: Game, objective: TerrainObjective, seat: int) -> bool:
    # Whether it's the player's own home objective.
    side = "attacker" if seat == game.attacker_seat else "defender"
    return objective.kind == HOME_KINDS[side]


def is_opponents_home(game: Game, objective: TerrainObjective, seat: int) -> bool:
    other = next(p.seat for p in game.players if p.seat != seat)
    return is_home(game, objective, other)


def is_central(objective: TerrainObjective) -> bool:
    return objective.kind == "centre"


def is_expansion(objective: TerrainObjective) -> bool:
    return objective.kind == "expansion"
