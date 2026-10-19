from __future__ import annotations

from typing import Literal

from app.models import Stratagem, Unit

Side = Literal["attacker", "defender"]

# In the combat calculator, a ranged attack happens in the shooting phase and
# a melee one in the fight phase.
CALCULATOR_PHASES = {False: "shooting", True: "fight"}

# Which stratagem timings each side can use: the attacker's unit is attacking
# in its own turn, the defender's is being attacked in its opponent's turn.
SIDE_TURNS = {"attacker": ("your_turn", "either"), "defender": ("opponent_turn", "either")}


def calculator_phase(in_engagement_range: bool) -> str:
    return CALCULATOR_PHASES[in_engagement_range]


def unavailable_reason(stratagem: Stratagem, unit: Unit, side: Side, phase: str) -> str | None:
    # Why a stratagem can't be used on `unit` as the given side in `phase`, or
    # None if it can. Needs the unit's army list detachments and its models'
    # keywords loaded, and the stratagem's detachments, keywords and timings.
    role = "attacking" if side == "attacker" else "defending"

    # Core, or from one of the detachments the unit's army list has taken.
    detachment_ids = {d.id for d in unit.army_list.detachments} if unit.army_list else set()
    if not stratagem.is_core and not ({d.id for d in stratagem.detachments} & detachment_ids):
        return f"is not available to the {role} unit's detachments"

    # Keyword requirements: a model in the unit with all of them (e.g. a
    # CHARACTER for Epic Challenge).
    required = {k.name for k in stratagem.keywords}
    if required and not any(
        required <= {k.name for k in unit_model.model.keywords} for unit_model in unit.unit_models
    ):
        return f"needs a model with {', '.join(sorted(required))} in the {role} unit"

    # Timing: no timings means any time.
    if stratagem.timings and not any(
        t.phase == phase and t.turn in SIDE_TURNS[side] for t in stratagem.timings
    ):
        return f"can't be used by the {side} in the {phase} phase"
    return None
