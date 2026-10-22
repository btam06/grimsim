from app.combat_rules.conditions import charged, critical_hit

# Chaos Knights conditions - checks for its own rules (e.g. Marked Prey, Knight
# Diabolus), shaped like the core ones in app/combat_rules/conditions.py, which
# combines them.

MARKED_PREY_CRITICAL_HIT = "marked_prey_critical_hit"
DIABOLIC_POWER_CHARGED_MELEE = "diabolic_power_charged_melee"

# The calculator's Positioning (see app/combat_rules/positions.py).
MARKED_PREY_TARGET = "marked_prey_target"

# Malefic Surge's Diabolic Power options (see datasheet_abilities.py).
DIABOLIC_POWER = "Diabolic Power"


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


# {keyword: check}
CONDITIONS = {
    MARKED_PREY_CRITICAL_HIT: marked_prey_critical_hit,
    DIABOLIC_POWER_CHARGED_MELEE: diabolic_power_charged_melee,
}

# Seeded Condition rows: (keyword, name, description).
ENTRIES = [
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
]
