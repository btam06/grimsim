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
        # Its effect is the "Lancer's Duty" option in OPTIONS: in a game, it
        # lets the unit declare a charge after Advancing.
        "Lancer's Duty (Bondsman)",
        "While a model is affected by this ability, it is eligible to declare a charge in a "
        "turn in which it Advanced.",
        [],
        [],
    ),
    (
        # In a game, see STRATAGEM_COSTS.
        "Shock Charge",
        "You can target this model with the Crushing Impact Stratagem for 0CP, and can do so "
        "even if you have already targeted a different unit with that Stratagem this phase.",
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
    "Lancer's Duty (Bondsman)": {
        "Lancer's Duty": RuleOption(
            army_wide=True,
            eligible_after=("advanced",),
            eligible_for=("charge",),
            description=(
                "Not modelled in the calculator: in a game, the unit it's picked for can "
                "declare a charge after Advancing."
            ),
        ),
    },
}

# In a game: abilities that change what a Stratagem costs when it targets
# their unit - Shock Charge: Crushing Impact for 0CP, even if it's already
# been used this phase.
STRATAGEM_COSTS = {"Shock Charge": {"Crushing Impact": (0, True)}}

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
