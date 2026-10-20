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
# its options is active in combat. Each rule's description says what it does
# in the calculator.
OPTIONS = {
    DOCTRINA_IMPERATIVES: {
        "Protector Imperative": [
            Rule(
                conditions=(RANGED_MOVED_LESS_THAN_3,),
                effects=(HEAVY,),
                description="Ranged weapons have [HEAVY].",
            ),
            Rule(
                conditions=(ALWAYS,),
                effects=(PLUS_ONE_SKILL_RANGED,),
                description="Improve the Ballistic Skill of ranged weapons by 1.",
            ),
            Rule(
                conditions=(MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,),
                effects=(MINUS_ONE_TO_HIT,),
                side="defender",
                description=(
                    "Melee attacks against this unit are -1 to hit if it's BATTLELINE, or "
                    "within 6\" of a friendly ADEPTUS MECHANICUS BATTLELINE unit (ticked "
                    "under Positioning)."
                ),
            ),
        ],
        "Conqueror Imperative": [
            Rule(
                conditions=(ALWAYS,),
                effects=(ASSAULT,),
                description="Ranged weapons have [ASSAULT].",
            ),
            Rule(
                conditions=(ALWAYS,),
                effects=(PLUS_ONE_SKILL_MELEE,),
                description="Improve the Weapon Skill of melee weapons by 1.",
            ),
            Rule(
                conditions=(ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,),
                effects=(IMPROVE_AP,),
                description=(
                    "Improve the AP of this unit's attacks by 1 if it's BATTLELINE, or within "
                    "6\" of a friendly ADEPTUS MECHANICUS BATTLELINE unit (ticked under "
                    "Positioning)."
                ),
            ),
        ],
    },
}
