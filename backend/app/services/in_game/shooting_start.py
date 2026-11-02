from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException

from app.models import Unit, UnitModel
from app.engine.state import Game
from app.services import dice
from app.services.combat import roll_dice_faces
from app.services.in_game import casualties, deployment, mission_state
from app.services.in_game.deployment import TOLERANCE, gap

# The start of a phase - their Shooting phase, unless it says otherwise: some
# abilities have their player, before anything else happens in it, select one
# enemy unit with some keywords within a distance of the model with the
# ability (or, `from_unit`, of its unit) and roll one D6 - on a high enough
# roll, that unit suffers mortal wounds (datasheet_abilities
# START_OF_SHOOTING: {ability name: {"target_keywords": (...), "range":
# inches, "roll": the D6 needed, "mortal_wounds": dice, "phase": "shooting"
# or "fight", "from_unit": bool, "heal_self": bool, "melee_skill": n}} -
# e.g. Secutor of Olympus: an enemy VEHICLE unit within 12", 2+, D3+1).
# `heal_self`: the model regains up to that many lost wounds (Matter
# Absorption); `melee_skill`: the target's melee weapons' Weapon Skill is
# worse by that much until the end of the phase (Data-spike). At the start
# of the Fight phase, either player can use theirs. Once a phase each.

# An ability used this phase (kept as a marked unit - see
# app/services/in_game/mission_state.py).
USED = "start_of_shooting"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


@dataclass
class StartOfShooting:
    unit: Unit
    model: UnitModel
    name: str
    how: dict
    targets: list[Unit] = field(default_factory=list)


@dataclass
class Result:
    roll: int
    wounds: int = 0
    destroyed: list[int] = field(default_factory=list)


def _config() -> dict:
    from app.seeds import datasheet_abilities

    return datasheet_abilities.START_OF_SHOOTING


def _used(game: Game, unit: Unit) -> bool:
    return any(
        m.unit_id == unit.id
        and m.battle_round == game.battle_round
        and m.turn_seat == game.turn_seat
        for m in mission_state.marked(game, USED)
    )


def is_start(game: Game) -> bool:
    # Whether it's the start of the player whose turn it is's Shooting phase
    # (none of their units has shot yet) - or of the Fight phase (no unit has
    # fought yet).
    # (Imported here: shooting imports what imports this.)
    from app.services.in_game import fighting, shooting

    if game.status != "in_progress":
        return False
    if game.phase == "fight":
        return not any(
            fighting.fought(game, u)
            for p in game.players
            for u in deployment.deployable_units(p)
        )
    if not shooting.is_shooting_phase(game):
        return False
    player = next(p for p in game.players if p.seat == game.turn_seat)
    return not any(shooting.unit_shot(game, u) for u in deployment.deployable_units(player))


def _base(game: Game, unit_model: UnitModel):
    p = deployment.positions(game)[unit_model.id]
    return deployment.base_at(unit_model, p.x, p.y, p.rotation)


def _targets(game: Game, unit: Unit, model: UnitModel, seat: int, how: dict) -> list[Unit]:
    placed = deployment.positions(game)
    sources = (
        [_base(game, m) for m in unit.unit_models if m.id in placed]
        if how.get("from_unit")
        else [_base(game, model)]
    )
    found = []
    for player in game.players:
        if player.seat == seat:
            continue
        for unit in deployment.deployable_units(player):
            models = [m for m in unit.unit_models if m.id in placed]
            keywords = {k.name for m in models for k in m.model.keywords}
            if not keywords & set(how["target_keywords"]):
                continue
            if any(
                gap(source, _base(game, m)) <= how["range"] + TOLERANCE
                for source in sources
                for m in models
            ):
                found.append(unit)
    return found


def available(game: Game) -> list[StartOfShooting]:
    # The abilities usable now (the player whose turn it is's, at the start
    # of their Shooting phase; either player's, at the start of the Fight
    # phase), with their possible targets.
    if not is_start(game):
        return []
    config = _config()
    players = [
        p for p in game.players if game.phase == "fight" or p.seat == game.turn_seat
    ]
    placed = deployment.positions(game)
    found = []
    for player in players:
        for unit in deployment.deployable_units(player):
            if _used(game, unit):
                continue
            for unit_model in unit.unit_models:
                if unit_model.id not in placed:
                    continue
                for ability in unit_model.model.abilities:
                    how = config.get(ability.name)
                    if how is None or how.get("phase", "shooting") != game.phase:
                        continue
                    found.append(
                        StartOfShooting(
                            unit, unit_model, ability.name, how,
                            _targets(game, unit, unit_model, player.seat, how),
                        )
                    )
    return found


def use(game: Game, unit: Unit, name: str, target: Unit) -> Result:
    # Uses the unit's ability on the target: rolls the D6, and on a high
    # enough roll inflicts the mortal wounds.
    found = next((a for a in available(game) if a.unit.id == unit.id and a.name == name), None)
    if found is None:
        phase = _config().get(name, {}).get("phase", "shooting")
        raise _bad_request(f"{name} is used at the start of the {phase} phase")
    if target.id not in {t.id for t in found.targets}:
        keywords = " or ".join(found.how["target_keywords"])
        raise _bad_request(
            f'{name} targets an enemy {keywords} unit within {found.how["range"]:g}" of the '
            "model with it"
        )
    mission_state.mark(game, deployment.owner(game, unit).seat, USED, unit.id)
    result = Result(roll=dice.randint(1, 6))
    if result.roll >= found.how["roll"]:
        result.wounds, _ = roll_dice_faces(found.how["mortal_wounds"])
        result.destroyed = casualties.mortal_wounds(game, target, result.wounds, unit)
        if found.how.get("heal_self"):
            # The model regains up to that many lost wounds.
            record = casualties.damage(game).get(found.model.id)
            if record is not None and not record.destroyed:
                record.wounds_lost -= min(result.wounds, record.wounds_lost)
        if found.how.get("melee_skill") and deployment.models_on_battlefield(game, target):
            from app.services.in_game import unit_effects

            unit_effects.apply(
                game, target, name, unit_effects.turn_index(game),
                melee_skill=found.how["melee_skill"], source_unit=unit,
            )
    return result
