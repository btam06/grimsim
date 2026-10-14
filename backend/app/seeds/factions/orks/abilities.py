from app.combat_rules import Rule
from app.combat_rules.conditions import ALWAYS
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
# (see app/seeds/factions/__init__.py).
#
# Not modelled: re-rolling advance rolls, charging after advancing, and the
# once-per-battle War Cry - movement/turn-sequence rules outside combat.
OPTIONS = {
    WAAAGH: {
        "Riled Up": [
            # This unit has a 5+ invulnerable save.
            Rule(conditions=(ALWAYS,), effects=(INVULNERABLE_5,), side="defender"),
            # This unit's ranged attacks have [ASSAULT].
            Rule(conditions=(ALWAYS,), effects=(ASSAULT,)),
        ],
    },
}
