from app.combat_rules import Rule, RuleOption
from app.combat_rules.conditions import (
    ALWAYS,
    ATTACKER_LED_BY_CHARACTER,
    CRITICAL_WOUND,
    DEFENDER_IN_RANGE_OF_OBJECTIVE,
    MELEE_ATTACK,
    TARGET_MODEL_CHARACTER,
)
from app.combat_rules.effects import (
    ADD_EXTRA_HIT,
    CRITICAL_HIT_5,
    FEEL_NO_PAIN_MORTAL_5,
    REROLL_FAILED_WOUNDS,
    FEEL_NO_PAIN_4,
    IMPROVE_AP,
    MINUS_ONE_DAMAGE,
    MINUS_ONE_TO_HIT,
    PLUS_ONE_TO_HIT,
    PLUS_ONE_TO_WOUND,
    PLUS_TWO_STRENGTH,
    REROLL_FAILED_HITS,
    REROLL_HIT_ONES,
    REROLL_WOUND_ONES,
)
from app.seeds.factions.necrons.conditions import (
    ATTACKER_IN_POWER_MATRIX,
    ATTACKER_SET_UP_THIS_TURN,
    CHARACTER_VS_BELOW_HALF_STRENGTH,
    MURDER_MADNESS_CRITICAL_HIT,
    PROPHET_OF_DESTRUCTION_TARGET,
    RANGED_ATTACK_LED_BY_CHARACTER,
    RANGED_VS_CLOSEST,
    RANGED_VS_CLOSEST_ON_OBJECTIVE,
    COLD_FERVOUR_SPREAD,
    DESTROYER_CULT_RANGED_VS_CLOSEST,
    NON_MONSTER_VS_OBJECTIVE_TARGET,
    RANGED_ATTACK_SET_UP_THIS_TURN,
    TARGET_IS_UNRAVELLING,
    TARGET_IS_WORTHY_FOE,
)

