from app.combat_rules import Rule, RuleOption
from app.combat_rules.conditions import RANGED_ATTACK, STATIONARY_RANGED_CRITICAL_HIT
from app.combat_rules.effects import ADD_EXTRA_HIT, PLUS_ONE_TO_HIT

# Imperial Knights datasheet abilities - see app/seeds/datasheet_abilities.py
# for what each of these holds. Core abilities (e.g. Deadly Demise) are
# defined there.

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        # Its effect is the "Crusader's Duty" option in OPTIONS.
        "Crusader's Duty (Bondsman)",
        "While a model is affected by this ability, each time that model makes a ranged "
        "attack, add 1 to the Hit roll.",
        [],
        [],
    ),
    (
        # Its effect is in RULES, read from the calculator's Positioning.
        "Punishing Salvoes",
        "In your Movement phase, if this model Remains Stationary, until the end of the turn, "
        "ranged weapons equipped by this model have the [SUSTAINED HITS 1] ability.",
        [],
        [],
    ),
]

# Selectable options for abilities above: {ability name: {option name:
# RuleOption}}.
OPTIONS = {
    "Crusader's Duty (Bondsman)": {
        "Crusader's Duty": RuleOption(
            rules=(Rule(conditions=(RANGED_ATTACK,), effects=(PLUS_ONE_TO_HIT,)),),
            army_wide=True,
            description=(
                "+1 to hit for ranged attacks - pick it for the unit the Bondsman ability is "
                "on (the Knight's own, or another unit of its faction in its army list)."
            ),
        ),
    },
}

# Code-defined rules for abilities above, by name.
RULES = {
    "Punishing Salvoes": [
        Rule(
            conditions=(STATIONARY_RANGED_CRITICAL_HIT,),
            effects=(ADD_EXTRA_HIT,),
            description=(
                "Ranged weapons have [SUSTAINED HITS 1] when Remained Stationary is ticked "
                "under Positioning."
            ),
        ),
    ],
}
