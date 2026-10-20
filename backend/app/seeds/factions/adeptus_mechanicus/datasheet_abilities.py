from app.combat_rules import Rule, RuleOption
from app.combat_rules.conditions import (
    ALWAYS,
    ATTACKER_NEAR_ADMECH_BATTLELINE,
    TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,
    TARGET_HAS_CHARACTER,
    TARGET_LED_BY_CHARACTER,
)
from app.combat_rules.effects import (
    ASSAULT,
    FEEL_NO_PAIN_4,
    FEEL_NO_PAIN_5,
    MINUS_ONE_TO_WOUND,
    REROLL_FAILED_HITS,
    REROLL_HIT_ONES,
)
from app.seeds.datasheet_abilities import CORE_RULES

# Adeptus Mechanicus datasheet abilities - see app/seeds/datasheet_abilities.py
# for what each of these holds. Core abilities (e.g. Stealth) are defined there.

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Electro-infusion",
        "While a CHARACTER model is leading this unit, each time an attack targets this unit, "
        "subtract 1 from the Wound roll.",
        [],
        [],
    ),
    (
        "Lord of the Machine Cult",
        "While this model is leading a unit, models in that unit have the Feel No Pain 5+ "
        "ability. If that unit has the ELECTRO-PRIESTS keyword, models in that unit have the "
        "Feel No Pain 4+ ability instead.",
        [],
        [],
    ),
    (
        "Data-spike",
        "At the start of the Fight phase, you can select one enemy VEHICLE unit within "
        "Engagement Range of this model's unit and roll one D6: on a 4+, that enemy unit "
        "suffers D6 mortal wounds and, until the end of the phase, the Weapon Skill "
        "characteristic of melee weapons equipped by that enemy unit is worsened by 1.",
        [],
        [],
    ),
    (
        "Breaching Command",
        "Each time a model in this unit makes an attack, re-roll a Hit roll of 1. While this "
        "unit is within 6\" of one or more friendly ADEPTUS MECHANICUS BATTLELINE units, you "
        "can re-roll the Hit roll instead.",
        [ALWAYS],
        [REROLL_HIT_ONES],
    ),
    (
        "Elevated Strider",
        "This unit is eligible to shoot in a turn in which it Fell Back or Advanced, and you "
        "can re-roll Desperate Escape tests taken for models in this unit.",
        [ALWAYS],
        [ASSAULT],
    ),
    (
        "Broad Spectrum Data-tether",
        "Each time you target this unit with a Stratagem, roll one D6: on a 5+, you gain 1CP.",
        [],
        [],
    ),
    (
        "Voices in the Code",
        "At the start of the Fight phase, each enemy unit within Engagement Range of one or more "
        "units with this ability must take a Battle-shock test.",
        [],
        [],
    ),
    (
        "Neurostatic Interference (Aura)",
        "While an enemy unit is within 6\" of this unit, each time a Battle-shock or Leadership "
        "test is taken for that unit, subtract 1 from that test. While this unit is within 6\" "
        "of one or more friendly ADEPTUS MECHANICUS BATTLELINE units, subtract 2 from that test "
        "instead.",
        [],
        [],
    ),
    (
        # Its options are in OPTIONS below.
        "Canticles of the Omnissiah",
        "At the start of your Command phase, select one of the abilities in the Canticles of "
        "the Omnissiah section. Until the start of your next Command phase, this model has that "
        "ability.",
        [],
        [],
    ),
    (
        "Mechanicus Bodyguard",
        "While this model is within 3\" of one or more other friendly ADEPTUS MECHANICUS units, "
        "this model has the Lone Operative ability.",
        [],
        [],
    ),
    (
        "Self-repair Mechanisms",
        "At the start of your Command phase, this model regains up to D3 lost wounds.",
        [],
        [],
    ),
]

# How the calculator handles abilities above, where that needs saying:
# {ability name: note}.
CALCULATOR_NOTES = {
    "Data-spike": (
        "Descriptive only: a start-of-Fight-phase action outside the attack "
        "sequence the combat engine resolves."
    ),
    "Elevated Strider": (
        "Shooting after Advancing is modelled as every weapon having [ASSAULT]; "
        "Falling Back and Desperate Escape aren't modelled."
    ),
    "Broad Spectrum Data-tether": "Descriptive only: gaining CP is outside the combat engine.",
    "Voices in the Code": "Descriptive only: Battle-shock is outside the combat engine.",
    "Neurostatic Interference (Aura)": (
        "Descriptive only: Battle-shock/Leadership is outside the combat "
        "engine."
    ),
    "Mechanicus Bodyguard": "Descriptive only: targeting restrictions aren't modelled.",
    "Self-repair Mechanisms": (
        "Descriptive only: healing between turns is outside the combat engine."
    ),
}

# Code-defined rules for abilities above, by name.
RULES = {
    "Electro-infusion": [
        Rule(
            conditions=(TARGET_HAS_CHARACTER,),
            effects=(MINUS_ONE_TO_WOUND,),
            side="defender",
            description=(
                "Attacks against this unit are -1 to wound while it contains a CHARACTER "
                "model (leader attachment isn't modelled)."
            ),
        ),
    ],
    "Lord of the Machine Cult": [
        Rule(
            conditions=(TARGET_LED_BY_CHARACTER,),
            effects=(FEEL_NO_PAIN_5,),
            side="defender",
            description=(
                "Feel No Pain 5+ while this CHARACTER is in a unit with other models "
                "(leading it)."
            ),
        ),
        Rule(
            conditions=(TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,),
            effects=(FEEL_NO_PAIN_4,),
            side="defender",
            description="Feel No Pain 4+ instead if that unit is ELECTRO-PRIESTS.",
        ),
    ],
    "Breaching Command": [
        Rule(
            conditions=(ATTACKER_NEAR_ADMECH_BATTLELINE,),
            effects=(REROLL_FAILED_HITS,),
            description=(
                "Re-roll any failed Hit roll, not just a 1, while within 6\" of a friendly "
                "ADEPTUS MECHANICUS BATTLELINE unit (ticked under Positioning)."
            ),
        ),
    ],
}

# Selectable options for abilities above: {ability name: {option name:
# RuleOption}}.
OPTIONS = {
    "Canticles of the Omnissiah": {
        "Invocation of Machine Vengeance": RuleOption(
            rules=(
                Rule(conditions=(ALWAYS,), effects=(REROLL_FAILED_HITS,)),
            ),
            army_wide=True,
            description=(
                "The defending unit is taken to be the Machine Vengeance target, so attacks "
                "against it by this model's unit, and other units of its faction in its army "
                "list, can re-roll the Hit roll (its range isn't modelled)."
            ),
        ),
        "Mantra of Discipline": RuleOption(
            keywords=("BATTLELINE",),
            description=(
                "This model's unit has BATTLELINE. (Binharic Courage, its OC/Battle-shock "
                "aura, is outside the calculator.)"
            ),
        ),
        "Shroudpsalm": RuleOption(
            rules=tuple(CORE_RULES["Stealth"]),
            army_wide=True,
            description=(
                "This model's unit, and other units of its faction in its army list, have "
                "Stealth (the 6\" range isn't modelled)."
            ),
        ),
    },
}
