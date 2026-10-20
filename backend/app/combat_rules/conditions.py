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
ANTI_MONSTER_4 = "anti_monster_4"
WITHIN_HALF_RANGE = "within_half_range"
MOVED_LESS_THAN_3 = "moved_less_than_3"
TARGET_MONSTER_OR_VEHICLE = "target_monster_or_vehicle"
RANGED_MOVED_LESS_THAN_3 = "ranged_moved_less_than_3"
MELEE_ATTACK_AGAINST_BATTLELINE = "melee_attack_against_battleline"
ATTACKER_IS_BATTLELINE = "attacker_is_battleline"
TARGET_NOT_MONSTER_OR_VEHICLE = "target_not_monster_or_vehicle"
CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE = "critical_hit_not_monster_or_vehicle"
RILED_UP_RANGED_CRITICAL_HIT = "riled_up_ranged_critical_hit"
PRE_WEAPON_NOT_MONSTER_OR_VEHICLE = "pre_weapon_not_monster_or_vehicle"
TARGET_HAS_CHARACTER = "target_has_character"
TARGET_LED_BY_CHARACTER = "target_led_by_character"
TARGET_INFANTRY = "target_infantry"
RANGED_ATTACK = "ranged_attack"
TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER = "target_electro_priests_led_by_character"
ATTACKER_NEAR_ADMECH_BATTLELINE = "attacker_near_admech_battleline"
ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE = "attacker_battleline_or_near_admech_battleline"
MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE = "melee_vs_battleline_or_near_admech_battleline"

# Positions a unit can be in that the calculator can't work out for itself,
# so the user says (see app/combat_rules/positions.py); conditions read them
# from the context's attacker_positions/defender_positions.
NEAR_ADMECH_BATTLELINE = "near_admech_battleline"

# Name of the Orks Waaagh! rule option that riles a unit up (see
# app/seeds/factions/orks/abilities.py), for "if this unit is riled up".
RILED_UP = "Riled Up"


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


def anti_monster_4(context: dict) -> bool:
    # True at the wound step if the wound roll was a 4+ against a defending
    # unit that contains a MONSTER model (e.g. for "Anti-Monster 4+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 4
        and "MONSTER" in context.get("defender_keywords", set())
    )


def within_half_range(context: dict) -> bool:
    # True at the once-per-weapon pre-weapon check if the shooting model is
    # within half the weapon's range (e.g. for a Rapid Fire weapon ability).
    return context.get("step") == "pre_weapon" and context.get("half_range", False)


def moved_less_than_3(context: dict) -> bool:
    # True at the pre-hit check if the attacking unit moved less than 3"
    # this turn (e.g. for a Heavy weapon ability).
    return context.get("step") == "pre_hit" and context.get("moved_less_than_3", False)


def target_monster_or_vehicle(context: dict) -> bool:
    # True at every step (like `always`) when the defending unit contains a
    # MONSTER or VEHICLE model - e.g. for a +1 to hit against big targets.
    defender_keywords = context.get("defender_keywords", set())
    return "MONSTER" in defender_keywords or "VEHICLE" in defender_keywords


def ranged_moved_less_than_3(context: dict) -> bool:
    # Like moved_less_than_3, but only for a ranged weapon - e.g. for granting
    # Heavy to a unit's ranged weapons without affecting its melee weapons.
    return moved_less_than_3(context) and context.get("is_ranged", False)


def melee_attack_against_battleline(context: dict) -> bool:
    # True at the pre-hit check of a melee attack against a defending unit
    # that contains a BATTLELINE model (e.g. Protector Imperative's -1 to hit).
    return (
        context.get("step") == "pre_hit"
        and not context.get("is_ranged", True)
        and "BATTLELINE" in context.get("defender_keywords", set())
    )


def attacker_is_battleline(context: dict) -> bool:
    # True at every step (like `always`) when the attacking unit contains a
    # BATTLELINE model (e.g. Conqueror Imperative's improved AP).
    return "BATTLELINE" in context.get("attacker_keywords", set())


def attacker_near_admech_battleline(context: dict) -> bool:
    # True at every step while the attacking unit is within 6" of a friendly
    # ADEPTUS MECHANICUS BATTLELINE unit (e.g. Breaching Command's re-rolls).
    return NEAR_ADMECH_BATTLELINE in context.get("attacker_positions", set())


def attacker_battleline_or_near_admech_battleline(context: dict) -> bool:
    # As attacker_is_battleline, or while the attacking unit is within 6" of a
    # friendly ADEPTUS MECHANICUS BATTLELINE unit (Conqueror Imperative).
    return attacker_is_battleline(context) or attacker_near_admech_battleline(context)


