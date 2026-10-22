from app.combat_rules import Rule
from app.combat_rules.conditions import MELEE_ATTACK, TARGET_TITANIC
from app.combat_rules.effects import (
    MINUS_ONE_TO_HIT,
    REROLL_FAILED_HITS,
    REROLL_FAILED_WOUNDS,
)

# Code-defined rules for Chaos Knights stratagems, by stratagem name - for the
# parts a stratagem's own conditions/effects (in stratagems.json) can't say.
# See app/seeds/stratagems.py, which combines every faction's.
RULES = {
    "Storm of Darkness": [
        Rule(
            conditions=(MELEE_ATTACK,),
            effects=(MINUS_ONE_TO_HIT,),
            side="defender",
            description="Melee attacks against your unit are -1 to hit.",
        ),
    ],
    "Titanic Duel": [
        Rule(
            conditions=(TARGET_TITANIC,),
            effects=(REROLL_FAILED_HITS, REROLL_FAILED_WOUNDS),
            description="Against a TITANIC unit, re-roll any failed Hit and Wound roll.",
        ),
    ],
}