# Necrons datasheet abilities - see app/seeds/datasheet_abilities.py for what
# each of these holds. Core abilities (e.g. Stealth) are defined there.

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Necrodermis",
        "Each time an attack is allocated to this model, subtract 1 from the Damage "
        "characteristic of that attack.",
        [],
        [],
    ),
    (
        "Matter Absorption",
        "At the start of your Shooting phase, select one enemy VEHICLE unit within 12\" of this "
        "model and roll one D6: on a 2+, that enemy unit suffers D3 mortal wounds and this model "
        "regains up to that many lost wounds.",
        [],
        [],
    ),
    (
        "Enslaved Star God",
        "This model cannot be your WARLORD.",
        [],
        [],
    ),
    (
        "Destroyer Cult",
        "While this model is leading a unit, each time a model in that unit makes a ranged "
        "attack, a successful unmodified Hit roll of 5+ scores a Critical Hit.",
        [],
        [],
    ),
    (
        "Driven by Hatred",
        "Each time this model makes an attack that targets an enemy unit that is Below "
        "Half-strength, you can re-roll the Hit roll and you can re-roll the Wound roll.",
        [],
        [],
    ),
    (
        "Resurrection Orb",
        "(Once per battle, per unit) At the end of any phase, you can use this ability. If you "
        "do, this unit resurrects: its Reanimation Protocols activate, but it heals D6 wounds "
        "(instead of D3 wounds). You cannot resurrect more than one unit per turn.",
        [],
        [],
    ),
    (
        "Hard-wired for Destruction",
        "Each time a model in this unit makes a ranged attack that targets the closest "
        "eligible enemy unit, re-roll a Hit roll of 1. If the target of that attack is within "
        "range of an objective marker your opponent controls, you can re-roll the Hit roll "
        "instead.",
        [],
        [],
    ),
    (
        "Protective Disciples",
        "While this model is within 3\" of one or more other friendly DESTROYER CULT units, "
        "this model has the Lone Operative ability.",
        [],
        [],
    ),
    (
        # Its option is in OPTIONS below.
        "Infectious Murder-madness (Aura)",
        "While a friendly NECRONS unit (excluding MONSTER and TITANIC units) is within 6\" of "
        "this model, each time a model in that unit makes an attack, if that model has the "
        "DESTROYER CULT keyword or that enemy unit is the closest eligible target, that attack "
        "has the [SUSTAINED HITS 1] ability.",
        [],
        [],
    ),
    (
        "Prophet of Destruction",
        "Each time this model destroys an enemy unit, select one other friendly DESTROYER CULT "
        "unit within 9\" of it. Until the end of the phase, each time a model in that unit "
        "makes an attack, re-roll a Wound roll of 1.",
        [],
        [],
    ),
    (
        # Its option is in OPTIONS below.
        "Nullstone Field Generator (Aura)",
        "While a friendly NECRONS unit is within 6\" of the bearer, models in that unit have "
        "the Feel No Pain 5+ ability against mortal wounds and Psychic Attacks.",
        [],
        [],
    ),
    # Granted by detachment rules (see detachments.json).
    (
        "Command Protocols",
        "While a NECRONS CHARACTER model is leading this unit, each time a model in this unit "
        "makes an attack, add 1 to the Hit roll.",
        [],
        [],
    ),
    (
        "Annihilation Protocol",
        "Each time a DESTROYER CULT model in this unit makes a ranged attack that targets the "
        "closest eligible target, add 1 to the Armour Penetration characteristic of that "
        "attack.",
        [],
        [],
    ),
    (
        "Power Matrix",
        "Each time a model in this unit makes an attack, re-roll a Hit roll of 1. If this unit "
        "is wholly within your army's Power Matrix, you can re-roll the Hit roll instead.",
        [ALWAYS],
        [REROLL_HIT_ONES],
    ),
    (
        "Worthy Foes",
        "Each time a model in this unit makes an attack that targets the enemy unit selected "
        "for Worthy Foes, add 1 to the Wound roll.",
        [],
        [],
    ),
    (
        "Relentless Onslaught",
        "Each time a NECRONS model (excluding MONSTER models) in this unit makes an attack "
        "that targets a unit within range of one or more objective markers, add 1 to the Hit "
        "roll.",
        [],
        [],
    ),
    (
        "Cold Fervour",
        "Add 2 to the Strength characteristic of weapons equipped by DESTROYER CULT models in "
        "this unit.",
        [ALWAYS],
        [PLUS_TWO_STRENGTH],
    ),
    (
        "Cold Fervour (Spread)",
        "The first time each turn that a DESTROYER CULT unit from your army destroys a unit or "
        "causes it to become Below Half-strength, until the end of the turn, add 2 to the "
        "Strength characteristic of weapons equipped by friendly NECRONS models (excluding "
        "DESTROYER CULT, MONSTER and TITANIC models).",
        [],
        [],
    ),
    (
        "Cosmic Distortion",
        "Distortion Fields (Aura): while an enemy unit is within 6\" of a NECRONS MONSTER unit "
        "from your army, it is unravelling. While an enemy unit is unravelling, each time an "
        "attack targets that unit, improve the Armour Penetration characteristic of that attack "
        "by 1.",
        [],
        [],
    ),
    (
        "Transdimensional Deployment",
        "This unit has Deep Strike. When this unit is selected to shoot, if it made an ingress "
        "move this turn, its ranged attacks have +1 to hit rolls.",
        [],
        [],
    ),
    # Granted by enhancements (see enhancements.json).
    (
        "Enaegic Dermal Bond",
        "The bearer has the Feel No Pain 4+ ability.",
        [],
        [],
    ),
    (
        "Ingrained Superiority",
        "Each time a model in this unit makes an attack, on a Critical Wound, improve the "
        "Armour Penetration characteristic of that attack by 1.",
        [CRITICAL_WOUND],
        [IMPROVE_AP],
    ),
    (
        "Hyperphasic Fulcrum",
        "While this unit is wholly within your army's Power Matrix, each time a model in this "
        "unit makes an attack, re-roll a Wound roll of 1.",
        [],
        [],
    ),
    (
        "Warrior Noble",
        "Each time a melee attack targets this unit, subtract 1 from the Hit roll.",
        [],
        [],
    ),
    (
        "Eternal Conqueror",
        "Each time a model in this unit makes an attack that targets an enemy unit within "
        "range of an objective marker, you can re-roll the Hit roll.",
        [DEFENDER_IN_RANGE_OF_OBJECTIVE],
        [REROLL_FAILED_HITS],
    ),
    (
        "Arisen Tyrant",
        "Each time a model in this unit makes an attack, re-roll a Hit roll of 1. If this unit "
        "was set up on the battlefield this turn, you can re-roll the Hit roll instead.",
        [ALWAYS],
        [REROLL_HIT_ONES],
    ),
    (
        "Mark of the Nekrosor",
        "Each time a model in this unit makes an attack, add 1 to the Hit roll.",
        [ALWAYS],
        [PLUS_ONE_TO_HIT],
    ),
]

