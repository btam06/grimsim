from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Rule:
    # A code-defined counterpart to an ability row (WeaponAbility etc.): if
    # *all* of its conditions match the current step, *all* of its effects
    # apply - the same keywords, looked up in CONDITIONS/EFFECTS. Combine
    # existing conditions (e.g. Terminatus Assault: a critical hit, if the
    # unit charged, with a Lightning Claws weapon, against a unit with no
    # MONSTER or VEHICLE model) rather than writing one for each combination.
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
    # In a game: what the unit it applies to can still shoot and declare a
    # charge after doing in its turn - "advanced", "fell_back" (e.g.
    # Fanatical Devotion, Adaptive Tactics).
    eligible_after: tuple[str, ...] = ()
    # In a game: an aura's range (inches) - the option applies to friendly
    # units with a model within it of the model with the ability, rather than
    # to every unit it reaches in the list (see app/services/in_game/auras.py).
    aura_range: float | None = None
    # In a game: picking it means selecting one enemy unit on the battlefield
    # (anywhere, seen or not), and it only applies to attacks against that
    # unit (e.g. Invocation of Machine Vengeance).
    targets_enemy: bool = False


@dataclass(frozen=True)
class CommandChoice:
    # In a game, a datasheet ability whose option (see RuleOption) its owner
    # selects in their Command phase (see app/services/in_game/command_phase.py).
    # Normally until the start of their next Command phase, and one must be
    # selected (`required`); a `persistent` one stays until another is
    # selected, starting as `default`. With `target_keywords`, the option
    # applies to one friendly unit with one of those keywords within
    # `target_range` of the model with the ability (e.g. Rod of the War
    # Forge), selected with it - and that it can see, if `target_visible`.
    # Some are selected in another of their owner's phases instead (`phase` -
    # e.g. Author of the Codex, the Movement phase), until the start of their
    # next Command phase all the same. With `faction_options` ((faction name,
    # faction ability name)), its options are that army rule's (e.g. Author of
    # the Codex: Combat Doctrines' doctrines) rather than its own.
    required: bool = True
    persistent: bool = False
    default: str | None = None
    target_keywords: tuple[str, ...] = ()
    target_range: float | None = None
    target_visible: bool = False
    phase: str = "command"
    faction_options: tuple[str, str] | None = None
