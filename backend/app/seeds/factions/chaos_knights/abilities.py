from app.combat_rules import Rule
from app.combat_rules.conditions import DEFENDER_BATTLE_SHOCKED
from app.combat_rules.effects import PLUS_ONE_TO_WOUND
from app.seeds.datasheet_abilities import CORE_RULES

HARBINGERS_OF_DREAD = "Harbingers of Dread"

# (ability name, description)
ENTRIES = [
    (
        "Favoured Household",
        "The army pledges itself to a traitor Knight Household, granting a bonus ability in return for loyalty.",
    ),
    (
        # Its options (the Dread abilities that matter in combat) are in
        # OPTIONS below.
        HARBINGERS_OF_DREAD,
        "If your Army Faction is CHAOS KNIGHTS, each unit from your army with this ability gains "
        "Dread abilities, depending which are active for your army. Deathly Terror is active "
        "from the start of the battle. At the start of the first, third and fifth battle rounds, "
        "you can either select one of the other Dread abilities or randomly select two by "
        "rolling two D6. Selected Dread abilities are active until the end of the battle; none "
        "can be selected more than once, and duplicates have no additional effect.\n"
        "Deathly Terror (Aura): while an enemy unit is within 9\" of this model, worsen the "
        "Leadership characteristic of models in that unit by 1.\n"
        "1 Despair (Aura): while an enemy unit is within 9\" of this model, worsen the "
        "Leadership characteristic of models in that unit by 1 (cumulative with Deathly "
        "Terror).\n"
        "2 Doom: each time this model makes an attack, if the target of that attack is "
        "Battle-shocked, add 1 to the Wound roll.\n"
        "3 Darkness: this model has Stealth.\n"
        "4 Dismay (Aura): in the Battle-shock step of your opponent's Command phase, each enemy "
        "unit that is below its Starting Strength and within 9\" of this model must take a "
        "Battle-shock test.\n"
        "5 Delirium (Aura): while an enemy unit that is Below Half-strength is within 9\" of "
        "this model, each time that unit fails a Battle-shock test, it suffers D3 mortal "
        "wounds.\n"
        "6 Dominion: add 3\" to the range of this model's Aura abilities.",
    ),
    (
        "Super-heavy Walker",
        "Each time a model with this ability makes a Normal, Advance or Fall Back move, it can "
        "move through models (excluding TITANIC models) and sections of terrain features that "
        "are 4\" or less in height. When doing so it can move within Engagement Range of enemy "
        "models, but cannot end that move within Engagement Range of them. It can also move "
        "through sections of terrain features that are more than 4\" in height, but if it does, "
        "after it has moved, roll one D6: on a 1, that model is Battle-shocked.",
    ),
]

# Rule options for abilities above: {ability name: {option name: [Rule, ...]}}.
# The Dread abilities that matter in combat: Doom when attacking, Darkness when
# defending. (Deathly Terror, Despair, Dismay, Delirium and Dominion are
# Leadership/Battle-shock/aura effects outside the calculator.)
OPTIONS = {
    HARBINGERS_OF_DREAD: {
        "Doom": [
            Rule(
                conditions=(DEFENDER_BATTLE_SHOCKED,),
                effects=(PLUS_ONE_TO_WOUND,),
                description="+1 to wound against a target ticked as Battle-shocked under Modifiers.",
            ),
        ],
        "Darkness": [
            Rule(
                conditions=rule.conditions,
                effects=rule.effects,
                side=rule.side,
                description="This model has Stealth: ranged attacks against it treat it as in cover.",
            )
            for rule in CORE_RULES["Stealth"]
        ],
    },
}

# How the calculator handles abilities above, where that needs saying.
CALCULATOR_NOTES = {
    HARBINGERS_OF_DREAD: (
        "Pick Doom for an attacking unit, or Darkness for a defending one, under Faction "
        "Rules; the rest are Leadership and Battle-shock effects outside the calculator."
    ),
    "Super-heavy Walker": "Descriptive only: movement isn't modelled.",
}
