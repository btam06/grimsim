from __future__ import annotations

from fastapi import HTTPException

from app.combat_rules import Rule
from app.combat_rules.conditions import ALWAYS
from app.combat_rules.effects import FEEL_NO_PAIN_5
from app.models import Game, GameRepair, Unit, UnitModel
from app.services.combat import roll_dice_faces
from app.services.in_game import casualties, deployment
from app.services.in_game.deployment import TOLERANCE, gap

# Repairing in the Command phase: some abilities let their player, in their
# Command phase, select one friendly model with some keywords within a
# distance of the model with the ability: it regains lost wounds - and if
# it's a VEHICLE, has a Feel No Pain until the start of their next Command
# phase. Each model can be repaired once a Command phase, and each ability
# used once (datasheet_abilities REPAIRS: {ability name: {"keywords": (...),
# "range": inches, "heal": dice, "vehicle_feel_no_pain": n}} - e.g.
# Omnissiah's Blessing).

FEEL_NO_PAIN_EFFECTS = {5: FEEL_NO_PAIN_5}


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _config() -> dict:
    from app.seeds import datasheet_abilities

    return datasheet_abilities.REPAIRS


def _base(game: Game, unit_model: UnitModel):
    p = deployment.positions(game)[unit_model.id]
    return deployment.base_at(unit_model, p.x, p.y, p.rotation)


def _this_phase(game: Game, record: GameRepair) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def available(game: Game) -> list[tuple[Unit, str, list[UnitModel]]]:
    # The repair abilities the player whose turn it is can use now (in their
    # Command phase), and the models each could repair.
    if game.status != "in_progress" or game.phase != "command":
        return []
    config = _config()
    player = next(p for p in game.players if p.seat == game.turn_seat)
    placed = deployment.positions(game)
    used = {r.source_unit_id for r in game.repairs if _this_phase(game, r)}
    repaired = {r.unit_model_id for r in game.repairs if _this_phase(game, r)}
    found = []
    for unit in deployment.deployable_units(player):
        if unit.id in used:
            continue
        for unit_model in unit.unit_models:
            if unit_model.id not in placed:
                continue
            for ability in unit_model.model.abilities:
                how = config.get(ability.name)
                if how is None:
                    continue
                base = _base(game, unit_model)
                targets = [
                    m
                    for other in deployment.deployable_units(player)
                    for m in other.unit_models
                    if m.id in placed
                    and m.id not in repaired
                    and set(how["keywords"]) <= {k.name for k in m.model.keywords}
                    and gap(base, _base(game, m)) <= how["range"] + TOLERANCE
                ]
                found.append((unit, ability.name, targets))
    return found


def repair(game: Game, unit: Unit, name: str, unit_model_id: int) -> int:
    # The unit's ability repairs the model: the wounds it regained.
    found = next((a for a in available(game) if a[0].id == unit.id and a[1] == name), None)
    if found is None:
        raise _bad_request(f"{name} is used once in its player's Command phase")
    target = next((m for m in found[2] if m.id == unit_model_id), None)
    if target is None:
        how = _config()[name]
        raise _bad_request(
            f'{name} targets a friendly {" ".join(how["keywords"])} model within '
            f'{how["range"]:g}" of the model with it, once a Command phase'
        )
    how = _config()[name]
    rolled, _ = roll_dice_faces(how["heal"])
    record = casualties.damage(game).get(target.id)
    healed = 0
    if record is not None and not record.destroyed:
        healed = min(rolled, record.wounds_lost)
        record.wounds_lost -= healed
    vehicle = "VEHICLE" in {k.name for k in target.model.keywords}
    game.repairs.append(
        GameRepair(
            source_unit_id=unit.id,
            unit_model_id=target.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            feel_no_pain=how.get("vehicle_feel_no_pain") if vehicle else None,
        )
    )
    return healed


def _lasting(game: Game, record: GameRepair) -> bool:
    # Whether a repair's Feel No Pain still lasts: until the start of its
    # player's next Command phase.
    if game.battle_round == record.battle_round:
        return True
    return game.battle_round == record.battle_round + 1 and (
        game.turn_seat != record.turn_seat
    )


def model_rules(game: Game, unit: Unit) -> dict[int, list[Rule]]:
    # The Feel No Pain its repairs give the unit's models now, as rules for
    # attacks against them ({unit model id: [Rule]}).
    found: dict[int, list[Rule]] = {}
    models = {m.id for m in unit.unit_models}
    for record in game.repairs:
        if record.unit_model_id in models and record.feel_no_pain and _lasting(game, record):
            effect = FEEL_NO_PAIN_EFFECTS.get(record.feel_no_pain)
            if effect:
                found.setdefault(record.unit_model_id, []).append(
                    Rule(conditions=(ALWAYS,), effects=(effect,), side="defender")
                )
    return found
