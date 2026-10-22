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
    # How the calculator applies it, in plain words - shown with the ability.
    description: str | None = None


@dataclass(frozen=True)
class RuleOption:
    # One selectable option of a datasheet ability (e.g. one of Belisarius
    # Cawl's Canticles of the Omnissiah): the rules it grants, any keywords the
    # model with the ability gains, and how far it reaches.
    rules: tuple[Rule, ...] = ()
    keywords: tuple[str, ...] = ()
    # False: only the unit containing the model with the ability. True: also
    # every other unit of the same faction in that model's army list (an aura
    # or army-wide effect - range isn't modelled).
    army_wide: bool = False
    # What picking it does in the calculator - shown with the option.
    description: str | None = None
    # Other rule options picking it makes active too, for a unit with the
    # ability they belong to (e.g. The Fires of Mars: both Doctrina
    # Imperatives).
    grants_options: tuple[str, ...] = ()
