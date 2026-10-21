from app.combat_rules import Rule
from app.combat_rules.conditions import ATTACKER_LED_BY_CHARACTER, DEFENDER_BELOW_HALF_STRENGTH
from app.combat_rules.effects import (
    IGNORE_WOUND_PENALTIES,
    IMPROVE_AP,
    INVULNERABLE_4,
    PLUS_ONE_TO_WOUND,
    REROLL_FAILED_HITS,
    REROLL_WOUND_ONES,
)
from app.seeds.factions.necrons.conditions import (
    ATTACKER_IS_CRYPTEK,
    HALF_RANGE_ATTACK_LED_BY_CHARACTER,
    TARGET_IMMORTALS,
    TARGET_IS_UNRAVELLING,
)

# Code-defined rules for Necrons stratagems, by stratagem name - for the parts a
# stratagem's own conditions/effects (in stratagems.json) can't say, since
# those apply all their effects when any condition matches: chiefly a second
# tier, e.g. "if a NECRONS CHARACTER is leading your unit, ... instead". In
# play while the stratagem is used, for the side the rule names. See
# app/seeds/stratagems.py, which combines every faction's.
RULES = {
    "Protocol of the Hungry Void": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER,),
            effects=(IMPROVE_AP,),
            description="Melee attacks also get +1 AP while a CHARACTER is leading the unit.",
        ),
    ],
    "Protocol of the Conquering Tyrant": [
        Rule(
            conditions=(HALF_RANGE_ATTACK_LED_BY_CHARACTER,),
            effects=(REROLL_FAILED_HITS,),
            description=(
                "Within half range, re-roll any failed Hit roll while a CHARACTER is leading "
                "the unit."
            ),
        ),
    ],
    "The Spoor of Frailty": [
        Rule(
            conditions=(DEFENDER_BELOW_HALF_STRENGTH,),
            effects=(PLUS_ONE_TO_WOUND,),
            description="+1 to wound when the target is ticked as Below Half-strength.",
        ),
    ],
    "Molecular Targeting": [
        Rule(
            conditions=(ATTACKER_IS_CRYPTEK,),
            effects=(IGNORE_WOUND_PENALTIES,),
            description="A CRYPTEK unit also ignores penalties to its Wound rolls.",
        ),
    ],
    "Entrophasic Aura Targeting": [
        Rule(
            conditions=(TARGET_IS_UNRAVELLING,),
            effects=(REROLL_WOUND_ONES,),
            description="Also re-roll Wound rolls of 1 against a target ticked as unravelling.",
        ),
    ],
    "Microscarab Swarm": [
        Rule(
            conditions=(TARGET_IMMORTALS,),
            effects=(INVULNERABLE_4,),
            side="defender",
            description="An IMMORTALS unit has a 4+ invulnerable save.",
        ),
    ],
}
