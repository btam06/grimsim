from app.combat_rules import CommandChoice, Rule, RuleOption
from app.combat_rules.conditions import (
    ALWAYS,
    ATTACKER_LED_BY_CHARACTER,
    PRE_WEAPON,
    TARGET_HAS_CHARACTER,
    TARGET_MONSTER_OR_VEHICLE,
    TARGET_LED_BY_CHARACTER,
)
from app.combat_rules.effects import (
    ADD_THREE_ATTACKS,
    ADD_TWO_ATTACKS,
    ASSAULT,
    FEEL_NO_PAIN_4,
    FEEL_NO_PAIN_5,
    IGNORE_COVER,
    INVULNERABLE_4,
    MINUS_ONE_TO_WOUND,
    PLUS_ONE_TO_HIT,
    PLUS_ONE_TOUGHNESS,
    REROLL_FAILED_HITS,
    REROLL_HIT_ONES,
    REROLL_WOUND_ONES,
)
from app.seeds.datasheet_abilities import CORE_RULES
from app.seeds.factions.adeptus_mechanicus.conditions import (
    ATTACKER_NEAR_ADMECH_BATTLELINE,
    ATTACKER_OR_TARGET_ON_ACQUISITION,
    CONQUEROR_IMPERATIVE_ACTIVE,
    DEFENDER_ON_ACQUISITION,
    KASTELAN_MELEE_WEAPON,
    KASTELAN_RANGED_WEAPON,
    NEUTRON_FUSIL_WEAPON,
    OMNISSIAN_AXE_WEAPON,
    PROTECTOR_IMPERATIVE_ACTIVE,
    TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,
    TARGET_MODEL_DATASMITH_LEADING_KASTELANS,
    TARGET_MODEL_KASTELAN,
    TARGET_WITHIN_ACQUISITION,
    VENGEANCE_ACTIVE,
)

