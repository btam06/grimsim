from app.combat_rules.conditions import (
    charged,
    critical_hit,
    defender_in_range_of_objective,
)

# Chaos Knights conditions - checks for its own rules (e.g. Marked Prey, Titanic
# Duel), shaped like the core ones in app/combat_rules/conditions.py, which
# combines them.

TARGET_TITANIC = "target_titanic"
MARKED_PREY_CRITICAL_HIT = "marked_prey_critical_hit"
DIABOLIC_POWER_CHARGED_MELEE = "diabolic_power_charged_melee"
RANGED_VS_OBJECTIVE_TARGET = "ranged_vs_objective_target"

# The calculator's Positioning (see app/combat_rules/positions.py).
MARKED_PREY_TARGET = "marked_prey_target"

# Malefic Surge's Diabolic Power options (see datasheet_abilities.py).
DIABOLIC_POWER = "Diabolic Power"


def target_titanic(context: dict) -> bool:
    # True at every step when the defending unit has a TITANIC model - e.g.
    # Titanic Duel's full re-rolls.
    return "TITANIC" in context.get("defender_keywords", set())


def marked_prey_critical_hit(context: dict) -> bool:
    # A critical hit by a WAR DOG model against the unit selected for Marked
    # Prey (ticked under Positioning) - [SUSTAINED HITS 1].
    return (
        critical_hit(context)
        and "WAR DOG" in context.get("attacker_model_keywords", set())
        and MARKED_PREY_TARGET in context.get("attacker_positions", set())
    )


def diabolic_power_charged_melee(context: dict) -> bool:
    # A melee attack by a unit that charged this turn, while it's using a
    # Diabolic Power option of Malefic Surge - Knight Diabolus's [LANCE].
    return (
        "is_ranged" in context
        and not context["is_ranged"]
        and charged(context)
        and any(o.startswith(DIABOLIC_POWER) for o in context.get("attacker_options", set()))
    )


def ranged_vs_objective_target(context: dict) -> bool:
    # A ranged attack against a unit within range of an objective marker
    # (ticked under Positioning) - e.g. the War Dog Brigand's [IGNORES COVER].
    return context.get("is_ranged", False) and defender_in_range_of_objective(context)


# {keyword: check}
CONDITIONS = {
    TARGET_TITANIC: target_titanic,
    MARKED_PREY_CRITICAL_HIT: marked_prey_critical_hit,
    DIABOLIC_POWER_CHARGED_MELEE: diabolic_power_charged_melee,
    RANGED_VS_OBJECTIVE_TARGET: ranged_vs_objective_target,
}

# Seeded Condition rows: (keyword, name, description).
ENTRIES = [
    (
        TARGET_TITANIC,
        "Target is Titanic",
        "The defending unit has a TITANIC model. Applies at every step.",
    ),
    (
        MARKED_PREY_CRITICAL_HIT,
        "Marked Prey Critical Hit",
        "A critical hit by a WAR DOG model against the unit selected for Marked Prey.",
    ),
    (
        DIABOLIC_POWER_CHARGED_MELEE,
        "Diabolic Power Charged Melee Attack",
        "A melee attack by a unit that charged this turn, while it's using Diabolic Power.",
    ),
    (
        RANGED_VS_OBJECTIVE_TARGET,
        "Ranged Attack vs Target on Objective",
        "A ranged attack against a unit within range of an objective marker.",
    ),
]
