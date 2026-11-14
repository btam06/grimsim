from app.combat_rules.conditions import BELOW_HALF_STRENGTH, BELOW_STARTING_STRENGTH

# Adepta Sororitas conditions - checks for its own rules (e.g. The Blood of
# Martyrs, Fervent Purgation), shaped like the core ones in
# app/combat_rules/conditions.py, which combines them.
#
# Those about the attack as a whole are checked at its pre-hit step, so an
# effect they trigger is applied once per attack (and carried to its Wound
# roll); the critical wound ones at its Wound roll.

ATTACKER_BELOW_STARTING_STRENGTH = "attacker_below_starting_strength"
ATTACKER_BELOW_HALF_STRENGTH = "attacker_below_half_strength"
RANGED_TARGET_WITHIN_6 = "ranged_target_within_6"
RANGED_CRITICAL_WOUND = "ranged_critical_wound"
TORRENT_CRITICAL_WOUND = "torrent_critical_wound"
RANGED_VS_SORORITAS_KILLER = "ranged_vs_sororitas_killer"

# The calculator's Positioning (see app/combat_rules/positions.py): the target
# is within 6" of the attacking unit (measured in a game).
WITHIN_6_OF_TARGET = "within_6_of_target"
# ...and the target has destroyed one or more ADEPTA SORORITAS units of the
# attacking army this battle (e.g. Storm of Retribution).
TARGET_KILLED_SORORITAS = "target_killed_sororitas"


def _pre_hit(context: dict) -> bool:
    return context.get("step") == "pre_hit"


def attacker_below_starting_strength(context: dict) -> bool:
    # An attack by a unit below its Starting Strength (Below Half-strength
    # counts too) - e.g. The Blood of Martyrs' +1 to hit.
    positions = context.get("attacker_positions", set())
    return _pre_hit(context) and bool(
        {BELOW_STARTING_STRENGTH, BELOW_HALF_STRENGTH} & positions
    )


def attacker_below_half_strength(context: dict) -> bool:
    # An attack by a unit that's Below Half-strength - e.g. The Blood of
    # Martyrs' +1 to wound.
    return _pre_hit(context) and BELOW_HALF_STRENGTH in context.get(
        "attacker_positions", set()
    )


def ranged_target_within_6(context: dict) -> bool:
    # A ranged attack that targets a unit within 6" - e.g. Fervent
    # Purgation's +1 Strength.
    return (
        _pre_hit(context)
        and context.get("is_ranged", False)
        and WITHIN_6_OF_TARGET in context.get("attacker_positions", set())
    )


def ranged_critical_wound(context: dict) -> bool:
    # A ranged attack's Critical Wound (an unmodified Wound roll of 6) - e.g.
    # Devastating Reprise's [DEVASTATING WOUNDS].
    return (
        context.get("step") == "wound"
        and context.get("roll") == 6
        and context.get("is_ranged", False)
    )


def torrent_critical_wound(context: dict) -> bool:
    # A [TORRENT] weapon's Critical Wound - e.g. Cleansing Flames'
    # [DEVASTATING WOUNDS].
    return (
        context.get("step") == "wound"
        and context.get("roll") == 6
        and "Torrent" in context.get("weapon_ability_names", set())
    )


def ranged_vs_sororitas_killer(context: dict) -> bool:
    # A ranged attack against a unit that's destroyed one of the attacking
    # army's ADEPTA SORORITAS units this battle - e.g. Storm of Retribution.
    return (
        _pre_hit(context)
        and context.get("is_ranged", False)
        and TARGET_KILLED_SORORITAS in context.get("attacker_positions", set())
    )


CONDITIONS = {
    ATTACKER_BELOW_STARTING_STRENGTH: attacker_below_starting_strength,
    ATTACKER_BELOW_HALF_STRENGTH: attacker_below_half_strength,
    RANGED_TARGET_WITHIN_6: ranged_target_within_6,
    RANGED_CRITICAL_WOUND: ranged_critical_wound,
    TORRENT_CRITICAL_WOUND: torrent_critical_wound,
    RANGED_VS_SORORITAS_KILLER: ranged_vs_sororitas_killer,
}

# (keyword, name, description), seeded as Condition rows.
ENTRIES = [
    (
        ATTACKER_BELOW_STARTING_STRENGTH,
        "Attacker Below Starting Strength",
        "An attack by a unit that is below its Starting Strength.",
    ),
    (
        ATTACKER_BELOW_HALF_STRENGTH,
        "Attacker Below Half-strength",
        "An attack by a unit that is Below Half-strength.",
    ),
    (
        RANGED_TARGET_WITHIN_6,
        "Ranged Attack vs Target Within 6\"",
        "A ranged attack that targets a unit within 6\".",
    ),
    (
        RANGED_CRITICAL_WOUND,
        "Ranged Critical Wound",
        "An unmodified Wound roll of 6 for a ranged attack.",
    ),
    (
        TORRENT_CRITICAL_WOUND,
        "Torrent Critical Wound",
        "An unmodified Wound roll of 6 for an attack made with a [TORRENT] weapon.",
    ),
    (
        RANGED_VS_SORORITAS_KILLER,
        "Ranged Attack vs Sororitas Killer",
        "A ranged attack against a unit that has destroyed one or more ADEPTA SORORITAS units "
        "of the attacking army this battle.",
    ),
]
