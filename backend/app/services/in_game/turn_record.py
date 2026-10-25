from __future__ import annotations

from app.models import (
    Game,
    GameKillOnObjective,
    GameModelDestroyed,
    GameTurnStartControl,
    GameTurnStartInArea,
    GameTurnStartOnObjective,
    Unit,
    UnitModel,
)
from app.services.in_game import deployment

# What happened each turn, for missions to score from:
#
# - Each model destroyed on the battlefield: when (battle round, whose turn,
#   phase), its unit, the unit whose attacks destroyed it (if any), and
#   whether it was the last of its unit on the battlefield - its unit was
#   destroyed (and if so, whether the unit that destroyed it was within range
#   of an objective then). Units destroyed off the battlefield (Strategic
#   Reserves that never arrived) aren't here: they're not kills.
# - At the start of each turn: who controlled each objective, which units
#   were within range of which objectives (a model on one of its terrain
#   areas, as for controlling it - see app/services/in_game/objectives.py),
#   and which were within which terrain areas.


def _when(game: Game) -> dict:
    return {"battle_round": game.battle_round, "turn_seat": game.turn_seat}


# --- destroyed ---


def record_destruction(
    game: Game, unit_model: UnitModel, destroyed_by: Unit | None = None
) -> None:
    # The model has just been destroyed (and taken off the battlefield).
    unit = deployment.find_unit(game, unit_model.unit_id)
    unit_destroyed = not deployment.models_on_battlefield(game, unit)
    record = GameModelDestroyed(
        **_when(game),
        phase=game.phase,
        unit_id=unit.id,
        unit_model_id=unit_model.id,
        destroyed_by_unit_id=destroyed_by.id if destroyed_by else None,
        unit_destroyed=unit_destroyed,
    )
    game.models_destroyed.append(record)
    if unit_destroyed:
        # (Imported here: mission_state imports regions, objectives...)
        from app.services.in_game import mission_state

        mission_state.unit_destroyed_by(game, destroyed_by)
        # Whether the unit that destroyed it was within range of an objective.
        if destroyed_by is not None and deployment.is_deployed(
            destroyed_by, deployment.positions(game)
        ) and mission_state.unit_objectives(game, destroyed_by):
            record.on_objective = GameKillOnObjective()


def _turn(record, battle_round: int, turn_seat: int) -> bool:
    return record.battle_round == battle_round and record.turn_seat == turn_seat


def models_destroyed(game: Game, battle_round: int, turn_seat: int) -> list[GameModelDestroyed]:
    # The models destroyed in that turn.
    return [d for d in game.models_destroyed if _turn(d, battle_round, turn_seat)]


def units_destroyed(game: Game, battle_round: int, turn_seat: int) -> list[GameModelDestroyed]:
    # The units destroyed in that turn (each one's last model's record).
    return [d for d in models_destroyed(game, battle_round, turn_seat) if d.unit_destroyed]


def owner_seat(game: Game, unit_id: int) -> int:
    return deployment.owner(game, deployment.find_unit(game, unit_id)).seat


# --- the start of a turn ---


def snapshot_turn_start(game: Game) -> None:
    # How things stand at the start of this turn: objective control, and
    # where each unit on the battlefield is (once a turn).
    # (Imported here: objectives imports battle_shock, which imports
    # casualties, which imports this module.)
    from app.services.in_game import objectives
    from app.services.in_game.terrain import area_polygon, within

    if any(_turn(c, game.battle_round, game.turn_seat) for c in game.turn_start_control):
        return
    for control in objectives.control(game):
        game.turn_start_control.append(
            GameTurnStartControl(
                **_when(game), objective_id=control.objective.id, controller=control.controller
            )
        )
    layout = game.layout
    if layout is None:
        return
    areas = {a.id: area_polygon(a) for a in layout.areas}
    placed = deployment.positions(game)
    for player in game.players:
        for unit in deployment.deployable_units(player):
            bases = [
                deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
                for m in deployment.models_on_battlefield(game, unit)
            ]
            if not bases:
                continue
            inside = {
                area_id
                for area_id, polygon in areas.items()
                if any(within(base, polygon) for base in bases)
            }
            for area_id in sorted(inside):
                game.turn_start_areas.append(
                    GameTurnStartInArea(**_when(game), unit_id=unit.id, area_id=area_id)
                )
            for objective in layout.objectives:
                if inside & {a.id for a in objective.areas}:
                    game.turn_start_objectives.append(
                        GameTurnStartOnObjective(
                            **_when(game), unit_id=unit.id, objective_id=objective.id
                        )
                    )


def controlled_at_start(game: Game, battle_round: int, turn_seat: int) -> dict[int, int | None]:
    # Who controlled each objective at the start of that turn, by objective id.
    return {
        c.objective_id: c.controller
        for c in game.turn_start_control
        if _turn(c, battle_round, turn_seat)
    }


def started_on_objectives(game: Game, battle_round: int, turn_seat: int) -> dict[int, set[int]]:
    # The objectives each unit was within range of at the start of that turn:
    # {unit id: {objective id}}.
    found: dict[int, set[int]] = {}
    for record in game.turn_start_objectives:
        if _turn(record, battle_round, turn_seat):
            found.setdefault(record.unit_id, set()).add(record.objective_id)
    return found


def started_in_areas(game: Game, battle_round: int, turn_seat: int) -> dict[int, set[int]]:
    # The terrain areas each unit was within at the start of that turn.
    found: dict[int, set[int]] = {}
    for record in game.turn_start_areas:
        if _turn(record, battle_round, turn_seat):
            found.setdefault(record.unit_id, set()).add(record.area_id)
    return found


def previous_turn(game: Game, battle_round: int, turn_seat: int) -> tuple[int, int] | None:
    # The turn before that one (battle round, whose turn), if there was one.
    other = next(p.seat for p in game.players if p.seat != turn_seat)
    if turn_seat == game.first_seat:
        return (battle_round - 1, other) if battle_round > 1 else None
    return battle_round, other
