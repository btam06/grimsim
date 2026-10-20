from app.combat_rules import Rule
from app.combat_rules.conditions import ALWAYS, RILED_UP
from app.combat_rules.effects import ASSAULT, INVULNERABLE_5

WAAAGH = "Waaagh!"

# (ability name, description)
ENTRIES = [
    (
        WAAAGH,
        "Units can re-roll advance rolls and become riled up (e.g. by a Waaagh! war cry): "
        "while riled up they have a 5+ invulnerable save, their ranged attacks have "
        "[ASSAULT], and advancing doesn't stop them declaring a charge.",
    ),
]

# Rule options for abilities above: {ability name: {option name: [Rule, ...]}}
# (see app/seeds/factions/__init__.py). Each rule's description says what it
# does in the calculator.
OPTIONS = {
    WAAAGH: {
        RILED_UP: [
            Rule(
                conditions=(ALWAYS,),
                effects=(INVULNERABLE_5,),
                side="defender",
                description="This unit has a 5+ invulnerable save.",
            ),
            Rule(
                conditions=(ALWAYS,),
                effects=(ASSAULT,),
                description="This unit's ranged attacks have [ASSAULT].",
            ),
        ],
    },
}

# How the calculator handles abilities above, where that needs saying:
# {ability name: note}.
CALCULATOR_NOTES = {
    WAAAGH: (
        "Re-rolling Advance rolls, charging after Advancing and the once-per-battle War Cry "
        "are outside the calculator - pick Riled Up when the unit is riled up."
    ),
}
