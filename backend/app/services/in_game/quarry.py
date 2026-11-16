from __future__ import annotations

from fastapi import HTTPException

from app.models import Unit
from app.engine.state import Game
from app.services.in_game import casualties, deployment

# A quarry: at the start of the battle, a unit with an ability in
# datasheet_abilities QUARRIES selects one unit from the opponent's army, and
# its attacks against that unit get the ability's effects until the end of
# the battle (e.g. Focused Hunters: re-roll the Hit roll; Virtue of
# Intolerance: [PRECISION] too). Some let it select a new one once its quarry
# is destroyed, while a model in it still has the wargear (`again_with` - the
# Denuncia oratory).
#
# {ability name: {"effects": (effect keywords), "again_with": wargear name
# or None, "hint": what it does, for the panel}}
#
# A unit's quarry is a marked unit, of kind "quarry:<unit id>" (see
# app/services/in_game/mission_state.py) - ended when it's replaced.
QUARRY = "quarry:"
# `again_with` for an ability that selects a new one whenever its quarry's
# destroyed, needing nothing to.
ALWAYS = "always"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _config() -> dict:
    from app.seeds import datasheet_abilities

    return datasheet_abilities.QUARRIES


def ability_of(unit: Unit) -> str | None:
    # The unit's quarry ability, if it has one. (Usable even embarked within
    # a TRANSPORT: its models, on the battlefield or not.)
    config = _config()
    return next(
        (a.name for m in unit.unit_models for a in m.model.abilities if a.name in config), None
    )


def hint(unit: Unit) -> str:
    name = ability_of(unit)
    return _config()[name].get("hint", "") if name else ""


def _marks(game: Game, unit: Unit) -> list:
    from app.services.in_game import mission_state

    return mission_state.marked(game, f"{QUARRY}{unit.id}")


def quarry_of(game: Game, unit: Unit) -> int | None:
    # The unit's quarry (its id), if it has one.
    marks = _marks(game, unit)
    return marks[-1].unit_id if marks else None


def destroyed(game: Game, unit: Unit) -> bool:
    lost = casualties.damage(game)
    return bool(unit.unit_models) and all(
        m.id in lost and lost[m.id].destroyed for m in unit.unit_models
    )


def reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't select a quarry now, if it can't: at the start of
    # the battle (the first battle round, before it's attacked), or - with
    # the wargear that lets it, still carried - once its quarry's destroyed.
    name = ability_of(unit)
    if name is None:
        return "it has no ability that selects a quarry"
    if game.status != "in_progress":
        return "the battle hasn't started"
    current = quarry_of(game, unit)
    if current is None:
        # (Never selected: a replaced quarry's replacement is its quarry.)
        if game.battle_round == 1:
            return None
        return "its quarry is selected at the start of the battle"
    again_with = _config()[name].get("again_with")
    if again_with is None:
        return "its quarry is selected once, at the start of the battle"
    if not destroyed(game, deployment.find_unit(game, current)):
        return "its quarry hasn't been destroyed"
    if again_with == ALWAYS:
        # (A new one each time it's destroyed - e.g. Methodical Destruction.)
        return None
    lost = casualties.damage(game)
    if not any(
        g.name == again_with
        for m in unit.unit_models
        if not (m.id in lost and lost[m.id].destroyed)
        for g in m.wargear
    ):
        return f"its quarry's been destroyed, and it has no {again_with} to select another"
    return None


def targets(game: Game, unit: Unit) -> list[Unit]:
    # Any unit from the opponent's army, not destroyed.
    if reason(game, unit) is not None:
        return []
    seat = deployment.owner(game, unit).seat
    return [
        u
        for p in game.players
        if p.seat != seat
        for u in deployment.deployable_units(p)
        if not destroyed(game, u)
    ]


def select(game: Game, unit: Unit, target: Unit) -> None:
    from app.services.in_game import mission_state

    if (why := reason(game, unit)) is not None:
        raise _bad_request(f"{unit.label} can't select a quarry: {why}")
    if target.id not in {t.id for t in targets(game, unit)}:
        raise _bad_request("its quarry must be a unit from the opponent's army, not destroyed")
    for mark in _marks(game, unit):
        mark.ended = True
    mission_state.mark(game, deployment.owner(game, unit).seat, f"{QUARRY}{unit.id}", target.id)


def rules(game: Game, attacker: Unit, target: Unit) -> list:
    # The attacker's attacks against its quarry: its ability's effects.
    from app.combat_rules import Rule
    from app.combat_rules.conditions import ALWAYS

    name = ability_of(attacker)
    if name is None or quarry_of(game, attacker) != target.id:
        return []
    return [Rule(conditions=(ALWAYS,), effects=tuple(_config()[name]["effects"]))]
