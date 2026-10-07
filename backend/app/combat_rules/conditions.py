from __future__ import annotations

# Each condition is a hardcoded keyword + a function that inspects the current
# combat-resolution step and reports whether that condition is met. The keyword
# is what gets stored on a Condition row (app/models/condition.py) and seeded
# (app/seeds/conditions.py) so it can be attached to a WeaponAbility; the engine
# (app/services/combat.py) looks the function back up by that same keyword.
#
# To add another condition: write a `context -> bool` function below, register
# its keyword in CONDITIONS, then add a matching row in app/seeds/conditions.py.

CRITICAL_HIT = "critical_hit"
ALWAYS = "always"


def critical_hit(context: dict) -> bool:
    # True when the roll just made was a hit roll, and it came up a natural 6.
    return context.get("step") == "hit" and context.get("roll") == 6


def always(context: dict) -> bool:
    # Unconditional - an ability using this "condition" simply always applies
    # its effects, regardless of step or roll (e.g. a static weapon/wargear trait).
    return True


CONDITIONS = {
    CRITICAL_HIT: critical_hit,
    ALWAYS: always,
}
