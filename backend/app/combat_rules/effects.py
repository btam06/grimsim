from __future__ import annotations

from collections import deque
from typing import Any

# Each effect is a hardcoded keyword + a function that mutates the current
# attack's state and/or the queue of pending attacks for the weapon still being
# resolved. The keyword is what gets stored on an Effect row
# (app/models/effect.py) and seeded (app/seeds/effects.py) so it can be attached
# to a WeaponAbility; the engine (app/services/combat.py) looks the function
# back up by that same keyword once one of the ability's conditions matches.
#
# To add another effect: write a `(state, pending) -> None` function below,
# register its keyword in EFFECTS, then add a matching row in
# app/seeds/effects.py.

AUTO_PASS_WOUND = "auto_pass_wound"
ADD_EXTRA_HIT = "add_extra_hit"
IGNORE_COVER = "ignore_cover"
NO_SAVE = "no_save"
FORCE_CRITICAL_WOUND = "force_critical_wound"
ADD_EXTRA_ATTACK = "add_extra_attack"
IGNORE_COVER_UNIT = "ignore_cover_unit"
HAZARDOUS = "hazardous"
PLUS_ONE_TO_HIT = "plus_one_to_hit"
REROLL_FAILED_HITS = "reroll_failed_hits"
PLUS_ONE_SKILL_RANGED = "plus_one_skill_ranged"
PLUS_ONE_SKILL_MELEE = "plus_one_skill_melee"


def auto_pass_wound(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The wound roll for *this* attack is skipped and treated as an automatic success.
    state["auto_pass_wound"] = True


def force_critical_wound(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's wound counts as a critical wound regardless of the actual
    # roll (e.g. an Anti-Infantry/Anti-Vehicle threshold was met) - it still
    # triggers critical_wound-dependent effects like Devastating Wounds.
    state["critical_wound"] = True


def add_extra_hit(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues one additional hit onto the attack chain - it's already a hit, so it
    # skips straight to the wound step with no hit roll of its own.
    pending.append({"auto_hit": True})


def ignore_cover(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll is not worsened by the defender being in cover.
    state["ignore_cover"] = True


def no_save(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The save roll for *this* attack is skipped entirely and treated as failed -
    # no armor save, and no invulnerable save either.
    state["no_save"] = True


def add_extra_attack(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues one additional attack onto the chain for this weapon - unlike
    # add_extra_hit, this is a fresh attack that still needs its own hit roll.
    pending.append({"auto_hit": False})


def ignore_cover_unit(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Marks the whole attacking unit (not just the model carrying this
    # wargear) as ignoring the in-cover penalty, for every weapon it fires.
    state["ignore_cover_unit"] = True


def hazardous(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Marks this weapon as hazardous - the engine makes a hazard roll for the
    # firing model once per weapon used, separately from the attack sequence.
    state["hazardous"] = True


def plus_one_to_hit(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll needs 1 less to succeed (e.g. Heavy, when the
    # firing unit moved less than 3" this turn).
    state["plus_one_to_hit"] = True


def reroll_failed_hits(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # If this attack's hit roll fails, it is rolled once more and the second
    # result is used instead.
    state["reroll_failed_hits"] = True


def plus_one_skill_ranged(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll needs 1 less to succeed, but only if the weapon
    # firing is ranged (no effect on a melee attack).
    state["plus_one_skill_ranged"] = True


def plus_one_skill_melee(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll needs 1 less to succeed, but only if the weapon
    # swinging is melee (no effect on a ranged attack).
    state["plus_one_skill_melee"] = True


EFFECTS = {
    AUTO_PASS_WOUND: auto_pass_wound,
    ADD_EXTRA_HIT: add_extra_hit,
    IGNORE_COVER: ignore_cover,
    NO_SAVE: no_save,
    FORCE_CRITICAL_WOUND: force_critical_wound,
    ADD_EXTRA_ATTACK: add_extra_attack,
    IGNORE_COVER_UNIT: ignore_cover_unit,
    HAZARDOUS: hazardous,
    PLUS_ONE_TO_HIT: plus_one_to_hit,
    REROLL_FAILED_HITS: reroll_failed_hits,
    PLUS_ONE_SKILL_RANGED: plus_one_skill_ranged,
    PLUS_ONE_SKILL_MELEE: plus_one_skill_melee,
}
