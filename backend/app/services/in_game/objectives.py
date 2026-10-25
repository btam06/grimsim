from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Game, UnitModel
from app.models.terrain import TerrainObjective
from app.services.in_game import battle_shock, deployment
from app.services.in_game.terrain import area_polygon, within

# Objective control. Objectives are terrain areas (see TerrainObjective): a
# model is on an objective if any part of its base is over one of its areas.
# Each player's Objective Control there is the sum of the OC of their models
# on it (see model_oc - rules can change a model's OC, and a Battle-shocked
# unit's models have 0); the player with more controls it, and in a tie
# neither does.
#
# An objective's kind is the layout's: a home objective (the attacker's or
# the defender's), an expansion objective, or a central one.

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


def objectives(game: Game) -> list[TerrainObjective]:
    return list(game.layout.objectives) if game.layout is not None else []


def control(game: Game) -> list[ObjectiveControl]:
    # Each objective on the battlefield, and who controls it now.
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
    found = []
    for objective in objectives(game):
        areas = [area_polygon(a) for a in objective.areas]
        oc = {p.seat: 0 for p in game.players}
        for seat, unit_model in models:
            if any(within(bases[unit_model.id], area) for area in areas):
                oc[seat] += model_oc(game, unit_model, shocked)
        best = max(oc.values(), default=0)
        leaders = [seat for seat, total in oc.items() if total == best]
        found.append(
            ObjectiveControl(
                objective=objective,
                oc=oc,
                controller=leaders[0] if best > 0 and len(leaders) == 1 else None,
            )
        )
    return found


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
