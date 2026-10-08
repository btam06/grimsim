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
CRITICAL_WOUND = "critical_wound"
ALWAYS = "always"
ANTI_INFANTRY_2 = "anti_infantry_2"
ANTI_INFANTRY_3 = "anti_infantry_3"
ANTI_INFANTRY_4 = "anti_infantry_4"
ANTI_VEHICLE_2 = "anti_vehicle_2"
ANTI_VEHICLE_3 = "anti_vehicle_3"
ANTI_VEHICLE_4 = "anti_vehicle_4"
WITHIN_HALF_RANGE = "within_half_range"
MOVED_LESS_THAN_3 = "moved_less_than_3"


def critical_hit(context: dict) -> bool:
    # True when the roll just made was a hit roll, and it came up a natural 6.
    return context.get("step") == "hit" and context.get("roll") == 6


def critical_wound(context: dict) -> bool:
    # True when the roll just made was a wound roll, and it came up a natural 6.
    return context.get("step") == "wound" and context.get("roll") == 6


def always(context: dict) -> bool:
    # Unconditional - an ability using this "condition" simply always applies
    # its effects, regardless of step or roll (e.g. a static weapon/wargear trait).
    return True


def anti_infantry_2(context: dict) -> bool:
    # True at the wound step if the wound roll was a 2+ against a defending
    # unit that contains an INFANTRY model (e.g. for "Anti-Infantry 2+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 2
        and "INFANTRY" in context.get("defender_keywords", set())
    )


def anti_infantry_3(context: dict) -> bool:
    # True at the wound step if the wound roll was a 3+ against a defending
    # unit that contains an INFANTRY model (e.g. for "Anti-Infantry 3+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 3
        and "INFANTRY" in context.get("defender_keywords", set())
    )


def anti_infantry_4(context: dict) -> bool:
    # True at the wound step if the wound roll was a 4+ against a defending
    # unit that contains an INFANTRY model (e.g. for "Anti-Infantry 4+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 4
        and "INFANTRY" in context.get("defender_keywords", set())
    )


def anti_vehicle_2(context: dict) -> bool:
    # True at the wound step if the wound roll was a 2+ against a defending
    # unit that contains a VEHICLE model (e.g. for "Anti-Vehicle 2+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 2
        and "VEHICLE" in context.get("defender_keywords", set())
    )


def anti_vehicle_3(context: dict) -> bool:
    # True at the wound step if the wound roll was a 3+ against a defending
    # unit that contains a VEHICLE model (e.g. for "Anti-Vehicle 3+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 3
        and "VEHICLE" in context.get("defender_keywords", set())
    )


def anti_vehicle_4(context: dict) -> bool:
    # True at the wound step if the wound roll was a 4+ against a defending
    # unit that contains a VEHICLE model (e.g. for "Anti-Vehicle 4+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 4
        and "VEHICLE" in context.get("defender_keywords", set())
    )


def within_half_range(context: dict) -> bool:
    # True at the once-per-weapon pre-weapon check if the shooting model is
    # within half the weapon's range (e.g. for a Rapid Fire weapon ability).
    return context.get("step") == "pre_weapon" and context.get("half_range", False)


def moved_less_than_3(context: dict) -> bool:
    # True at the pre-hit check if the attacking unit moved less than 3"
    # this turn (e.g. for a Heavy weapon ability).
    return context.get("step") == "pre_hit" and context.get("moved_less_than_3", False)


CONDITIONS = {
    CRITICAL_HIT: critical_hit,
    CRITICAL_WOUND: critical_wound,
    ALWAYS: always,
    ANTI_INFANTRY_2: anti_infantry_2,
    ANTI_INFANTRY_3: anti_infantry_3,
    ANTI_INFANTRY_4: anti_infantry_4,
    ANTI_VEHICLE_2: anti_vehicle_2,
    ANTI_VEHICLE_3: anti_vehicle_3,
    ANTI_VEHICLE_4: anti_vehicle_4,
    WITHIN_HALF_RANGE: within_half_range,
    MOVED_LESS_THAN_3: moved_less_than_3,
}
