from __future__ import annotations

from fastapi import HTTPException

from app.models import Unit
from app.engine.state import PHASES, Game, GameHagiomnifexUse
from app.services.in_game import deployment

# Hagiomnifex (the Sanctified Orators upgrade), in a game: once per turn, at
# the start of a phase (either player's turn), the unit's player can select
# one of its abilities - in play for the rest of that phase:
#
# - Rite of Revelation: while this unit is shooting, enemy units have +6"
#   detection range (see app/services/in_game/shooting.py detection_range).
# - Sermon of Intolerance: this unit's Battle-shock rolls automatically
#   succeed (see app/services/in_game/battle_shock.py).
# - Catechism of Raging Fervour: this unit has +1" M.
# - Psalm of Righteous Smiting: this unit's attacks have +1 S.
# - Chorus of Repudiation: attacks that target this unit with a S greater
#   than its T have -1 to wound rolls.
#
# The start of a phase: before anything's happened in it - no Battle-shock
# test taken (Command), no unit moved (Movement), shot (Shooting), declared a
# charge (Charge), or piled in or fought (Fight) this turn.

HAGIOMNIFEX = "Hagiomnifex"
RITE_OF_REVELATION = "Rite of Revelation"
SERMON_OF_INTOLERANCE = "Sermon of Intolerance"
CATECHISM_OF_RAGING_FERVOUR = "Catechism of Raging Fervour"
PSALM_OF_RIGHTEOUS_SMITING = "Psalm of Righteous Smiting"
CHORUS_OF_REPUDIATION = "Chorus of Repudiation"
ABILITIES = (
    RITE_OF_REVELATION,
    SERMON_OF_INTOLERANCE,
    CATECHISM_OF_RAGING_FERVOUR,
    PSALM_OF_RIGHTEOUS_SMITING,
    CHORUS_OF_REPUDIATION,
)
DETECTION_BONUS = 6.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _this_turn(game: Game, record) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def has_it(unit: Unit) -> bool:
    return unit.upgrade is not None and unit.upgrade.name == HAGIOMNIFEX


def phase_started(game: Game) -> bool:
    # Whether something's happened in this phase already (so it's past its
    # start).
    phase = game.phase
    if phase == "command":
        return any(
            _this_turn(game, t) and t.phase == "command" and t.passed is not None
            for t in game.battle_shock_tests
        )
    if phase == "movement":
        return any(_this_turn(game, m) for m in game.unit_moves)
    if phase == "shooting":
        return any(_this_turn(game, s) for s in game.unit_shots)
    if phase == "charge":
        return any(_this_turn(game, c) for c in game.unit_charges)
    if phase == "fight":
        return any(_this_turn(game, p) for p in game.unit_pile_ins) or any(
            _this_turn(game, f) for f in game.unit_fights
        )
    return True


def used_this_turn(game: Game, unit: Unit) -> GameHagiomnifexUse | None:
    return next(
        (u for u in game.hagiomnifex_uses if u.unit_id == unit.id and _this_turn(game, u)),
        None,
    )


def active(game: Game, unit: Unit) -> str | None:
    # The ability selected for the unit this phase, if one was.
    use = used_this_turn(game, unit)
    return use.ability if use is not None and use.phase == game.phase else None


def cant_reason(game: Game, unit: Unit) -> str | None:
    if not has_it(unit):
        return f"it doesn't have {HAGIOMNIFEX}"
    if game.status != "in_progress" or game.phase not in PHASES:
        return "it's used at the start of a phase"
    if not deployment.models_on_battlefield(game, unit):
        return "it isn't on the battlefield"
    if used_this_turn(game, unit) is not None:
        return "it's already been used this turn"
    if phase_started(game):
        return "the start of the phase has passed"
    return None


def use(game: Game, unit: Unit, ability: str) -> None:
    if ability not in ABILITIES:
        raise _bad_request(f"{HAGIOMNIFEX} has no {ability!r} ability")
    if (reason := cant_reason(game, unit)) is not None:
        raise _bad_request(f"{unit.label} can't use {HAGIOMNIFEX}: {reason}")
    game.hagiomnifex_uses.append(
        GameHagiomnifexUse(
            seat=deployment.owner(game, unit).seat,
            unit_id=unit.id,
            ability=ability,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            phase=game.phase,
        )
    )


# --- what each does ---


def detection_bonus(game: Game, viewer: Unit | None) -> float:
    # Rite of Revelation: what's added to enemy units' detection range while
    # `viewer` is shooting.
    if viewer is not None and active(game, viewer) == RITE_OF_REVELATION:
        return DETECTION_BONUS
    return 0.0


def auto_pass_battle_shock(game: Game, unit: Unit) -> bool:
    return active(game, unit) == SERMON_OF_INTOLERANCE


def move_bonus(game: Game, unit: Unit) -> int:
    return 1 if active(game, unit) == CATECHISM_OF_RAGING_FERVOUR else 0


def attack_rules(game: Game, unit: Unit) -> list:
    # Psalm of Righteous Smiting: the unit's attacks have +1 S.
    from app.combat_rules import Rule
    from app.combat_rules.conditions import ALWAYS
    from app.combat_rules.effects import PLUS_ONE_STRENGTH

    if active(game, unit) != PSALM_OF_RIGHTEOUS_SMITING:
        return []
    return [Rule(conditions=(ALWAYS,), effects=(PLUS_ONE_STRENGTH,))]


def defence_rules(game: Game, unit: Unit) -> list:
    # Chorus of Repudiation: attacks against the unit with S greater than its
    # T have -1 to wound.
    from app.combat_rules import Rule
    from app.combat_rules.conditions import STRENGTH_EXCEEDS_TOUGHNESS
    from app.combat_rules.effects import MINUS_ONE_TO_WOUND

    if active(game, unit) != CHORUS_OF_REPUDIATION:
        return []
    return [
        Rule(
            conditions=(STRENGTH_EXCEEDS_TOUGHNESS,),
            effects=(MINUS_ONE_TO_WOUND,),
            side="defender",
        )
    ]