def melee_vs_battleline_or_near_admech_battleline(context: dict) -> bool:
    # As melee_attack_against_battleline, or against a defending unit within
    # 6" of a friendly ADEPTUS MECHANICUS BATTLELINE unit (Protector Imperative).
    return (
        context.get("step") == "pre_hit"
        and not context.get("is_ranged", True)
        and (
            "BATTLELINE" in context.get("defender_keywords", set())
            or NEAR_ADMECH_BATTLELINE in context.get("defender_positions", set())
        )
    )


def target_not_monster_or_vehicle(context: dict) -> bool:
    # The opposite of target_monster_or_vehicle, at every step - e.g. for a
    # HUNTER: MONSTER/VEHICLE profile that can't attack anything else.
    return not target_monster_or_vehicle(context)


def critical_hit_not_monster_or_vehicle(context: dict) -> bool:
    # A critical hit against a defending unit with no MONSTER or VEHICLE model
    # (e.g. for "LETHAL HITS: non-MONSTER/VEHICLE").
    return critical_hit(context) and target_not_monster_or_vehicle(context)


def riled_up_ranged_critical_hit(context: dict) -> bool:
    # A critical hit with a ranged weapon while the attacking unit is riled up
    # (e.g. Even More Dakka's [SUSTAINED HITS 1]).
    return (
        critical_hit(context)
        and context.get("is_ranged", False)
        and RILED_UP in context.get("attacker_options", set())
    )


def pre_weapon_not_monster_or_vehicle(context: dict) -> bool:
    # Checked once per weapon (not per attack): the defending unit has no
    # MONSTER or VEHICLE model - e.g. for Blitz Dem Gitz!'s extra attacks.
    return context.get("step") == "pre_weapon" and target_not_monster_or_vehicle(context)


def target_has_character(context: dict) -> bool:
    # True at every step when the defending unit contains a CHARACTER model -
    # e.g. "while a CHARACTER model is leading this unit" on a defensive rule.
    return "CHARACTER" in context.get("defender_keywords", set())


def target_led_by_character(context: dict) -> bool:
    # True at every step when the defending unit is a CHARACTER leading a unit:
    # it has at least one CHARACTER model and at least one other model. (A lone
    # CHARACTER isn't leading anything.)
    per_model = context.get("defender_model_keywords", [])
    return any("CHARACTER" in keywords for keywords in per_model) and any(
        "CHARACTER" not in keywords for keywords in per_model
    )


def target_electro_priests_led_by_character(context: dict) -> bool:
    # As target_led_by_character, for a led unit with the ELECTRO-PRIESTS keyword.
    return target_led_by_character(context) and "ELECTRO-PRIESTS" in context.get(
        "defender_keywords", set()
    )


def target_infantry(context: dict) -> bool:
    # True at every step when the defending unit contains an INFANTRY model -
    # e.g. "each time this model makes an attack ... that targets an INFANTRY
    # unit, add 1 to the Hit roll".
    return "INFANTRY" in context.get("defender_keywords", set())


def ranged_attack(context: dict) -> bool:
    # True at the pre-hit check of a ranged attack - e.g. Stealth's -1 to hit
    # for ranged attacks targeting the unit.
    return context.get("step") == "pre_hit" and context.get("is_ranged", False)


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
    ANTI_MONSTER_4: anti_monster_4,
    WITHIN_HALF_RANGE: within_half_range,
    MOVED_LESS_THAN_3: moved_less_than_3,
    TARGET_MONSTER_OR_VEHICLE: target_monster_or_vehicle,
    RANGED_MOVED_LESS_THAN_3: ranged_moved_less_than_3,
    MELEE_ATTACK_AGAINST_BATTLELINE: melee_attack_against_battleline,
    ATTACKER_IS_BATTLELINE: attacker_is_battleline,
    TARGET_NOT_MONSTER_OR_VEHICLE: target_not_monster_or_vehicle,
    CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE: critical_hit_not_monster_or_vehicle,
    RILED_UP_RANGED_CRITICAL_HIT: riled_up_ranged_critical_hit,
    PRE_WEAPON_NOT_MONSTER_OR_VEHICLE: pre_weapon_not_monster_or_vehicle,
    TARGET_HAS_CHARACTER: target_has_character,
    TARGET_LED_BY_CHARACTER: target_led_by_character,
    TARGET_INFANTRY: target_infantry,
    RANGED_ATTACK: ranged_attack,
    TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER: target_electro_priests_led_by_character,
    ATTACKER_NEAR_ADMECH_BATTLELINE: attacker_near_admech_battleline,
    ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE: attacker_battleline_or_near_admech_battleline,
    MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE: melee_vs_battleline_or_near_admech_battleline,
}
