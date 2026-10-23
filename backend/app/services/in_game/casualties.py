from __future__ import annotations

from app.models import Game, GameModelDamage, Unit
from app.services.in_game import deployment

# Wounds and destroyed models in a game. A model that loses all its wounds is
# destroyed: taken off the battlefield (its position removed), so everything
# that looks at the battlefield (coherency, sight, Engagement Range...) no
# longer sees it, and a unit with none left is gone. Only this game: the
# model stays in its list.


def damage(game: Game) -> dict[int, GameModelDamage]:
    # Each damaged (or destroyed) model's record, by unit model id.
    return {d.unit_model_id: d for d in game.model_damage}


def wounds_remaining(game: Game, unit: Unit) -> dict[int, int]:
    # The wounds each of the unit's models on the battlefield has left, by
    # unit model id (destroyed ones aren't there).
    placed = deployment.positions(game)
    lost = damage(game)
    return {
        m.id: m.model.wounds - (lost[m.id].wounds_lost if m.id in lost else 0)
        for m in unit.unit_models
        if m.id in placed
    }


def _lose(game: Game, unit_model, wounds: int) -> None:
    # The model loses `wounds` (to none left, at most) - and if it has none
    # left, it's destroyed and taken off the battlefield.
    if wounds <= 0:
        return
    record = damage(game).get(unit_model.id)
    if record is None:
        record = GameModelDamage(unit_model_id=unit_model.id, wounds_lost=0, destroyed=False)
        game.model_damage.append(record)
    record.wounds_lost = min(unit_model.model.wounds, record.wounds_lost + wounds)
    if record.wounds_lost >= unit_model.model.wounds:
        record.destroyed = True
        position = deployment.positions(game).get(unit_model.id)
        if position is not None:
            game.model_positions.remove(position)


def apply_attack(
    game: Game,
    attacker: Unit,
    defender: Unit,
    defender_wounds_before: dict[int, int],
    defender_wounds_after: dict[int, int],
    attacker_damage: dict[int, int],
) -> list[int]:
    # Applies an attack's result (see app/services/combat.py): the wounds each
    # defending model lost, and the hazardous wounds each attacking model
    # took. The models destroyed, by unit model id.
    destroyed = []
    for side, losses in (
        (defender, {i: defender_wounds_before[i] - w for i, w in defender_wounds_after.items()}),
        (attacker, attacker_damage),
    ):
        for unit_model in side.unit_models:
            lost = losses.get(unit_model.id, 0)
            if lost <= 0:
                continue
            _lose(game, unit_model, lost)
            if damage(game)[unit_model.id].destroyed:
                destroyed.append(unit_model.id)
    return destroyed
