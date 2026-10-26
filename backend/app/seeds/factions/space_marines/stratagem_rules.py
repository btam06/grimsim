from app.combat_rules import Rule
from app.combat_rules.effects import IMPROVE_AP
from app.seeds.factions.space_marines.conditions import ASSAULT_DOCTRINE_ACTIVE

# Code-defined rules for Space Marines stratagems, by stratagem name - for the
# parts a stratagem's own conditions/effects (in stratagems.json) can't say:
# here, a second tier that depends on the unit's combat doctrine. See
# app/seeds/stratagems.py, which combines every faction's.
RULES = {
    "Gene-Wrought Might": [
        Rule(
            conditions=(ASSAULT_DOCTRINE_ACTIVE,),
            effects=(IMPROVE_AP,),
            description="Melee attacks also get +1 AP while the Assault Doctrine is active.",
        ),
    ],
}
