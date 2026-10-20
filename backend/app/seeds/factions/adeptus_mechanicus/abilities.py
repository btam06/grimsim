from app.combat_rules import Rule
from app.combat_rules.conditions import (
    ALWAYS,
    ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
    MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
    RANGED_MOVED_LESS_THAN_3,
)
from app.combat_rules.effects import (
    ASSAULT,
    HEAVY,
    IMPROVE_AP,
    MINUS_ONE_TO_HIT,
    PLUS_ONE_SKILL_MELEE,
    PLUS_ONE_SKILL_RANGED,
)

DOCTRINA_IMPERATIVES = "Doctrina Imperatives"

# (ability name, description)
ENTRIES = [
    (
        DOCTRINA_IMPERATIVES,
        "While a Doctrina Imperative (Protector or Conqueror) is active, units with this ability gain its abilities.",
    ),
]

# Rule options for abilities above: {ability name: {option name: [Rule, ...]}}.
# A unit with one of these faction abilities gains the rules of whichever of
# its options is active in combat.
#
# "If this unit is BATTLELINE or within 6\" of one or more friendly ADEPTUS
# MECHANICUS BATTLELINE units": the calculator's Positioning section says
# whether a unit is within 6" (see app/combat_rules/positions.py).
OPTIONS = {
    DOCTRINA_IMPERATIVES: {
        "Protector Imperative": [
            # Ranged weapons have [HEAVY].
            Rule(conditions=(RANGED_MOVED_LESS_THAN_3,), effects=(HEAVY,)),
            # Improve the Ballistic Skill of ranged weapons by 1.
            Rule(conditions=(ALWAYS,), effects=(PLUS_ONE_SKILL_RANGED,)),
            # Melee attacks targeting this unit, if it is BATTLELINE (or near
            # one): -1 to hit.
            Rule(
                conditions=(MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,),
                effects=(MINUS_ONE_TO_HIT,),
                side="defender",
            ),
        ],
        "Conqueror Imperative": [
            # Ranged weapons have [ASSAULT].
            Rule(conditions=(ALWAYS,), effects=(ASSAULT,)),
            # Improve the Weapon Skill of melee weapons by 1.
            Rule(conditions=(ALWAYS,), effects=(PLUS_ONE_SKILL_MELEE,)),
            # Attacks by this unit, if it is BATTLELINE (or near one): improve AP
            # by 1.
            Rule(
                conditions=(ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,),
                effects=(IMPROVE_AP,),
            ),
        ],
    },
}