# Adeptus Mechanicus datasheet abilities - see app/seeds/datasheet_abilities.py
# for what each of these holds. Core abilities (e.g. Stealth) are defined there.

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Control Edict",
        "While this model is leading a unit, each time a model in that unit makes an attack, "
        "you can re-roll the Hit roll.",
        [],
        [],
    ),
    (
        # In a game, see RALLIES below.
        "Servo-skull Uplink",
        "Once per battle, at the start of any phase, you can select one friendly SKITARII unit "
        "that is Battle-shocked and within 6\" of this model. That unit is no longer "
        "Battle-shocked.",
        [],
        [],
    ),
    (
        "Enginseer",
        "While this model is within 3\" of one or more friendly ADEPTUS MECHANICUS VEHICLE "
        "units, unless it is leading a unit, this model has the Lone Operative ability.",
        [],
        [],
    ),
    (
        # In a game, see REPAIRS below.
        "Omnissiah's Blessing",
        "In your Command phase, select one friendly ADEPTUS MECHANICUS model within 3\" of "
        "this model. That model regains up to D3 lost wounds and, if it is a VEHICLE model, "
        "until the start of your next Command phase, that model has the Feel No Pain 5+ "
        "ability. Each model can only be selected for this ability once per Command phase.",
        [],
        [],
    ),
    (
        # In a game, see app/seeds/factions/adeptus_mechanicus/vengeance.py.
        "Vengeance for the Omnissiah",
        "If a friendly ADEPTUS MECHANICUS VEHICLE model is destroyed within 12\" of this model, "
        "until the end of the battle, this model's Omnissian axe has an Attacks characteristic "
        "of 6.",
        [],
        [],
    ),
    (
        # In a game, see REACTIVE_MOVES below.
        "Tactica Obliqua",
        "In your opponent's Movement phase, if an enemy unit ends a move within 8\" of this "
        "unit, if this unit is not within Engagement Range of one or more enemy units, it can "
        "do one of the following: make a Normal move of up to D6\"; or make a Normal move of "
        "up to 6\" provided every model in this unit ends that move wholly within 6\" of one "
        "or more friendly ADEPTUS MECHANICUS BATTLELINE units.",
        [],
        [],
    ),
    (
        "Monocular Targeting Helms",
        "Each time a model in this unit makes an attack with a neutron fusil against a MONSTER "
        "or VEHICLE unit, that attack has the [IGNORES COVER] ability.",
        [],
        [],
    ),
    (
        # In a game, see SHOOT_SCOOT below.
        "Ride the Thermals",
        "In your Shooting phase, after this unit has shot, if it is not within Engagement Range "
        "of one or more enemy units, it can do one of the following: make a Normal move of up "
        "to 6\"; or make a Normal move of up to 12\", provided every model in this unit ends "
        "that move wholly within 6\" of one or more friendly ADEPTUS MECHANICUS BATTLELINE "
        "units. In either case, if it does, until the end of the turn, this unit is not "
        "eligible to declare a charge.",
        [],
        [],
    ),
    (
        # In a game, see app/seeds/factions/adeptus_mechanicus/fire_support.py.
        "Fire Support",
        "In your Shooting phase, after this model has shot, select one enemy unit it scored one "
        "or more hits against this phase. Until the end of the phase, each time a friendly "
        "model that disembarked from this Transport this turn makes an attack that targets "
        "that enemy unit, you can re-roll the Wound roll.",
        [],
        [],
    ),
    (
        # In a game, see ROLL_BONUSES below.
        "Optimised Gait",
        "Add 1 to Advance and Charge rolls made for this unit. While this unit is within 6\" of "
        "one or more friendly ADEPTUS MECHANICUS BATTLELINE units, add 2 to Advance and Charge "
        "rolls made for this unit instead.",
        [],
        [],
    ),
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
        "Objective Scouted",
        "At the end of your Command phase, if this unit is within range of an objective marker "
        "you control, that objective marker remains under your control until your opponent's "
        "Level of Control over that objective marker is greater than yours at the end of a "
        "phase.",
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
        # Explorator Maniple's detachment rule. In a game, the Acquisition
        # objective marker is selected in the Command phase (see
        # app/services/in_game/selected_objectives.py).
        "Acquisition At Any Cost",
        "Each time a model in this unit makes an attack, if this unit is within range of your "
        "Acquisition objective marker, or if the target of that attack is within range of your "
        "Acquisition objective marker, re-roll a Wound roll of 1.",
        [],
        [],
    ),
    (
        # The Genetor enhancement, for the unit its bearer leads.
        "Genetor",
        "While the bearer is leading a unit that is within range of your Acquisition objective "
        "marker, models in that unit have a 4+ invulnerable save.",
        [],
        [],
    ),
    (
        # The Logis enhancement, likewise.
        "Logis",
        "While the bearer is leading a unit, each time a model in that unit makes an attack "
        "that targets a unit within range of your Acquisition objective marker, add 1 to the "
        "Hit roll.",
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
    "Servo-skull Uplink": (
        "Descriptive only in the calculator; in a game, once per battle it rallies a friendly "
        "Battle-shocked SKITARII unit within 6\"."
    ),
    "Enginseer": (
        "Descriptive only in the calculator; in a game, models more than 12\" away can't shoot "
        "it while it's within 3\" of a friendly ADEPTUS MECHANICUS VEHICLE unit and not "
        "leading one."
    ),
    "Omnissiah's Blessing": (
        "Descriptive only in the calculator; in a game, used in your Command phase on a model "
        "within 3\"."
    ),
    "Tactica Obliqua": (
        "Descriptive only in the calculator; in a game, a move in your opponent's Movement "
        "phase (see app/services/in_game/reactive_move.py) - once that phase."
    ),
    "Ride the Thermals": (
        "Descriptive only in the calculator; in a game, a move after shooting (see "
        "app/services/in_game/shoot_scoot.py)."
    ),
    "Fire Support": (
        "Descriptive only in the calculator; in a game, units that disembarked from it re-roll "
        "Wound rolls against the unit it hit this Shooting phase."
    ),
    "Optimised Gait": (
        "Descriptive only in the calculator; in a game, added to its Advance and charge rolls."
    ),
    "Data-spike": (
        "Descriptive only: a start-of-Fight-phase action outside the attack "
        "sequence the combat engine resolves."
    ),
    "Elevated Strider": (
        "Shooting after Advancing is modelled as every weapon having [ASSAULT]; "
        "Falling Back and Desperate Escape aren't modelled."
    ),
    "Broad Spectrum Data-tether": (
        "Descriptive only in the calculator; in a game, a Stratagem used on its unit (with a "
        "unit target, or Rapid Ingress) rolls for the CP."
    ),
    "Dynamic Efficiency": "Descriptive only: charging and Desperate Escape aren't modelled.",
    "Voices in the Code": "Descriptive only: Battle-shock is outside the combat engine.",
    "Neurostatic Interference (Aura)": (
        "Descriptive only: Battle-shock/Leadership is outside the combat "
        "engine."
    ),
    "Mechanicus Bodyguard": (
        "Descriptive only in the calculator; in a game, models more than 12\" away can't shoot "
        "it while it's within 3\" of another friendly ADEPTUS MECHANICUS unit."
    ),
    "Secutor of Olympus": (
        "Descriptive only in the calculator; in a game, used at the start of your Shooting "
        "phase (see app/services/in_game/shooting_start.py)."
    ),
    "Supreme Commander": "Descriptive only: an army-building restriction.",
    "Objective Scouted": (
        "Descriptive only in the calculator; in a game, objectives it's controlling at the end "
        "of your Command phase are secured."
    ),
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
    "Acquisition At Any Cost": (
        "Tick whether the unit, or its target, is within range of the Acquisition objective "
        "marker under Positioning; in a game, it's selected in your Command phase."
    ),
}

