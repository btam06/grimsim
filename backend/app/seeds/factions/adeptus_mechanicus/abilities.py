from app.combat_rules import Rule
from app.combat_rules.conditions import (
    ALWAYS,
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
from app.seeds.factions.adeptus_mechanicus.conditions import (
    ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
    MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
)

DOCTRINA_IMPERATIVES = "Doctrina Imperatives"

# (ability name, description)
ENTRIES = [
    (
        DOCTRINA_IMPERATIVES,
        "At the start of the battle round, you can select one of the Doctrina Imperatives "
        "below. Until the end of the battle round, that Doctrina Imperative is active for "
        "your army, and all units from your army that have the Doctrina Imperatives ability "
        "gain the relevant abilities shown below.\n"
        "Protector Imperative:\n"
        "- Ranged weapons equipped by models in this unit have the [HEAVY] ability.\n"
        "- Improve the Ballistic Skill characteristic of ranged weapons equipped by models in "
        "this unit by 1.\n"
        "- Each time a melee attack targets this unit, if this unit has the BATTLELINE keyword "
        "and/or it is within 6\" of one or more friendly ADEPTUS MECHANICUS BATTLELINE units, "
        "subtract 1 from the Hit roll.\n"
        "Conqueror Imperative:\n"
        "- Ranged weapons equipped by models in this unit have the [ASSAULT] ability.\n"
        "- Improve the Weapon Skill characteristic of melee weapons equipped by models in this "
        "unit by 1.\n"
        "- Each time a model in this unit makes an attack, if this unit has the BATTLELINE "
        "keyword and/or it is within 6\" of one or more friendly ADEPTUS MECHANICUS BATTLELINE "
        "units, improve the Armour Penetration characteristic of that attack by 1.",
    ),
]

# Abilities above whose options are required: one is always chosen - there's
# no "none" (Doctrina Imperatives: Protector or Conqueror).
REQUIRED_OPTIONS = {DOCTRINA_IMPERATIVES}

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
