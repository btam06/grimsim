from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.engine.state import Game
from app.models import Unit
from app.services import weapon_profiles
from app.services.in_game import deployment, shooting
from app.services.in_game.deployment import TOLERANCE, gap
from app.services.in_game.shooting import TargetReach

# Shooting in the opponent's turn "as if it were your Shooting phase", at one
# enemy unit (datasheet_abilities REACTIVE_SHOTS) - once a turn for the
# player's units with the ability:
#
# - "arrived" (Hyperspace Hunters): in the opponent's Movement phase, at an
#   enemy unit set up from Reserves this phase within `range` of and visible
#   to it;
# - "shot_friend" (Multi-threat Eliminator): in the opponent's Shooting phase,
#   at an enemy unit that has shot a friendly unit with `keywords` within
#   `range` of the model with it - that model shoots, on its own.
#
# The shot's resolved like any other (see app/routers/games.py); the target
# must be one it could shoot (visible, a weapon in range).

USED = "reactive_shot:"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _config() -> dict:
    from app.seeds import datasheet_abilities

    return datasheet_abilities.REACTIVE_SHOTS


@dataclass
class ReactiveShot:
    unit: Unit
    ability: str
    targets: list[Unit]


def _has(unit: Unit, name: str) -> bool:
    return any(a.name == name for m in unit.unit_models for a in m.model.abilities)


def _used(game: Game, seat: int, name: str) -> bool:
    from app.services.in_game import mission_state

    return any(
        (m.battle_round, m.turn_seat) == (game.battle_round, game.turn_seat)
        for m in mission_state.marked(game, f"{USED}{name}", seat)
    )


def _bases(game: Game, unit: Unit, only: str | None = None) -> list:
    placed = deployment.positions(game)
    return [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in deployment.models_on_battlefield(game, unit)
        if m.id in placed and (only is None or any(a.name == only for a in m.model.abilities))
    ]


def _arrived(game: Game, seat: int) -> list[Unit]:
    # The opponent's units set up from Reserves this phase.
    from app.services.in_game import movement, reinforcements

    return [
        u
        for p in game.players
        if p.seat != seat
        for u in deployment.deployable_units(p)
        if (move := movement.unit_move(game, u)) is not None and move.kind == reinforcements.ARRIVED
    ]


def _shooters_of(game: Game, seat: int, near: list, how: dict) -> list[Unit]:
    # The opponent's units that have shot (this phase) a unit of the player's
    # with the keywords and a model within range of `near`.
    found = []
    for shot in game.unit_shots:
        if (shot.battle_round, shot.turn_seat) != (game.battle_round, game.turn_seat):
            continue
        target = deployment.find_unit(game, shot.target_unit_id)
        if deployment.owner(game, target).seat != seat:
            continue
        keywords = {k.name for m in target.unit_models for k in m.model.keywords}
        if not set(how.get("keywords", ())) <= keywords:
            continue
        if not any(gap(a, b) <= how["range"] + TOLERANCE for a in near for b in _bases(game, target)):
            continue
        shooter = deployment.find_unit(game, shot.unit_id)
        if shooter.id not in {u.id for u in found}:
            found.append(shooter)
    return found


def available(game: Game) -> list[ReactiveShot]:
    # The reactive shots units could take now, at which enemy units.
    from app.seeds.factions.adepta_sororitas.unit_abilities import visible_enemies

    if game.status != "in_progress" or game.turn_seat is None:
        return []
    found = []
    for player in game.players:
        if player.seat == game.turn_seat:
            continue
        for name, how in sorted(_config().items()):
            if _used(game, player.seat, name):
                continue
            phase = "movement" if how["trigger"] == "arrived" else "shooting"
            if game.phase != phase:
                continue
            for unit in deployment.deployable_units(player):
                if not _has(unit, name) or not deployment.models_on_battlefield(game, unit):
                    continue
                from app.services.in_game import movement

                if movement.in_engagement_range(game, unit):
                    continue
                if how["trigger"] == "arrived":
                    seen = {u.id for u in visible_enemies(game, unit, how["range"])}
                    targets = [u for u in _arrived(game, player.seat) if u.id in seen]
                else:
                    targets = _shooters_of(game, player.seat, _bases(game, unit, name), how)
                if targets:
                    found.append(ReactiveShot(unit, name, targets))
    return found


def check(game: Game, unit: Unit, ability: str, target: Unit, weapon_ids: set) -> TargetReach:
    # That the unit can take this reactive shot at the target with those
    # weapons; what it can do to it.
    match = next((s for s in available(game) if s.unit.id == unit.id and s.ability == ability), None)
    if match is None:
        raise _bad_request(f"{unit.label} can't use {ability} now")
    if target.id not in {t.id for t in match.targets}:
        raise _bad_request(f"{ability} can only target the unit that triggered it")
    result = shooting.reach(game, unit, target)
    if not result.visible:
        raise _bad_request("none of its models can see the target")
    if not weapon_ids:
        raise _bad_request("choose at least one weapon to shoot with")
    if (conflict := weapon_profiles.unit_conflict(unit, weapon_ids)) is not None:
        raise _bad_request(conflict)
    usable = {w.id for w in result.weapons if w.in_range}
    if not weapon_ids <= usable:
        raise _bad_request("one or more of those weapons can't reach the target")
    return result


def record(game: Game, unit: Unit, ability: str) -> None:
    from app.services.in_game import mission_state

    mission_state.mark(game, deployment.owner(game, unit).seat, f"{USED}{ability}", unit.id)
