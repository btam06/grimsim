from app.combat_rules.conditions import (
    charged,
    critical_hit,
    defender_in_range_of_objective,
    strength_exceeds_toughness,
    target_monster_or_vehicle,
    target_not_monster_or_vehicle,
)

# Space Marines conditions - checks for its own rules (e.g. Never Shall the
# Standard Fall, Terminatus Assault), shaped like the core ones in
# app/combat_rules/conditions.py, which combines them.

STANDARD_FALL = "standard_fall"
CHARGED_CLAWS_CRITICAL_VS_NON_MONSTER_VEHICLE = "charged_claws_critical_vs_non_monster_vehicle"
CHARGED_HAMMER_CRITICAL_VS_MONSTER_VEHICLE = "charged_hammer_critical_vs_monster_vehicle"
ASSAULT_DOCTRINE_ACTIVE = "assault_doctrine_active"
DEVASTATOR_DOCTRINE_CRITICAL_HIT = "devastator_doctrine_critical_hit"
TACTICAL_DOCTRINE_CRITICAL_HIT = "tactical_doctrine_critical_hit"
ASSAULT_DOCTRINE_TARGET_WITHIN_9 = "assault_doctrine_target_within_9"
HELLFIRE_ANTI_NON_VEHICLE_4 = "hellfire_anti_non_vehicle_4"
# The calculator's Positioning (see app/combat_rules/positions.py): the
# target is within 9" of the attacking unit - Purgatus Tactics.
TARGET_WITHIN_9 = "target_within_9"


def standard_fall(context: dict) -> bool:
    # At the wound step: the defending unit is within range of an objective
    # (ticked under Positioning) and the attack's Strength is greater than
    # its Toughness - Never Shall the Standard Fall.
    return defender_in_range_of_objective(context) and strength_exceeds_toughness(context)


def _weapon(context: dict, name: str) -> bool:
    return name in context.get("weapon_name", "").lower()


def charged_claws_critical_vs_non_monster_vehicle(context: dict) -> bool:
    # A Critical Hit with a Lightning Claws weapon, by a unit that charged
    # this turn, against a unit with no MONSTER or VEHICLE model - Terminatus
    # Assault's [SUSTAINED HITS 1].
    return (
        charged(context)
        and _weapon(context, "lightning claws")
        and critical_hit(context)
        and target_not_monster_or_vehicle(context)
    )


def charged_hammer_critical_vs_monster_vehicle(context: dict) -> bool:
    # A Critical Hit with a Thunder Hammer weapon, by a unit that charged this
    # turn, against a unit with a MONSTER or VEHICLE model - Terminatus
    # Assault's [SUSTAINED HITS 1].
    return (
        charged(context)
        and _weapon(context, "thunder hammer")
        and critical_hit(context)
        and target_monster_or_vehicle(context)
    )


def _doctrine(context: dict, name: str) -> bool:
    return f"{name} Doctrine" in context.get("attacker_options", set())


def assault_doctrine_active(context: dict) -> bool:
    # The attacking unit has the Assault Doctrine active (Combat Doctrines) -
    # e.g. Gene-Wrought Might's +1 AP.
    return _doctrine(context, "Assault")


def devastator_doctrine_critical_hit(context: dict) -> bool:
    # A Critical Hit while the attacking unit has the Devastator Doctrine
    # active - Furor Tactics' [SUSTAINED HITS 1].
    return _doctrine(context, "Devastator") and critical_hit(context)


def tactical_doctrine_critical_hit(context: dict) -> bool:
    # A Critical Hit while the attacking unit has the Tactical Doctrine
    # active - Malleus Tactics' [LETHAL HITS].
    return _doctrine(context, "Tactical") and critical_hit(context)


def assault_doctrine_target_within_9(context: dict) -> bool:
    # The attacking unit has the Assault Doctrine active and its target is
    # within 9" of it (ticked under Positioning) - Purgatus Tactics'
    # [PRECISION].
    return assault_doctrine_active(context) and TARGET_WITHIN_9 in context.get(
        "attacker_positions", set()
    )


def hellfire_anti_non_vehicle_4(context: dict) -> bool:
    # At the wound step of a ranged attack, a wound roll of 4+ against a unit
    # with no VEHICLE model, by a weapon without [DEVASTATING WOUNDS] -
    # Hellfire Rounds' [ANTI-non-VEHICLE 4+].
    return (
        context.get("step") == "wound"
        and context.get("is_ranged", False)
        and context.get("roll", 0) >= 4
        and "VEHICLE" not in context.get("defender_keywords", set())
        and "Devastating Wounds" not in context.get("weapon_ability_names", set())
    )


CONDITIONS = {
    STANDARD_FALL: standard_fall,
    CHARGED_CLAWS_CRITICAL_VS_NON_MONSTER_VEHICLE: charged_claws_critical_vs_non_monster_vehicle,
    CHARGED_HAMMER_CRITICAL_VS_MONSTER_VEHICLE: charged_hammer_critical_vs_monster_vehicle,
    ASSAULT_DOCTRINE_ACTIVE: assault_doctrine_active,
    DEVASTATOR_DOCTRINE_CRITICAL_HIT: devastator_doctrine_critical_hit,
    TACTICAL_DOCTRINE_CRITICAL_HIT: tactical_doctrine_critical_hit,
    ASSAULT_DOCTRINE_TARGET_WITHIN_9: assault_doctrine_target_within_9,
    HELLFIRE_ANTI_NON_VEHICLE_4: hellfire_anti_non_vehicle_4,
}

# Seeded Condition rows, for those stratagems reference by keyword (see
# app/data/stratagems.json): (keyword, name, description).
ENTRIES = [
    (
        HELLFIRE_ANTI_NON_VEHICLE_4,
        "Hellfire Anti-non-Vehicle 4+",
        "A ranged wound roll of 4+ against a unit with no VEHICLE model, by a weapon without "
        "[DEVASTATING WOUNDS].",
    ),
]
