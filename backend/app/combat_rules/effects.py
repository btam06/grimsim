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


def auto_pass_wound(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The wound roll for *this* attack is skipped and treated as an automatic success.
    state["auto_pass_wound"] = True


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


EFFECTS = {
    AUTO_PASS_WOUND: auto_pass_wound,
    ADD_EXTRA_HIT: add_extra_hit,
    IGNORE_COVER: ignore_cover,
    NO_SAVE: no_save,
}
