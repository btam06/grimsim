from __future__ import annotations

from app.models import Game, Unit
from app.seeds.factions.adeptus_mechanicus.conditions import VENGEANCE
from app.services.in_game import deployment, mission_state
from app.services.in_game.deployment import TOLERANCE, gap

# Vengeance for the Omnissiah (a Tech-priest Enginseer): if a friendly
# ADEPTUS MECHANICUS VEHICLE model is destroyed within 12" of the model with
# it, until the end of the battle its Omnissian axe has an Attacks
# characteristic of 6 - in combat, the VENGEANCE position (see its rule in
# datasheet_abilities.py), set for its unit in a game (see
# app/routers/games.py).

NAME = "Vengeance for the Omnissiah"
RANGE = 12.0
VICTIM_KEYWORDS = {"ADEPTUS MECHANICUS", "VEHICLE"}


def _avenging(game: Game, unit: Unit) -> bool:
    return any(m.unit_id == unit.id for m in mission_state.marked(game, VENGEANCE))


def active(game: Game, unit: Unit) -> bool:
    # Whether the unit has its vengeance (for the rest of the battle).
    return _avenging(game, unit)


def model_destroyed(game: Game, unit: Unit, unit_model, base) -> None:
    # A model of the unit is about to be taken off the battlefield, at `base`:
    # if it's an ADEPTUS MECHANICUS VEHICLE, its player's units with the
    # ability within 12" of it have their vengeance.
    if not VICTIM_KEYWORDS <= {k.name for k in unit_model.model.keywords}:
        return
    player = deployment.owner(game, unit)
    placed = deployment.positions(game)
    for other in deployment.deployable_units(player):
        if other.id == unit.id or _avenging(game, other):
            continue
        for m in other.unit_models:
            if m.id not in placed or not any(a.name == NAME for a in m.model.abilities):
                continue
            p = placed[m.id]
            if gap(base, deployment.base_at(m, p.x, p.y, p.rotation)) <= RANGE + TOLERANCE:
                mission_state.mark(game, player.seat, VENGEANCE, other.id)
                break
