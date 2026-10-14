from app.combat_rules import Rule
from app.combat_rules.conditions import (
    ALWAYS,
    ATTACKER_IS_BATTLELINE,
    MELEE_ATTACK_AGAINST_BATTLELINE,
    RANGED_MOVED_LESS_THAN_3,
)
from app.combat_rules.effects import (
    ASSAULT,
    IMPROVE_AP,
    MINUS_ONE_TO_HIT,
    PLUS_ONE_SKILL_MELEE,
    PLUS_ONE_SKILL_RANGED,
    PLUS_ONE_TO_HIT,
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
# Not modelled: "within 6\" of one or more friendly ADEPTUS MECHANICUS
# BATTLELINE units" - only the unit's own BATTLELINE keyword counts.
OPTIONS = {
    DOCTRINA_IMPERATIVES: {
        "Protector Imperative": [
            # Ranged weapons have [HEAVY].
            Rule(conditions=(RANGED_MOVED_LESS_THAN_3,), effects=(PLUS_ONE_TO_HIT,)),
            # Improve the Ballistic Skill of ranged weapons by 1.
            Rule(conditions=(ALWAYS,), effects=(PLUS_ONE_SKILL_RANGED,)),
            # Melee attacks targeting this unit, if it is BATTLELINE: -1 to hit.
            Rule(
                conditions=(MELEE_ATTACK_AGAINST_BATTLELINE,),
                effects=(MINUS_ONE_TO_HIT,),
                side="defender",
            ),
        ],
        "Conqueror Imperative": [
            # Ranged weapons have [ASSAULT].
            Rule(conditions=(ALWAYS,), effects=(ASSAULT,)),
            # Improve the Weapon Skill of melee weapons by 1.
            Rule(conditions=(ALWAYS,), effects=(PLUS_ONE_SKILL_MELEE,)),
            # Attacks by this unit, if it is BATTLELINE: improve AP by 1.
            Rule(conditions=(ATTACKER_IS_BATTLELINE,), effects=(IMPROVE_AP,)),
        ],
    },
}
