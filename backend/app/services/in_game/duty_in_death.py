from __future__ import annotations

import random

from app.models import Game, GameLingeringModel, Unit
from app.services.in_game import deployment

# Duty in Death (a stratagem with game action "duty_in_death"): used in the
# fight phase on one of the player's units an enemy unit targets. Then for
# the rest of the phase, each time a model in that unit is destroyed, if the
# unit hasn't fought this phase, roll one D6 (+1 if the Assault Doctrine is
# active for the unit): on a 4+, the model isn't removed from the battlefield
# yet - it lingers, destroyed (it has no wounds left and can't be attacked
# again) but still there, so it fights with its unit. It's removed when its
# unit has fought, or at the end of the phase, whichever comes first.

DUTY_IN_DEATH = "duty_in_death"
LINGERS_ON = 4
ASSAULT_DOCTRINE = "Assault Doctrine"


def _this_phase(game: Game, record) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def active(game: Game, unit: Unit) -> bool:
    # Whether Duty in Death was used on the unit this fight phase.
    if game.phase != "fight":
        return False
    player = deployment.owner(game, unit)
    return any(
        use.stratagem.game_action == DUTY_IN_DEATH
        and use.target_unit_id == unit.id
        and use.phase == "fight"
        and _this_phase(game, use)
        for use in player.stratagem_uses
    )


def lingering(game: Game, unit_model_id: int) -> bool:
    return any(m.unit_model_id == unit_model_id for m in game.lingering_models)


def _assault_doctrine(game: Game, unit: Unit) -> bool:
    # Whether the Assault Doctrine is active for the unit (its army rule's
    # option this round, or one of its own).
    # (Imported here: command_phase imports the casualties module, which
    # imports this.)
    from app.services.in_game import command_phase

    seat = deployment.owner(game, unit).seat
    return ASSAULT_DOCTRINE in command_phase.options_for(game, seat, unit)


def lingers(game: Game, unit: Unit, unit_model, destroyed_by: Unit | None = None) -> bool:
    # A model of the unit has just been destroyed (by `destroyed_by`'s
    # attacks, if given): whether it stays on the battlefield for now
    # (recorded, if so) - Duty in Death is active for its unit, which hasn't
    # fought this phase, and the roll is a 4+.
    # (Imported here: fighting imports the casualties module.)
    from app.services.in_game import fighting

    if not active(game, unit) or fighting.fought(game, unit):
        return False
    roll = random.randint(1, 6) + (1 if _assault_doctrine(game, unit) else 0)
    if roll < LINGERS_ON:
        return False
    game.lingering_models.append(
        GameLingeringModel(
            unit_model_id=unit_model.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            destroyed_by_unit_id=destroyed_by.id if destroyed_by is not None else None,
        )
    )
    return True


def remove(game: Game, unit: Unit | None = None) -> None:
    # Removes the lingering models from the battlefield - the unit's (it has
    # fought), or every one (the end of the phase).
    from app.services.in_game import casualties

    models = {m.id for m in unit.unit_models} if unit is not None else None
    for record in list(game.lingering_models):
        if models is not None and record.unit_model_id not in models:
            continue
        game.lingering_models.remove(record)
        casualties.remove_from_battlefield(
            game, record.unit_model_id, record.destroyed_by_unit_id
        )