# Code-defined rules for abilities above, by name.
RULES = {
    "Destroyer Cult": [
        Rule(
            conditions=(RANGED_ATTACK_LED_BY_CHARACTER,),
            effects=(CRITICAL_HIT_5,),
            description=(
                "Ranged attacks score Critical Hits on a 5+ while this unit has a CHARACTER and "
                "other models (this model leading it)."
            ),
        ),
    ],
    "Driven by Hatred": [
        Rule(
            conditions=(CHARACTER_VS_BELOW_HALF_STRENGTH,),
            effects=(REROLL_FAILED_HITS, REROLL_FAILED_WOUNDS),
            description=(
                "This model's attacks re-roll failed Hit and Wound rolls when the target is "
                "ticked as Below Half-strength."
            ),
        ),
    ],
    "Hard-wired for Destruction": [
        Rule(
            conditions=(RANGED_VS_CLOSEST,),
            effects=(REROLL_HIT_ONES,),
            description=(
                "Ranged attacks re-roll Hit rolls of 1 when Targeting the closest eligible "
                "target is ticked under Positioning."
            ),
        ),
        Rule(
            conditions=(RANGED_VS_CLOSEST_ON_OBJECTIVE,),
            effects=(REROLL_FAILED_HITS,),
            description=(
                "...and any failed Hit roll if the defender is also ticked as within range of "
                "an objective marker (who controls it isn't tracked)."
            ),
        ),
    ],
    "Necrodermis": [
        Rule(
            conditions=(ALWAYS,),
            effects=(MINUS_ONE_DAMAGE,),
            side="defender",
            description="Attacks against this unit have -1 Damage (to a minimum of 1).",
        ),
    ],
    "Command Protocols": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER,),
            effects=(PLUS_ONE_TO_HIT,),
            description=(
                "+1 to hit while this unit has a CHARACTER and other models (a CHARACTER "
                "leading it)."
            ),
        ),
    ],
    "Annihilation Protocol": [
        Rule(
            conditions=(DESTROYER_CULT_RANGED_VS_CLOSEST,),
            effects=(IMPROVE_AP,),
            description=(
                "DESTROYER CULT models' ranged attacks get +1 AP when Targeting the closest "
                "eligible target is ticked under Positioning."
            ),
        ),
    ],
    "Power Matrix": [
        Rule(
            conditions=(ATTACKER_IN_POWER_MATRIX,),
            effects=(REROLL_FAILED_HITS,),
            description=(
                "Re-roll any failed Hit roll, not just a 1, when Wholly within the Power "
                "Matrix is ticked under Positioning."
            ),
        ),
    ],
    "Worthy Foes": [
        Rule(
            conditions=(TARGET_IS_WORTHY_FOE,),
            effects=(PLUS_ONE_TO_WOUND,),
            description=(
                "+1 to wound when the target is ticked as the Worthy Foes unit under "
                "Positioning."
            ),
        ),
    ],
    "Relentless Onslaught": [
        Rule(
            conditions=(NON_MONSTER_VS_OBJECTIVE_TARGET,),
            effects=(PLUS_ONE_TO_HIT,),
            description=(
                "+1 to hit for non-MONSTER models when the defender is ticked as within range "
                "of an objective marker under Positioning."
            ),
        ),
    ],
    "Cold Fervour (Spread)": [
        Rule(
            conditions=(COLD_FERVOUR_SPREAD,),
            effects=(PLUS_TWO_STRENGTH,),
            description=(
                "+2 Strength for models other than DESTROYER CULT, MONSTER and TITANIC ones, "
                "when Cold Fervour triggered is ticked under Positioning."
            ),
        ),
    ],
    "Cosmic Distortion": [
        Rule(
            conditions=(TARGET_IS_UNRAVELLING,),
            effects=(IMPROVE_AP,),
            description=(
                "+1 AP against a target ticked as unravelling under Positioning (any of the "
                "army's attacks benefit, not only the MONSTER's)."
            ),
        ),
    ],
    "Transdimensional Deployment": [
        Rule(
            conditions=(RANGED_ATTACK_SET_UP_THIS_TURN,),
            effects=(PLUS_ONE_TO_HIT,),
            description=(
                "Ranged attacks get +1 to hit when Set up on the battlefield this turn is "
                "ticked under Positioning."
            ),
        ),
    ],
    "Enaegic Dermal Bond": [
        Rule(
            conditions=(TARGET_MODEL_CHARACTER,),
            effects=(FEEL_NO_PAIN_4,),
            side="defender",
            description=(
                "Feel No Pain 4+ for the CHARACTER models in the bearer's unit (the bearer), "
                "not the models it's leading."
            ),
        ),
    ],
    "Hyperphasic Fulcrum": [
        Rule(
            conditions=(ATTACKER_IN_POWER_MATRIX,),
            effects=(REROLL_WOUND_ONES,),
            description=(
                "Re-roll Wound rolls of 1 when Wholly within the Power Matrix is ticked under "
                "Positioning."
            ),
        ),
    ],
    "Warrior Noble": [
        Rule(
            conditions=(MELEE_ATTACK,),
            effects=(MINUS_ONE_TO_HIT,),
            side="defender",
            description="Melee attacks against this unit are -1 to hit.",
        ),
    ],
    "Arisen Tyrant": [
        Rule(
            conditions=(ATTACKER_SET_UP_THIS_TURN,),
            effects=(REROLL_FAILED_HITS,),
            description=(
                "Re-roll any failed Hit roll, not just a 1, when Set up this turn is ticked "
                "under Positioning."
            ),
        ),
    ],
}

