from app.combat_rules import Rule
from app.combat_rules.conditions import MELEE_ATTACK
from app.combat_rules.effects import ADD_EXTRA_ATTACK, REROLL_FAILED_WOUNDS
from app.seeds.factions.adepta_sororitas.conditions import ATTACKER_BELOW_HALF_STRENGTH
from app.seeds.factions.space_marines.conditions import MELEE_PRE_WEAPON

# Code-defined rules for Adepta Sororitas stratagems, by stratagem name - the
# parts a stratagem's own conditions/effects (in stratagems.json) can't say,
# since those are one set of conditions for all its effects. In play while the
# stratagem is used, for the side the rule names. See app/seeds/stratagems.py,
# which combines every faction's.
RULES = {
    "Righteous Vengeance": [
        Rule(
            conditions=(MELEE_ATTACK, ATTACKER_BELOW_HALF_STRENGTH),
            effects=(REROLL_FAILED_WOUNDS,),
            description="Melee attacks also re-roll the Wound roll while Below Half-strength.",
        ),
    ],
    "Sanctified Blows": [
        Rule(
            conditions=(MELEE_PRE_WEAPON,),
            effects=(ADD_EXTRA_ATTACK,),
            description="+1 Attacks for melee weapons.",
        ),
    ],
}
