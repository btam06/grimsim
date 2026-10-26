from __future__ import annotations

import random

from fastapi import HTTPException

from app.models import Game, GameSelectedObjective, Unit
from app.models.terrain import TerrainObjective
from app.seeds import factions as faction_seeds
from app.services.in_game import deployment, mission_state, objectives
from app.services.in_game.deployment import TOLERANCE
from app.services.in_game.terrain import area_polygon
from app.services.list_building import enhancements as enhancement_rules

# Objectives players select for their rules. Some detachment rules have their
# player select one objective marker at the start of their Command phase
# (faction OBJECTIVE_SELECTIONS - e.g. Acquisition At Any Cost: their
# Acquisition objective marker); it's theirs until the start of their next
# Command phase, and the phase can't end until it's selected. A stratagem can
# make another objective one of them too, until then (game action
# "extra_selected_objective" - e.g. Infoslave Skull).
#
# In combat, a unit within range of one of its player's selected objectives
# has the selection's position (e.g. ON_ACQUISITION), and an attack against a
# unit within range of one of the attacking player's has its target position
# (TARGET_ON_ACQUISITION) - see app/combat_rules/positions.py.
#
# Some enhancements gain CP at the end of their bearer's Command phase while
# it's within range of one (faction END_OF_COMMAND_CP - e.g. Magos: 1CP on a
# 4+).


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _player(game: Game, seat: int):
    return next(p for p in game.players if p.seat == seat)


def configs(game: Game, seat: int) -> dict[str, dict]:
    # The selections the player's list's detachment rules have them make:
    # {selection name: config}.
    rules = enhancement_rules.list_rules(_player(game, seat).army_list)
    return {
        faction_seeds.OBJECTIVE_SELECTIONS[r.name]["name"]: faction_seeds.OBJECTIVE_SELECTIONS[
            r.name
        ]
        for r in rules
        if r.name in faction_seeds.OBJECTIVE_SELECTIONS
    }


def label(game: Game, objective: TerrainObjective) -> str:
    # How to tell objectives apart: their number in the layout, and kind.
    from app.services.in_game.actions import KIND_LABELS

    number = [o.id for o in objectives.objectives(game)].index(objective.id) + 1
    return f"Objective {number} ({KIND_LABELS.get(objective.kind, 'an objective')})"


def selected(game: Game, seat: int, name: str) -> list[GameSelectedObjective]:
    return [s for s in game.selected_objectives if s.seat == seat and s.name == name]


def objective_ids(game: Game, seat: int, name: str) -> set[int]:
    return {s.objective_id for s in selected(game, seat, name)}


def own_selection(game: Game, seat: int, name: str) -> GameSelectedObjective | None:
    # The rule's own selection (not one a stratagem added).
    return next((s for s in selected(game, seat, name) if not s.extra), None)


def clear(game: Game, seat: int) -> None:
    # The start of the player's Command phase: their selections end.
    for record in [s for s in game.selected_objectives if s.seat == seat]:
        game.selected_objectives.remove(record)


def _objective(game: Game, objective_id: int) -> TerrainObjective:
    found = next((o for o in objectives.objectives(game) if o.id == objective_id), None)
    if found is None:
        raise _bad_request("that isn't one of the battlefield's objectives")
    return found


def select(game: Game, seat: int, name: str, objective_id: int) -> None:
    # The player selects their objective for the rule, in their Command phase
    # (in place of any they selected earlier in it).
    if game.status != "in_progress" or game.phase != "command" or game.turn_seat != seat:
        raise _bad_request("it's selected in its player's Command phase")
    if name not in configs(game, seat):
        raise _bad_request(f"they have no rule that selects an {name} objective")
    _objective(game, objective_id)
    if (current := own_selection(game, seat, name)) is not None:
        game.selected_objectives.remove(current)
    game.selected_objectives.append(
        GameSelectedObjective(
            seat=seat, name=name, objective_id=objective_id, battle_round=game.battle_round
        )
    )


def add_extra(game: Game, seat: int, name: str, objective_id: int) -> None:
    # A stratagem makes the objective one of the player's selected ones too.
    _objective(game, objective_id)
    game.selected_objectives.append(
        GameSelectedObjective(
            seat=seat,
            name=name,
            objective_id=objective_id,
            battle_round=game.battle_round,
            extra=True,
        )
    )


def missing(game: Game) -> list[str]:
    # The selections the player whose turn it is must still make before
    # their Command phase ends.
    seat = game.turn_seat
    if not objectives.objectives(game):
        return []
    return [
        f"their {name} objective marker"
        for name in configs(game, seat)
        if own_selection(game, seat, name) is None
    ]


def unit_within(game: Game, unit: Unit, name: str, seat: int | None = None) -> bool:
    # Whether the unit is within range of one of `seat`'s (by default its own
    # player's) selected objectives.
    seat = deployment.owner(game, unit).seat if seat is None else seat
    ids = objective_ids(game, seat, name)
    if not ids or not deployment.is_deployed(unit, deployment.positions(game)):
        return False
    return any(o.id in ids for o in mission_state.unit_objectives(game, unit))


def attacker_positions(game: Game, unit: Unit, target: Unit) -> list[str]:
    # The attacking unit's positions from its player's selections: within
    # range of one, and its target within range of one.
    seat = deployment.owner(game, unit).seat
    found = []
    for name, config in configs(game, seat).items():
        if config.get("position") and unit_within(game, unit, name):
            found.append(config["position"])
        if config.get("target_position") and unit_within(game, target, name, seat):
            found.append(config["target_position"])
    return found


def defender_positions(game: Game, target: Unit) -> list[str]:
    # The defending unit's: within range of one of its own player's.
    seat = deployment.owner(game, target).seat
    return [
        config["position"]
        for name, config in configs(game, seat).items()
        if config.get("position") and unit_within(game, target, name)
    ]


def within_of_model(game: Game, unit: Unit, keywords: set[str], reach: float) -> list:
    # The objectives within `reach` of one of the unit's models with
    # `keywords` (e.g. Infoslave Skull: within 24" of the TECH-PRIEST model).
    placed = deployment.positions(game)
    bases = [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
        and keywords <= enhancement_rules.model_keywords(unit, m)
    ]
    return [
        o
        for o in objectives.objectives(game)
        if any(
            deployment.distance_to_polygon(b, area_polygon(a)) <= reach + TOLERANCE
            for b in bases
            for a in o.areas
        )
    ]


def end_of_command(game: Game) -> None:
    # The end of the player whose turn it is's Command phase: their
    # enhancements that gain CP then roll, if their bearer's within range of
    # one of their selected objectives.
    player = _player(game, game.turn_seat)
    for unit in deployment.deployable_units(player):
        for unit_model in unit.unit_models:
            enhancement = unit_model.enhancement
            config = faction_seeds.END_OF_COMMAND_CP.get(enhancement.name) if enhancement else None
            if config is None or not unit_within(game, unit, config["within"]):
                continue
            if random.randint(1, 6) >= config["roll"]:
                player.cp += 1
