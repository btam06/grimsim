from __future__ import annotations

from fastapi import HTTPException

from app.models import Game, GameBattleShockTest, Unit, UnitModel
from app.services.in_game import battle_shock, deployment, mission_state
from app.services.in_game.deployment import TOLERANCE, gap

# Rallying: some abilities let their player select a friendly Battle-shocked
# unit with some keywords within a distance of the model with the ability:
# it's no longer Battle-shocked (recorded as a passed test, the ability its
# reason - see app/services/in_game/battle_shock.py). Datasheet abilities
# RALLIES: {ability name: {"keywords": (...), "range": inches,
# "once_per_battle": bool}} - e.g. Servo-skull Uplink ("at the start of any
# phase": it can be used whenever the game is in progress).

# A once-per-battle rally used (kept as a marked unit, never ended - see
# app/services/in_game/mission_state.py).
RALLIED = "rallied"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _config() -> dict:
    from app.seeds import datasheet_abilities

    return datasheet_abilities.RALLIES


def _base(game: Game, unit_model: UnitModel):
    p = deployment.positions(game)[unit_model.id]
    return deployment.base_at(unit_model, p.x, p.y, p.rotation)


def _used(game: Game, unit: Unit) -> bool:
    return any(m.unit_id == unit.id for m in mission_state.marked(game, RALLIED))


def available(game: Game) -> list[tuple[Unit, str, list[Unit]]]:
    # Each unit's rally ability that can be used now, and the units it could
    # rally (either player's).
    if game.status != "in_progress":
        return []
    config = _config()
    placed = deployment.positions(game)
    found = []
    for player in game.players:
        for unit in deployment.deployable_units(player):
            for unit_model in unit.unit_models:
                if unit_model.id not in placed:
                    continue
                for ability in unit_model.model.abilities:
                    how = config.get(ability.name)
                    if how is None or (how.get("once_per_battle") and _used(game, unit)):
                        continue
                    found.append((unit, ability.name, _targets(game, unit_model, player, how)))
    return found


def _targets(game: Game, source: UnitModel, player, how: dict) -> list[Unit]:
    placed = deployment.positions(game)
    base = _base(game, source)
    found = []
    for unit in deployment.deployable_units(player):
        models = [m for m in unit.unit_models if m.id in placed]
        keywords = {k.name for m in models for k in m.model.keywords}
        if not set(how["keywords"]) & keywords or not battle_shock.is_battle_shocked(game, unit):
            continue
        if any(gap(base, _base(game, m)) <= how["range"] + TOLERANCE for m in models):
            found.append(unit)
    return found


def rally(game: Game, unit: Unit, name: str, target: Unit) -> None:
    # The unit's ability rallies the target: it's no longer Battle-shocked.
    found = next((a for a in available(game) if a[0].id == unit.id and a[1] == name), None)
    if found is None:
        raise _bad_request(f"{name} can't be used now")
    if target.id not in {t.id for t in found[2]}:
        how = _config()[name]
        raise _bad_request(
            f'{name} targets a friendly Battle-shocked {" or ".join(how["keywords"])} unit '
            f'within {how["range"]:g}" of the model with it'
        )
    game.battle_shock_tests.append(
        GameBattleShockTest(
            unit_id=target.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            phase=game.phase,
            reason=name,
            modifier=0,
            insane_bravery=False,
            passed=True,
        )
    )
    if _config()[name].get("once_per_battle"):
        mission_state.mark(game, deployment.owner(game, unit).seat, RALLIED, unit.id)
