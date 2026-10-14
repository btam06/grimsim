from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Rule:
    # A code-defined counterpart to an ability row (WeaponAbility etc.): if
    # *any* of its conditions match the current step, *all* of its effects
    # apply - the same keywords, looked up in CONDITIONS/EFFECTS.
    #
    # `side` says whose attacks the rule modifies: an "attacker" rule applies
    # when the unit that has it makes attacks; a "defender" rule applies to
    # attacks made *against* the unit that has it (e.g. -1 to be hit).
    conditions: tuple[str, ...]
    effects: tuple[str, ...]
    side: Literal["attacker", "defender"] = "attacker"