# Code-defined rules for abilities above, by name.
RULES = {
    "Control Edict": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER,),
            effects=(REROLL_FAILED_HITS,),
            description="Re-roll Hit rolls while a CHARACTER is leading the unit.",
        ),
    ],
    "Vengeance for the Omnissiah": [
        Rule(
            conditions=(PRE_WEAPON, OMNISSIAN_AXE_WEAPON, VENGEANCE_ACTIVE),
            effects=(ADD_THREE_ATTACKS,),
            description=(
                "The Omnissian axe has 6 Attacks once a friendly ADEPTUS MECHANICUS VEHICLE "
                "model was destroyed within 12\" (ticked under Positioning)."
            ),
        ),
    ],
    "Monocular Targeting Helms": [
        Rule(
            conditions=(NEUTRON_FUSIL_WEAPON, TARGET_MONSTER_OR_VEHICLE),
            effects=(IGNORE_COVER,),
            description="Neutron fusils ignore cover against MONSTER or VEHICLE units.",
        ),
    ],
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
    "Acquisition At Any Cost": [
        Rule(
            conditions=(ATTACKER_OR_TARGET_ON_ACQUISITION,),
            effects=(REROLL_WOUND_ONES,),
            description=(
                "Re-roll Wound rolls of 1 while the unit, or its target, is within range of the "
                "Acquisition objective marker."
            ),
        ),
    ],
    "Genetor": [
        Rule(
            conditions=(DEFENDER_ON_ACQUISITION,),
            effects=(INVULNERABLE_4,),
            side="defender",
            description="A 4+ invulnerable save within range of the Acquisition objective marker.",
        ),
    ],
    "Logis": [
        Rule(
            conditions=(TARGET_WITHIN_ACQUISITION,),
            effects=(PLUS_ONE_TO_HIT,),
            description="+1 to hit against units within range of the Acquisition objective marker.",
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
            targets_enemy=True,
            description=(
                "The defending unit is taken to be the Machine Vengeance target, so attacks "
                "against it by this model's unit, and other units of its faction in its army "
                "list, can re-roll the Hit roll. In a game, the target is the enemy unit "
                "selected with it (anywhere on the battlefield; it needn't be visible)."
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
                "The SKITARII or THULIA GHULD unit chosen (within 6\" of Thulia) can shoot "
                "after Advancing - its ranged weapons have [ASSAULT]. Pick it for that unit; in "
                "a game, it's chosen in the Command phase."
            ),
        ),
        "Adaptive Tactics": RuleOption(
            army_wide=True,
            eligible_after=("fell_back",),
            description=(
                "Not modelled in the calculator: in a game, the SKITARII or THULIA GHULD unit "
                "chosen (within 6\" of Thulia) can shoot and declare a charge after Falling "
                "Back."
            ),
        ),
        "The Fires of Mars": RuleOption(
            army_wide=True,
            grants_options=("Protector Imperative", "Conqueror Imperative"),
            description=(
                "The SKITARII or THULIA GHULD unit chosen (within 6\" of Thulia) has both the "
                "Protector and Conqueror Imperatives active (if it has Doctrina Imperatives). "
                "Pick it for that unit; in a game, it's chosen in the Command phase."
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

# In a game: abilities that give their unit Lone Operative while within a
# distance of a friendly unit with some keywords (see
# app/services/in_game/shooting.py).
# (A third value of True: only while it isn't leading a unit.)
CONDITIONAL_LONE_OPERATIVE = {
    "Mechanicus Bodyguard": (3.0, ("ADEPTUS MECHANICUS",)),
    "Enginseer": (3.0, ("ADEPTUS MECHANICUS", "VEHICLE"), True),
}

# In a game: abilities that secure the objectives their unit is controlling at
# the end of one of their player's phases (see
# app/services/in_game/objectives.py).
SECURES_OBJECTIVES = {"Objective Scouted": "command"}

# In a game: abilities that let their unit move after shooting (see
# app/services/in_game/shoot_scoot.py) - Ride the Thermals: 6", or 12" if
# every model ends wholly within 6" of a friendly ADEPTUS MECHANICUS
# BATTLELINE unit; then no charge this turn.
SHOOT_SCOOT = {
    "Ride the Thermals": {
        "reach": 6.0,
        "further": (12.0, ("ADEPTUS MECHANICUS", "BATTLELINE"), 6.0),
        "no_charge": True,
    },
}

# In a game: abilities that add to their unit's Advance and charge rolls (see
# app/services/in_game/movement.py roll_bonus) - Optimised Gait: +1, or +2
# within 6" of a friendly ADEPTUS MECHANICUS BATTLELINE unit.
ROLL_BONUSES = {
    "Optimised Gait": {
        "rolls": ("advance", "charge"),
        "bonus": 1,
        "near": (("ADEPTUS MECHANICUS", "BATTLELINE"), 6.0, 2),
    },
}

# In a game: abilities that gain their player 1CP on a D6 roll of at least
# this, each time a Stratagem targets their unit - Broad Spectrum Data-tether.
STRATAGEM_TARGET_CP = {"Broad Spectrum Data-tether": 5, "Enhanced data-tether": 5}

# In a game: abilities that rally a friendly Battle-shocked unit (see
# app/services/in_game/rally.py) - Servo-skull Uplink.
RALLIES = {
    "Servo-skull Uplink": {"keywords": ("SKITARII",), "range": 6.0, "once_per_battle": True},
}

# In a game: abilities that repair a friendly model in their player's Command
# phase (see app/services/in_game/repair.py) - Omnissiah's Blessing.
REPAIRS = {
    "Omnissiah's Blessing": {
        "keywords": ("ADEPTUS MECHANICUS",),
        "range": 3.0,
        "heal": "D3",
        "vehicle_feel_no_pain": 5,
    },
}

# In a game: abilities that let their unit move in its opponent's Movement
# phase (see app/services/in_game/reactive_move.py) - Tactica Obliqua: D6",
# or 6" ending wholly within 6" of a friendly ADEPTUS MECHANICUS BATTLELINE
# unit.
REACTIVE_MOVES = {
    "Tactica Obliqua": {
        "trigger_range": 8.0,
        "reach": "D6",
        "further": (6.0, ("ADEPTUS MECHANICUS", "BATTLELINE"), 6.0),
    },
}

# In a game: abilities used at the start of their player's Shooting phase on an
# enemy unit (see app/services/in_game/shooting_start.py) - Secutor of
# Olympus: an enemy VEHICLE unit within 12", on a 2+ D3+1 mortal wounds.
START_OF_SHOOTING = {
    "Secutor of Olympus": {
        "target_keywords": ("VEHICLE",),
        "range": 12.0,
        "roll": 2,
        "mortal_wounds": "D3+1",
    },
}
