from app.combat_rules import Rule
from app.combat_rules.conditions import ATTACKER_LED_BY_CHARACTER, TARGET_NOT_IMPERIUM_OR_CHAOS
from app.combat_rules.effects import PLUS_ONE_TO_HIT

# Imperial Agents datasheet abilities - see app/seeds/datasheet_abilities.py
# for what each of these holds.

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        # In a game, see TRANSPORT_AS_BODYGUARD below.
        "Authority of the Inquisition",
        "While this model is leading a unit, it can embark within any TRANSPORT that its "
        "Bodyguard unit can embark within.",
        [],
        [],
    ),
    (
        "Xenos Hunter",
        "While this model is leading a unit, each time a model in that unit makes an attack "
        "that targets an enemy unit that does not have the IMPERIUM or CHAOS keywords, add 1 "
        "to the Hit roll.",
        [],
        [],
    ),
    (
        # In a game, see PSYCHIC_ROLLS below.
        "Psychic Veil (Psychic)",
        "In your Command phase, this PSYKER can use this ability. If it does, roll one D6: on "
        "a 1, this PSYKER's unit suffers D3 mortal wounds; on a 2+, until the start of your "
        "next Command phase, this PSYKER's unit can only be selected as the target of a "
        "ranged attack if the attacking model is within 18\".",
        [],
        [],
    ),
]

# Code-defined rules for abilities above: {ability name: [Rule, ...]}.
RULES = {
    "Xenos Hunter": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER, TARGET_NOT_IMPERIUM_OR_CHAOS),
            effects=(PLUS_ONE_TO_HIT,),
            description=(
                "+1 to hit against a unit with no IMPERIUM or CHAOS model, while a CHARACTER is "
                "leading the unit."
            ),
        ),
    ],
}

# How the calculator handles abilities above, where that needs saying.
CALCULATOR_NOTES = {
    "Authority of the Inquisition": (
        "Descriptive only in the calculator; in a game, while leading a unit, its own keywords "
        "don't stop it embarking with that unit."
    ),
    "Psychic Veil (Psychic)": (
        "Descriptive only in the calculator; in a game, used in your Command phase (see "
        "app/services/in_game/psychic.py)."
    ),
}

# In a game: psychic abilities without a psychic level, and what their
# psychic roll does (see app/services/in_game/psychic.py) - Psychic Veil: a 1
# is D3 mortal wounds to its unit; otherwise it can only be targeted by ranged
# attacks from within 18" until its player's next Command phase.
PSYCHIC_ROLLS = {
    "Psychic Veil (Psychic)": {
        "when": "own_command",
        "fails_on": 1,
        "mortal_wounds": "D3",
        "targeted_within": 18.0,
    },
}

# In a game: abilities that let their model, while it's leading a unit, embark
# in any TRANSPORT its Bodyguard unit can (see app/services/in_game/embarked.py).
TRANSPORT_AS_BODYGUARD = {"Authority of the Inquisition"}