# How the calculator handles abilities above, where that needs saying:
# {ability name: note}.
CALCULATOR_NOTES = {
    "Resurrection Orb": "Descriptive only: healing between attacks isn't modelled.",
    "Protective Disciples": "Descriptive only: targeting restrictions aren't modelled.",
    "Matter Absorption": (
        "Descriptive only: a start-of-Shooting-phase action outside the attack sequence."
    ),
    "Enslaved Star God": "Descriptive only: an army-building restriction.",
    "Command Protocols": (
        "Leader attachment is approximated: a unit with a CHARACTER model and other models "
        "counts as led."
    ),
}

# Selectable options for abilities above: {ability name: {option name:
# RuleOption}}. Aura ranges aren't modelled: picking one means the unit is
# within range.
OPTIONS = {
    "Infectious Murder-madness (Aura)": {
        "Infectious Murder-madness": RuleOption(
            rules=(Rule(conditions=(MURDER_MADNESS_CRITICAL_HIT,), effects=(ADD_EXTRA_HIT,)),),
            army_wide=True,
            description=(
                "This unit, or another NECRONS unit in the army list, is within 6\": attacks by "
                "DESTROYER CULT models, or against a target ticked as the closest eligible "
                "target, have [SUSTAINED HITS 1] (not MONSTER or TITANIC models)."
            ),
        ),
    },
    "Nullstone Field Generator (Aura)": {
        "Nullstone Field": RuleOption(
            rules=(
                Rule(conditions=(ALWAYS,), effects=(FEEL_NO_PAIN_MORTAL_5,), side="defender"),
            ),
            army_wide=True,
            description=(
                "This unit, or another NECRONS unit in the army list, is within 6\": Feel No "
                "Pain 5+ against mortal wounds (Psychic Attacks aren't modelled)."
            ),
        ),
    },
}

# Rules abilities above give the other NECRONS units in the same army list:
# {ability name: [Rule, ...]}.
ARMY_RULES = {
    "Prophet of Destruction": [
        Rule(
            conditions=(PROPHET_OF_DESTRUCTION_TARGET,),
            effects=(REROLL_WOUND_ONES,),
            description=(
                "Other DESTROYER CULT units in the army list re-roll Wound rolls of 1 when "
                "Within 9\" of Nekrosor Ammentar after it destroyed a unit is ticked under "
                "Positioning."
            ),
        ),
    ],
}
