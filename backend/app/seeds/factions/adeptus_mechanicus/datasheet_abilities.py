from app.combat_rules import CommandChoice, Rule, RuleOption
from app.combat_rules.conditions import (
    ALWAYS,
    TARGET_HAS_CHARACTER,
    TARGET_LED_BY_CHARACTER,
)
from app.combat_rules.effects import (
    ADD_TWO_ATTACKS,
    ASSAULT,
    FEEL_NO_PAIN_4,
    FEEL_NO_PAIN_5,
    INVULNERABLE_4,
    MINUS_ONE_TO_WOUND,
    PLUS_ONE_TOUGHNESS,
    REROLL_FAILED_HITS,
    REROLL_HIT_ONES,
    REROLL_WOUND_ONES,
)
from app.seeds.datasheet_abilities import CORE_RULES
from app.seeds.factions.adeptus_mechanicus.conditions import (
    ATTACKER_NEAR_ADMECH_BATTLELINE,
    CONQUEROR_IMPERATIVE_ACTIVE,
    KASTELAN_MELEE_WEAPON,
    KASTELAN_RANGED_WEAPON,
    PROTECTOR_IMPERATIVE_ACTIVE,
    TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,
    TARGET_MODEL_DATASMITH_LEADING_KASTELANS,
    TARGET_MODEL_KASTELAN,
)

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
        "Dynamic Efficiency",
        "This unit is eligible to declare a charge in a turn in which it Advanced or Fell "
        "Back, and you can re-roll Desperate Escape tests taken for models in this unit.",
        [],
        [],
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
        # Its Icon of War abilities are in OPTIONS below.
        "Rod of the War Forge",
        "In your Command phase, select one of the abilities in the Icon of War section. Until "
        "the start of your next Command phase, this model has that ability. Fanatical "
        "Devotion: select one friendly SKITARII or THULIA GHULD unit within 6\" of this model; "
        "until the start of your next Command phase, that unit is eligible to shoot and "
        "declare a charge in a turn in which it Advanced. Adaptive Tactics: as Fanatical "
        "Devotion, but in a turn in which it Fell Back. The Fires of Mars: select one friendly "
        "SKITARII or THULIA GHULD unit within 6\" of this model; until the start of your next "
        "Command phase, the Conqueror Imperative and Protector Imperative are both active for "
        "that unit.",
        [],
        [],
    ),
    (
        "Secutor of Olympus",
        "At the start of your Shooting phase, select one enemy VEHICLE unit within 12\" of "
        "this model and roll one D6: on a 2+, that enemy unit suffers D3+1 mortal wounds.",
        [],
        [],
    ),
    (
        "Supreme Commander",
        "If this model is in your army, it must be your Warlord.",
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
    # Granted by detachment rules (see detachments.json).
    (
        "Murderous Imperative",
        "Each time a model in this unit makes an attack: if the Protector Imperative is active "
        "for this unit, re-roll a Hit roll of 1; if the Conqueror Imperative is active, "
        "re-roll a Wound roll of 1.",
        [],
        [],
    ),
    (
        "War-Form Mantle",
        "This model has a 4+ invulnerable save and the Feel No Pain 5+ ability.",
        [],
        [],
    ),
    (
        "Baffling Data Screed",
        "In your Shooting phase, when this unit is selected to shoot, if it is not "
        "Battle-shocked, you can roll one D6: on a 2+, select one enemy VEHICLE unit within "
        "12\" of this unit; that unit takes a Battle-shock test with -1 to it (a unit can't "
        "be selected for this more than once per turn). Or, on a 2+, those ranged attacks "
        "don't prevent this unit from being hidden.",
        [],
        [],
    ),
    (
        # Its protocols are in OPTIONS below.
        "Battle Protocols",
        "At the start of the battle, if this model is leading a KASTELAN ROBOTS unit, that unit "
        "enters the Aegis Protocol. In your Command phase, if this model is leading a KASTELAN "
        "ROBOTS unit, you can select one protocol for that unit to enter; it remains in it "
        "until it enters a different one. Protector Protocol: add 2 to the Attacks of ranged "
        "weapons equipped by KASTELAN ROBOT models in that unit. Conqueror Protocol: add 2 to "
        "the Attacks of their melee weapons. Aegis Protocol: add 1 to the Toughness of "
        "KASTELAN ROBOT models in that unit.",
        [],
        [],
    ),
    (
        "Data-severed",
        "If there are no KASTELAN ROBOT models in this unit, this unit loses VEHICLE and has "
        "INFANTRY.",
        [],
        [],
    ),
    (
        "Robotic Bodyguard",
        "While a CYBERNETICA DATASMITH model is leading this unit, that model has the Feel No "
        "Pain 4+ ability.",
        [],
        [],
    ),
    (
        "Repulsor Grid",
        "When an enemy unit targets this unit with ranged attacks, until that enemy unit has "
        "shot, each time this unit makes a save roll of an unmodified 6, that enemy unit "
        "suffers 1 mortal wound after it has shot.",
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
    "Dynamic Efficiency": "Descriptive only: charging and Desperate Escape aren't modelled.",
    "Voices in the Code": "Descriptive only: Battle-shock is outside the combat engine.",
    "Neurostatic Interference (Aura)": (
        "Descriptive only: Battle-shock/Leadership is outside the combat "
        "engine."
    ),
    "Mechanicus Bodyguard": "Descriptive only: targeting restrictions aren't modelled.",
    "Secutor of Olympus": (
        "Descriptive only: a start-of-Shooting-phase action outside the attack sequence."
    ),
    "Supreme Commander": "Descriptive only: an army-building restriction.",
    "Self-repair Mechanisms": (
        "Descriptive only in the calculator; in a game, the model regains D3 lost wounds at "
        "the start of its owner's Command phase."
    ),
    "Baffling Data Screed": "Descriptive only: Battle-shock and hiding are outside the calculator.",
    "Data-severed": (
        "Not modelled: a lone Datasmith keeps VEHICLE and doesn't gain INFANTRY in the "
        "calculator."
    ),
    "Repulsor Grid": "Not modelled: mortal wounds to the attacking unit aren't tracked.",
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
    "Murderous Imperative": [
        Rule(
            conditions=(PROTECTOR_IMPERATIVE_ACTIVE,),
            effects=(REROLL_HIT_ONES,),
            description="Re-roll Hit rolls of 1 while the Protector Imperative is picked.",
        ),
        Rule(
            conditions=(CONQUEROR_IMPERATIVE_ACTIVE,),
            effects=(REROLL_WOUND_ONES,),
            description="Re-roll Wound rolls of 1 while the Conqueror Imperative is picked.",
        ),
    ],
    "War-Form Mantle": [
        Rule(
            conditions=(ALWAYS,),
            effects=(INVULNERABLE_4,),
            side="defender",
            description="4+ invulnerable save.",
        ),
        Rule(
            conditions=(ALWAYS,),
            effects=(FEEL_NO_PAIN_5,),
            side="defender",
            description="Feel No Pain 5+.",
        ),
    ],
    "Robotic Bodyguard": [
        Rule(
            conditions=(TARGET_MODEL_DATASMITH_LEADING_KASTELANS,),
            effects=(FEEL_NO_PAIN_4,),
            side="defender",
            description=(
                "A CYBERNETICA DATASMITH in this unit (leading it) has Feel No Pain 4+; the "
                "Kastelans don't."
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
            aura_range=6.0,
            description=(
                "This model's unit, and other units of its faction in its army list, have "
                "Stealth (in a game, only those within 6\" of this model)."
            ),
        ),
    },
    "Rod of the War Forge": {
        "Fanatical Devotion": RuleOption(
            rules=(Rule(conditions=(ALWAYS,), effects=(ASSAULT,)),),
            army_wide=True,
            eligible_after=("advanced",),
            description=(
                "A SKITARII or THULIA GHULD unit within 6\" can shoot after Advancing - "
                "modelled as its ranged weapons having [ASSAULT] (the 6\" isn't modelled)."
            ),
        ),
        "Adaptive Tactics": RuleOption(
            army_wide=True,
            eligible_after=("fell_back",),
            description=(
                "Not modelled in the calculator: in a game, the unit can shoot and declare a "
                "charge after Falling Back."
            ),
        ),
        "The Fires of Mars": RuleOption(
            army_wide=True,
            grants_options=("Protector Imperative", "Conqueror Imperative"),
            description=(
                "A SKITARII or THULIA GHULD unit within 6\" has both the Protector and "
                "Conqueror Imperatives active (if it has Doctrina Imperatives; the 6\" isn't "
                "modelled)."
            ),
        ),
    },
    "Battle Protocols": {
        "Protector Protocol": RuleOption(
            rules=(Rule(conditions=(KASTELAN_RANGED_WEAPON,), effects=(ADD_TWO_ATTACKS,)),),
            description="+2 Attacks on KASTELAN ROBOT models' ranged weapons.",
        ),
        "Conqueror Protocol": RuleOption(
            rules=(Rule(conditions=(KASTELAN_MELEE_WEAPON,), effects=(ADD_TWO_ATTACKS,)),),
            description="+2 Attacks on KASTELAN ROBOT models' melee weapons.",
        ),
        "Aegis Protocol": RuleOption(
            rules=(
                Rule(
                    conditions=(TARGET_MODEL_KASTELAN,),
                    effects=(PLUS_ONE_TOUGHNESS,),
                    side="defender",
                ),
            ),
            description="+1 Toughness for KASTELAN ROBOT models when this unit is attacked.",
        ),
    },
}


# Abilities above whose option is selected in the Command phase, in a game
# (see CommandChoice): {ability name: CommandChoice}.
COMMAND_CHOICES = {
    "Canticles of the Omnissiah": CommandChoice(),
    "Rod of the War Forge": CommandChoice(
        target_keywords=("SKITARII", "THULIA GHULD"), target_range=6.0
    ),
    "Battle Protocols": CommandChoice(
        required=False, persistent=True, default="Aegis Protocol"
    ),
}

# Abilities above with which a model regains lost wounds at the start of its
# owner's Command phase, in a game: {ability name: the die rolled (D3)}.
COMMAND_HEALS = {
    "Self-repair Mechanisms": 3,
}
