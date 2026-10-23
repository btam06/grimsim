from __future__ import annotations

from typing import Literal

from app.models import Stratagem, Unit
from app.models.game import PHASES
from app.services.list_building import enhancements as enhancement_rules

Side = Literal["attacker", "defender"]

# In the combat calculator, a ranged attack happens in the shooting phase and
# a melee one in the fight phase.
CALCULATOR_PHASES = {False: "shooting", True: "fight"}

# Which stratagem timings each side can use: the attacker's unit is attacking
# in its own turn, the defender's is being attacked in its opponent's turn.
SIDE_TURNS = {"attacker": ("your_turn", "either"), "defender": ("opponent_turn", "either")}


def calculator_phase(in_engagement_range: bool) -> str:
    return CALCULATOR_PHASES[in_engagement_range]


def _keyword_rule(stratagem: Stratagem) -> str:
    # e.g. "INFANTRY and not VEHICLE", or "SICARIAN or SKITARII + MOUNTED".
    parts = [", ".join(sorted(k.name for k in stratagem.keywords))] if stratagem.keywords else []
    if stratagem.keyword_options:
        parts.append(
            " or ".join(
                " + ".join(sorted(k.name for k in option)) for option in stratagem.keyword_options
            )
        )
    parts += [f"not {k.name}" for k in sorted(stratagem.excluded_keywords, key=lambda k: k.name)]
    return " and ".join(parts)


def unavailable_reason(stratagem: Stratagem, unit: Unit, side: Side, phase: str) -> str | None:
    # Why a stratagem can't be used on `unit` as the given side in `phase`, or
    # None if it can. Needs the unit's army list detachments and its models'
    # keywords loaded, and the stratagem's detachments, keywords and timings.
    role = "attacking" if side == "attacker" else "defending"

    # Used only on the attacking unit, or only on the one being attacked.
    if stratagem.combat_side is not None and stratagem.combat_side != side:
        return f"is only used by the {stratagem.combat_side}"

    # Core, or from one of the detachments the unit's army list has taken.
    detachment_ids = {d.id for d in unit.army_list.detachments} if unit.army_list else set()
    if not stratagem.is_core and not ({d.id for d in stratagem.detachments} & detachment_ids):
        return f"is not available to the {role} unit's detachments"

    # Keywords: a model in the unit with all the required ones (e.g. a
    # CHARACTER for Epic Challenge) and none of the excluded ones (e.g. not a
    # VEHICLE, for Baleful Halo).
    if not stratagem.is_unrestricted and not any(
        stratagem.applies_to(enhancement_rules.model_keywords(unit, unit_model))
        for unit_model in unit.unit_models
    ):
        return f"needs a model in the {role} unit with {_keyword_rule(stratagem)}"

    # Timing: no timings means any time. One that lasts until your next
    # Command phase is used then, but is in effect whenever the unit fights;
    # one that lasts until the end of the turn, in any later phase of a turn
    # it can be used in.
    if stratagem.duration == "until_next_command_phase":
        return None
    if stratagem.duration == "until_end_of_turn":
        if stratagem.timings and not any(
            PHASES.index(t.phase) <= PHASES.index(phase) and t.turn in SIDE_TURNS[side]
            for t in stratagem.timings
        ):
            return f"can't be in effect for the {side} in the {phase} phase"
        return None
    if stratagem.timings and not any(
        t.phase == phase and t.turn in SIDE_TURNS[side] for t in stratagem.timings
    ):
        return f"can't be used by the {side} in the {phase} phase"
    return None
