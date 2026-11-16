from app.combat_rules import FightAbility, PhaseStartAbility, Rule, RuleOption, UnitEffect
from app.combat_rules.conditions import (
    ALWAYS,
    PRE_WEAPON,
    ATTACKER_LED_BY_CHARACTER,
    CRITICAL_HIT,
    CRITICAL_WOUND,
    CHARGED,
    DAMAGED_6,
    DEFENDER_IN_RANGE_OF_OBJECTIVE,
    MELEE_ATTACK,
    MELEE_WEAPON,
    RANGED_ATTACK,
    TARGET_MONSTER_OR_VEHICLE,
    TARGET_LED_BY_CHARACTER,
    TARGET_MODEL_CHARACTER,
)
from app.combat_rules.effects import (
    ADD_EXTRA_HIT,
    ADD_ATTACKS_2,
    AUTO_PASS_WOUND,
    FEEL_NO_PAIN_4,
    FEEL_NO_PAIN_6,
    HALVE_ATTACKS,
    IMPROVE_AP,
    FEEL_NO_PAIN_MORTAL_4,
    FEEL_NO_PAIN_PSYCHIC_4,
    HAZARDOUS,
    INVULNERABLE_2,
    INVULNERABLE_4,
    MINUS_ONE_TO_HIT,
    NO_SAVE,
    SAVE_2,
    REROLL_ATTACKS,
    MINUS_ONE_TO_WOUND,
    REROLL_HIT_ONES,
    REROLL_WOUND_ONES,
    PRECISION,
    REROLL_FAILED_HITS,
    REROLL_FAILED_WOUNDS,
    FEEL_NO_PAIN_5,
    IGNORE_HIT_PENALTIES,
    INVULNERABLE_5,
    PLUS_ONE_SKILL_MELEE,
    PLUS_ONE_SKILL_RANGED,
    PLUS_ONE_STRENGTH,
    PLUS_ONE_TO_HIT,
    PLUS_ONE_TO_WOUND,
)
from app.seeds.factions.adepta_sororitas.conditions import (
    ARCO_FLAILS_WEAPON,
    ATTACKER_HAS_AESTRED_THURGA,
    ATTACKER_HAS_MINISTORUM_PRIEST,
    CELESTINE_WITH_GEMINAE,
    REPENTIA_OVERSEEN_MELEE,
    ATTACKER_BELOW_HALF_STRENGTH,
    ATTACKER_BELOW_STARTING_STRENGTH,
    RANGED_TARGET_WITHIN_6,
    RANGED_VS_SORORITAS_KILLER,
)

# Adepta Sororitas datasheet abilities - see app/seeds/datasheet_abilities.py
# for what each of these holds. These are the ones its detachment rules and
# enhancements grant (see app/data/factions/adepta_sororitas/).

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    # Granted by upgrades (see enhancements.json).
    (
        "Symphonic Payload",
        "This unit can re-roll rolls to determine the A of a weapon. (Each weapon's roll is "
        "re-rolled if it came up below its average.)",
        [PRE_WEAPON],
        [REROLL_ATTACKS],
    ),
    # Granted by detachment rules (see detachments.json).
    (
        "The Blood of Martyrs",
        "Each time a model in this unit makes an attack, add 1 to the Hit roll if this unit "
        "is below its Starting Strength, and add 1 to the Wound roll as well if this unit is "
        "Below Half-strength.",
        [],
        [],
    ),
    (
        "Fervent Purgation",
        "Each time a ranged attack made by a model in this unit targets a unit within 6\", "
        "add 1 to the Strength characteristic of that attack.",
        [RANGED_TARGET_WITHIN_6],
        [PLUS_ONE_STRENGTH],
    ),
    (
        "Holy Quest",
        "This unit's attacks have +1 BS and WS.",
        [ALWAYS],
        [PLUS_ONE_SKILL_RANGED, PLUS_ONE_SKILL_MELEE],
    ),
    # Granted by enhancements (see enhancements.json).
    (
        "Iron Surplice of Saint Istalela",
        "The bearer has a Save characteristic of 2+ and the Feel No Pain 5+ ability.",
        [],
        [],
    ),
    (
        # (Ignoring only the modifiers that make the attack worse - the ones
        # anyone would choose to ignore.)
        "Triptych of Judgement",
        "Each time a model in this unit makes an attack, you can ignore any or all modifiers "
        "to that attack's Ballistic Skill or Weapon Skill characteristics and/or any or all "
        "modifiers to the Hit roll.",
        [ALWAYS],
        [IGNORE_HIT_PENALTIES],
    ),
    (
        "Refrain of Enduring Faith",
        "While the bearer is leading a unit, models in that unit have a 5+ invulnerable save.",
        [],
        [],
    ),
    # Datasheets' (see datasheets.json). Those used in a game are in
    # app/seeds/factions/adepta_sororitas/unit_abilities.py.
    (
        "Righteous Denunciation",
        "At the start of the Fight phase, each enemy unit within 6\" of this model must take a "
        "Battle-shock test, subtracting 1 from that test.",
        [],
        [],
    ),
    (
        "Judged for Execution",
        "At the end of your Movement phase, you can select one enemy unit within 18\" of and "
        "visible to this model. Until the start of your next Command phase, each time a "
        "friendly ADEPTA SORORITAS model makes an attack that targets that enemy unit, that "
        "attack has the [LETHAL HITS] ability.",
        [],
        [],
    ),
    (
        "Abbess Sanctorum",
        "While this model is leading a unit, each time a model in that unit makes an attack, "
        "you can re-roll the Hit roll and you can re-roll the Wound roll.",
        [],
        [],
    ),
    (
        "Righteous Repugnance",
        "Each time this model's unit is selected to shoot or fight, you can discard 1 Miracle "
        "dice. If you do, until the end of the phase, add 3 to the Attacks characteristic of "
        "Fidelis and the Lance of Illumination. Each time an enemy unit is destroyed by this "
        "model, you gain 1 Miracle dice.",
        [],
        [],
    ),
    (
        "Sacred Command",
        "Once per battle round, one unit from your army with this ability can use it when its "
        "unit is targeted with a Stratagem. If it does, reduce the CP cost of that use of that "
        "Stratagem by 1CP.",
        [],
        [],
    ),
    (
        "Divine Deliverance",
        "Once per battle, at the start of the Fight phase, this model can use this ability. If "
        "it does, until the end of the phase, add 3 to the Attacks characteristic of melee "
        "weapons equipped by this model and those weapons have the [DEVASTATING WOUNDS] "
        "ability.",
        [],
        [],
    ),
    (
        "Medicus Ministorum",
        "While this model is leading a unit, models in that unit have the Feel No Pain 5+ "
        "ability.",
        [],
        [],
    ),
    (
        "Sacred Healing",
        "While this model is leading a unit, in your Command phase, you can return up to 1 "
        "destroyed model (excluding CHARACTER models) to that unit. If you wish, you can first "
        "discard 1 Miracle dice; if you do, you can return up to D3+1 destroyed models "
        "(excluding CHARACTER models) to that unit instead.",
        [],
        [],
    ),
    (
        "Fury of the Righteous",
        "While this model is leading a unit, weapons equipped by models in that unit have the "
        "[LETHAL HITS] ability.",
        [],
        [],
    ),
    (
        "Rapturous Blows",
        "Each time this model's unit is selected to fight, you can discard 1 Miracle dice. If "
        "you do, then until the end of the phase, each time a melee attack made by this model "
        "scores a wound, the target of that attack suffers 1 mortal wound in addition to any "
        "normal damage.",
        [],
        [],
    ),
    (
        "Righteous Smiting",
        "While this model is leading a unit, each time a model in that unit makes a melee "
        "attack, add 1 to the Wound roll.",
        [],
        [],
    ),
    (
        "Zealot",
        "Once per battle, in the Fight phase, this model can use this ability. If it does, until "
        "the end of the phase, improve the Strength and Attacks characteristics of melee "
        "weapons equipped by this model by 3.",
        [],
        [],
    ),
    (
        "Holy Mission",
        "If this model is attached to a DOMINION SQUAD during the Declare Battle Formations "
        "step, it gains the Scouts 6\" ability. If this model is attached to a SISTERS "
        "NOVITIATE SQUAD during the Declare Battle Formations step, it gains the Infiltrators "
        "ability.",
        [],
        [],
    ),
    (
        "Cherub",
        "Once per battle, after this unit has performed an Act of Faith, you gain 1 Miracle "
        "dice.",
        [],
        [],
    ),
    (
        "Cherubs",
        "Twice per battle, after this unit has performed an Act of Faith, you gain 1 Miracle "
        "dice.",
        [],
        [],
    ),
    (
        "Defenders of the Faith",
        "At the end of your Command phase, if this unit is within range of an objective marker "
        "you control, that objective marker remains under your control until your opponent's "
        "Level of Control over that objective marker is greater than yours at the end of a "
        "phase.",
        [],
        [],
    ),
    (
        "Simulacrum Imperialis",
        "At the end of your Command phase, for each objective marker you control that has one "
        "or more units from your army with this ability within range of it, roll one D6: on a "
        "4+, you gain 1 Miracle dice showing a value equal to that result.",
        [],
        [],
    ),
    (
        "Righteous Awareness",
        "In your opponent's Movement phase, if an enemy unit ends a move within 8\" of this "
        "unit, if this unit is not within Engagement Range of one or more enemy units it can "
        "make a Normal move of up to D6\".",
        [],
        [],
    ),
    (
        "Holy Vanguard",
        "If this unit has a Leader unit attached to it during the Declare Battle Formations "
        "step and this unit starts the battle embarked within a TRANSPORT, that Leader unit "
        "gains the Scouts 6\" ability.",
        [],
        [],
    ),
    (
        "Storm of Retribution",
        "Each time a model in this unit makes a ranged attack, that model can re-roll a Hit "
        "roll of 1 and re-roll a Wound roll of 1. If such an attack targets an enemy unit that "
        "has destroyed one or more ADEPTA SORORITAS units from your army during the battle, add "
        "1 to the Hit roll and add 1 to the Wound roll as well.",
        [],
        [],
    ),
    (
        "Sworn Protectors",
        "While an ADEPTA SORORITAS CHARACTER is leading this unit, each time an attack targets "
        "this unit, subtract 1 from the Wound roll.",
        [],
        [],
    ),
    (
        "Angelic Ascent",
        "In your Shooting phase, after this unit has shot, if it is not within Engagement Range "
        "of any enemy units, it can make a Normal move of up to 6\". If it does, until the end "
        "of the turn, this unit is not eligible to declare a charge.",
        [],
        [],
    ),
    (
        "Purge and Cleanse",
        "In your Shooting phase, after this model has shot, select one enemy unit hit by one or "
        "more of those attacks. Until the end of the phase, that enemy unit cannot have the "
        "Benefit of Cover.",
        [],
        [],
    ),
    (
        "Rites of Castigation",
        "In your Shooting phase, after this model has shot, select one enemy unit hit by one or "
        "more of those attacks. Until the end of the turn, each time a friendly ADEPTA "
        "SORORITAS unit makes a ranged attack that targets that enemy unit, improve the Armour "
        "Penetration characteristic of that attack by 1. The same enemy unit can only be "
        "affected by this ability once per turn.",
        [],
        [],
    ),
    (
        "Devastating Refrain",
        "In your Shooting phase, after this model has shot, if one or more of those attacks "
        "made with an Indirect Fire weapon scored a hit against an enemy unit, that unit must "
        "take a Battle-shock test. Each time such an attack destroys an enemy model that has "
        "the Deadly Demise ability, that model's Deadly Demise ability inflicts mortal wounds "
        "on a D6 roll of 5+ instead of on a 6.",
        [],
        [],
    ),
    (
        "Anguish of the Unredeemed",
        "Each time a model in this unit is destroyed by a melee attack, if that model has not "
        "fought this phase, roll one D6. On a 2+, do not remove it from play; that destroyed "
        "model can fight after the attacking unit has finished making its attacks, and is then "
        "removed from play.",
        [],
        [],
    ),
    (
        "Righteous Paragons",
        "Each time a model in this unit makes an attack that targets a MONSTER or VEHICLE "
        "unit, add 1 to the Hit roll and add 1 to the Wound roll.",
        [TARGET_MONSTER_OR_VEHICLE],
        [PLUS_ONE_TO_HIT, PLUS_ONE_TO_WOUND],
    ),
    # From the Wahapedia datasheets (11th edition, 2026-11) - each one's game logic is
    # below (RULES etc.) or in unit_abilities.py.
    (
        "Auto-Tapestry of the Emperor's Judgement",
        "While this unit is leading a unit and contains an Aestred Thurga model, weapons "
        "equipped by models in that unit have the [DEVASTATING WOUNDS] ability.",
        [],
        [],
    ),
    (
        "Recount the Deeds of the Saints",
        "While this unit is leading a unit and contains an Agathae Dolan model, each time "
        "that unit destroys an enemy unit, you gain 1 Miracle dice. When that Agathae Dolan "
        "model is destroyed, you gain D3 Miracle dice.",
        [],
        [],
    ),
    (
        "Holy Judgement",
        "At the start of your Shooting phase, select one enemy unit within 12\" of and "
        "visible to this unit's Ephrael Stern model. That unit must take a Battle-shock test,"
        " subtracting 2 from the result if it is a CHAOS unit. If the test is failed, that "
        "enemy unit suffers 3 mortal wounds.",
        [],
        [],
    ),
    (
        "Mysterious Saviours",
        "You can target this unit with the Heroic Intervention Stratagem, regardless of any "
        "other uses of that Stratagem this phase. If you do, that use is -1CP and does not "
        "prevent any uses of that Stratagem on other units this phase.",
        [],
        [],
    ),
    (
        "Healing Tears",
        "While this unit contains a Celestine model, in your Command phase, you can return 1 "
        "destroyed Geminae Superia model to this unit.",
        [],
        [],
    ),
    (
        "Lifewards",
        "While this unit contains one or more Geminae Superia models, Celestine has the Feel "
        "No Pain 4+ ability.",
        [],
        [],
    ),
    (
        "Miraculous Intervention",
        "The first time this unit's Celestine model is destroyed, roll one D6 at the end of "
        "the phase. On a 2+, set that Celestine model back up on the battlefield, as close as"
        " possible to where it was destroyed and not within Engagement Range of any enemy "
        "units, with its full wounds remaining.",
        [],
        [],
    ),
    (
        "Relics of the Matriarchs",
        "At the start of the battle round, select up to two of the abilities in the Relics of"
        " the Matriarchs section. Until the start of the next battle round, this model has "
        "those abilities. (While it has 1-6 wounds remaining, only one.)",
        [],
        [],
    ),
    (
        "Solemn Procession",
        "Each time you gain 1 Miracle dice at the start of your turn, if this model is on the"
        " battlefield, do not roll one D6 to determine the value of that Miracle dice; it has"
        " a value of 6.",
        [],
        [],
    ),
    (
        "Damaged: 1-6 Wounds Remaining",
        "While this model has 1-6 wounds remaining, the Attacks characteristics of all of its"
        " weapons are halved, and you can only select one ability when using its Relics of "
        "the Matriarchs ability, instead of up to two.",
        [],
        [],
    ),
    (
        "The Pulpit of Saint Holline's Basilica",
        "This unit has the Stealth ability, and each time a melee attack targets this unit, "
        "subtract 1 from the Hit roll.",
        [],
        [],
    ),
    (
        "Fiery Conviction",
        "If this model is on the battlefield at the start of your Command phase, you can "
        "choose one of the following: discard 1 Miracle dice and gain 1CP; or take a "
        "Leadership test for this model - if that test is passed, gain 1CP.",
        [],
        [],
    ),
    (
        "The Emperor's Grace",
        "Once per battle, at the start of any phase, this model can use this ability. If it "
        "does, until the end of the phase, this model has a 2+ invulnerable save.",
        [],
        [],
    ),
    (
        "Laud Hailer",
        "Once per battle, at the start of any phase, you can select one friendly ADEPTA "
        "SORORITAS unit that is Battle-shocked and within 12\" of this model. That unit is no"
        " longer Battle-shocked.",
        [],
        [],
    ),
    (
        "Stirring Rhetoric",
        "While this model is leading a unit, each time this model's unit performs an Act of "
        "Faith, the value of one of the Miracle dice used in that Act of Faith is first "
        "changed to a 6.",
        [],
        [],
    ),
    (
        "Executioner of Heretics (Aura)",
        "While an enemy unit is within 6\" of this model, worsen the Leadership "
        "characteristic of models in that unit by 1.",
        [],
        [],
    ),
    (
        "Unflinching Determination",
        "While this model is leading a unit, add 1 to the Objective Control characteristic of"
        " models in that unit.",
        [],
        [],
    ),
    (
        "Litany of Deeds",
        "Each time you gain a Miracle dice as the result of an ADEPTA SORORITAS unit or model"
        " from your army being destroyed, if that unit or model was destroyed within 12\" of "
        "this model, you can re-roll the result of that Miracle dice before adding it to your"
        " Miracle dice pool.",
        [],
        [],
    ),
    (
        "Stanchion of Holy Martyrs",
        "While this model is leading a unit, models in that unit have a Save characteristic "
        "of 2+ and a 4+ invulnerable save.",
        [],
        [],
    ),
    (
        "Self Repair",
        "At the start of your Command phase, this model regains 1 lost wound.",
        [],
        [],
    ),
    (
        "Extremis Trigger Word",
        "Each time this unit is selected to fight, you can choose to invoke its extremis "
        "trigger word. If you do, then until the end of the phase, arco-flails equipped by "
        "models in this unit have an Attacks characteristic of 6 and the [HAZARDOUS] ability.",
        [],
        [],
    ),
    (
        "Rituale Nullificatus",
        "Models in this unit have the Feel No Pain 4+ ability against Psychic Attacks and "
        "mortal wounds.",
        [],
        [],
    ),
    (
        "Virtue of Intolerance",
        "At the start of the battle, select one unit from your opponent's army to be this "
        "unit's quarry. Each time a model in this unit makes an attack that targets its "
        "quarry, that attack has the [PRECISION] ability and you can re-roll the Hit roll. "
        "This ability can be used even if this unit is embarked within a TRANSPORT.",
        [],
        [],
    ),
    (
        "Overseer of Redemption",
        "While this unit contains a Repentia Superior model, each time a Sisters Repentia "
        "model in this unit makes a melee attack, you can re-roll the Hit roll and you can "
        "re-roll the Wound roll.",
        [],
        [],
    ),
    (
        "Ministorum Sermon",
        "While this unit contains a MINISTORUM PRIEST, melee weapons equipped by models in "
        "this unit have the [SUSTAINED HITS 1] ability.",
        [],
        [],
    ),
    (
        "Impetuous Fervour",
        "Each time a model in this unit makes an attack, re-roll a Hit roll of 1. If the "
        "target of that attack is an enemy unit within range of an objective marker, you can "
        "re-roll the Hit roll instead.",
        [],
        [],
    ),
    (
        "Embodied Prophecy",
        "Each time this unit is selected to fight, select one of [SUSTAINED HITS 1] or "
        "[LETHAL HITS] to apply to melee weapons equipped by models in this unit until the "
        "end of the phase. If this unit made a Charge move this turn, both apply instead.",
        [],
        [],
    ),
    (
        "Endless Suffering",
        "This unit is eligible to declare a charge in a turn in which it Advanced.",
        [],
        [],
    ),
]

RULES = {
    "Damaged: 1-6 Wounds Remaining": [
        Rule(
            conditions=(PRE_WEAPON, DAMAGED_6),
            effects=(HALVE_ATTACKS,),
            description="Its weapons' Attacks halved while it has 1-6 wounds left.",
        ),
    ],
    "Auto-Tapestry of the Emperor's Judgement": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER, ATTACKER_HAS_AESTRED_THURGA, CRITICAL_WOUND),
            effects=(NO_SAVE,),
            description="[DEVASTATING WOUNDS] while leading a unit with Aestred Thurga in it.",
        ),
    ],
    "Lifewards": [
        Rule(
            conditions=(CELESTINE_WITH_GEMINAE,),
            effects=(FEEL_NO_PAIN_4,),
            side="defender",
            description="Feel No Pain 4+ for Celestine while a Geminae Superia is in her unit.",
        ),
    ],
    "The Pulpit of Saint Holline's Basilica": [
        Rule(
            conditions=(MELEE_ATTACK,),
            effects=(MINUS_ONE_TO_HIT,),
            side="defender",
            description="-1 to hit melee attacks against the unit (Stealth is its own ability).",
        ),
    ],
    "Stanchion of Holy Martyrs": [
        Rule(
            conditions=(TARGET_LED_BY_CHARACTER,),
            effects=(SAVE_2, INVULNERABLE_4),
            side="defender",
            description="A 2+ Save and 4+ invulnerable save for the unit it's leading.",
        ),
    ],
    "Rituale Nullificatus": [
        Rule(
            conditions=(ALWAYS,),
            effects=(FEEL_NO_PAIN_MORTAL_4, FEEL_NO_PAIN_PSYCHIC_4),
            side="defender",
            description="Feel No Pain 4+ against mortal wounds and Psychic Attacks.",
        ),
    ],
    "Overseer of Redemption": [
        Rule(
            conditions=(REPENTIA_OVERSEEN_MELEE,),
            effects=(REROLL_FAILED_HITS, REROLL_FAILED_WOUNDS),
            description=(
                "Sisters Repentia re-roll melee Hit and Wound rolls while a Repentia Superior is in "
                "the unit."
            ),
        ),
    ],
    "Ministorum Sermon": [
        Rule(
            conditions=(ATTACKER_HAS_MINISTORUM_PRIEST, MELEE_WEAPON, CRITICAL_HIT),
            effects=(ADD_EXTRA_HIT,),
            description="[SUSTAINED HITS 1] for melee weapons while a Ministorum Priest is in it.",
        ),
    ],
    "Impetuous Fervour": [
        Rule(conditions=(ALWAYS,), effects=(REROLL_HIT_ONES,), description="Re-roll Hit rolls of 1."),
        Rule(
            conditions=(DEFENDER_IN_RANGE_OF_OBJECTIVE,),
            effects=(REROLL_FAILED_HITS,),
            description="Re-roll the Hit roll against a unit within range of an objective marker.",
        ),
    ],
    "Embodied Prophecy": [
        Rule(
            conditions=(CHARGED, MELEE_WEAPON, CRITICAL_HIT),
            effects=(ADD_EXTRA_HIT, AUTO_PASS_WOUND),
            description=(
                "Having charged: [SUSTAINED HITS 1] and [LETHAL HITS] for melee weapons (otherwise one, "
                "chosen as it fights)."
            ),
        ),
    ],
    "Righteous Smiting": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER, MELEE_ATTACK),
            effects=(PLUS_ONE_TO_WOUND,),
            description="+1 to wound for melee attacks while it's leading a unit.",
        ),
    ],
    "Storm of Retribution": [
        Rule(
            conditions=(RANGED_ATTACK,),
            effects=(REROLL_HIT_ONES, REROLL_WOUND_ONES),
            description="Ranged attacks re-roll Hit and Wound rolls of 1.",
        ),
        Rule(
            conditions=(RANGED_VS_SORORITAS_KILLER,),
            effects=(PLUS_ONE_TO_HIT, PLUS_ONE_TO_WOUND),
            description=(
                "+1 to hit and wound against a unit that's destroyed one of its army's ADEPTA "
                "SORORITAS units."
            ),
        ),
    ],
    "Sworn Protectors": [
        Rule(
            conditions=(TARGET_LED_BY_CHARACTER,),
            effects=(MINUS_ONE_TO_WOUND,),
            side="defender",
            description="-1 to wound attacks against it while a CHARACTER is leading it.",
        ),
    ],
    "Abbess Sanctorum": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER,),
            effects=(REROLL_FAILED_HITS, REROLL_FAILED_WOUNDS),
            description="Re-roll failed Hit and Wound rolls while it's leading a unit.",
        ),
    ],
    "Fury of the Righteous": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER, CRITICAL_HIT),
            effects=(AUTO_PASS_WOUND,),
            description="[LETHAL HITS] while it's leading a unit.",
        ),
    ],
    "Medicus Ministorum": [
        Rule(
            conditions=(TARGET_LED_BY_CHARACTER,),
            effects=(FEEL_NO_PAIN_5,),
            side="defender",
            description="Feel No Pain 5+ for the unit while it's leading it.",
        ),
    ],
    "The Blood of Martyrs": [
        Rule(
            conditions=(ATTACKER_BELOW_STARTING_STRENGTH,),
            effects=(PLUS_ONE_TO_HIT,),
            description="+1 to hit while the unit is below its Starting Strength.",
        ),
        Rule(
            conditions=(ATTACKER_BELOW_HALF_STRENGTH,),
            effects=(PLUS_ONE_TO_WOUND,),
            description="+1 to wound as well while the unit is Below Half-strength.",
        ),
    ],
    "Iron Surplice of Saint Istalela": [
        Rule(
            conditions=(TARGET_MODEL_CHARACTER,),
            effects=(FEEL_NO_PAIN_5,),
            side="defender",
            description=(
                "Feel No Pain 5+ for the CHARACTER models in the bearer's unit (the bearer), "
                "not the models it's leading."
            ),
        ),
    ],
    "Refrain of Enduring Faith": [
        Rule(
            conditions=(ALWAYS,),
            effects=(INVULNERABLE_5,),
            side="defender",
            description="A 5+ invulnerable save for the models in the unit the bearer leads.",
        ),
    ],
}

CALCULATOR_NOTES = {
    "Iron Surplice of Saint Istalela": (
        "Only its Feel No Pain 5+ is applied: the bearer's 2+ Save characteristic isn't."
    ),
    "Fervent Purgation": (
        "In the calculator, tick that the target is within 6\" under Positioning; in a game "
        "it's measured."
    ),
}

# Its Stratagems cost 1CP less, once a battle round for the army (see
# app/services/in_game/game.py ability_discount).
STRATAGEM_DISCOUNTS = {"Sacred Command": 1}

# Used as its unit fights, once a battle: what it does is a weapon bonus for
# the model with it (see unit_abilities.py weapon_bonuses).
FIGHT_ABILITIES = {
    # Each time the unit fights (arco-flails: A6 and [HAZARDOUS]).
    "Extremis Trigger Word": FightAbility(
        rules=(Rule(conditions=(ARCO_FLAILS_WEAPON,), effects=(ADD_ATTACKS_2, HAZARDOUS)),),
        once_per_battle=False,
    ),
    # One of the two, each time it fights (both, having charged - see RULES).
    "Embodied Prophecy: Sustained Hits": FightAbility(
        rules=(Rule(conditions=(MELEE_WEAPON, CRITICAL_HIT), effects=(ADD_EXTRA_HIT,)),),
        once_per_battle=False,
        ability="Embodied Prophecy",
        group="Embodied Prophecy",
    ),
    "Embodied Prophecy: Lethal Hits": FightAbility(
        rules=(Rule(conditions=(MELEE_WEAPON, CRITICAL_HIT), effects=(AUTO_PASS_WOUND,)),),
        once_per_battle=False,
        ability="Embodied Prophecy",
        group="Embodied Prophecy",
    ),
    "Divine Deliverance": FightAbility(rules=(), once_per_battle=True),
    "Zealot": FightAbility(rules=(), once_per_battle=True),
}

# At the end of its player's Command phase, objectives it's controlling stay
# theirs (see app/services/in_game/objectives.py secure_at_end_of).
SECURES_OBJECTIVES = {"Defenders of the Faith": "command"}

# A Normal move of up to D6" when an enemy unit ends a move within 8" of it,
# in its opponent's Movement phase (see app/services/in_game/reactive_move.py).
REACTIVE_MOVES = {"Righteous Awareness": {"trigger_range": 8.0, "reach": "D6"}}

# After it shoots in its Shooting phase, the enemy unit it hit: +1 AP for
# ADEPTA SORORITAS ranged attacks against it this turn.
AFTER_SHOOTING_EFFECTS = {
    "Rites of Castigation": UnitEffect(
        ranged_ap=1, by_keyword="ADEPTA SORORITAS", lasts="this turn"
    ),
    "Purge and Cleanse": UnitEffect(no_cover=True, lasts="this phase"),
}

# After it shoots, it can make a Normal move (see
# app/services/in_game/shoot_scoot.py) - Angelic Ascent: up to 6", and then it
# can't declare a charge this turn.
SHOOT_SCOOT = {"Angelic Ascent": {"reach": 6.0, "no_charge": True}}

# After it shoots in its Shooting phase, the enemy unit it hit takes a
# Battle-shock test - only if an [INDIRECT FIRE] weapon hit it. (Its Deadly
# Demise on a 5+ is in app/services/combat.py.)
AFTER_SHOOTING_BATTLE_SHOCK = {"Devastating Refrain": 0}
AFTER_SHOOTING_INDIRECT_ONLY = {"Devastating Refrain"}

# A model destroyed by a melee attack, before its unit's fought this phase,
# stays to fight on this D6 (see app/services/in_game/duty_in_death.py).
FIGHTS_ON_DEATH = {"Anguish of the Unredeemed": 2}

# Wargear that sets its bearer's characteristics (see
# app/models/unit_model.py).
WARGEAR_CHARACTERISTICS = {"Anchorite Sarcophagus": {"movement": 7, "save": 3}}

# Abilities that let their unit declare a charge after Advancing.
ELIGIBLE_AFTER = {"Endless Suffering": {"advanced": ("charge",)}}

# Re-rolls of their unit's Advance and Charge rolls (the wargear's ability).
CHARGE_REROLLS = {"Sacred Banner"}
ADVANCE_REROLLS = {"Sacred Banner"}

# Lost wounds regained at the start of its Command phase (a D1: one).
COMMAND_HEALS = {"Self Repair": 1}

# Heroic Intervention on it: 0CP (1 less), even if used already this phase.
STRATAGEM_COSTS = {"Mysterious Saviours": {"Heroic Intervention": (0, True)}}

# Enemy units within 6" of it: -1 to their Battle-shock tests (a worse
# Leadership).
BATTLE_SHOCK_AURAS = {"Executioner of Heretics (Aura)": {"range": 6.0, "modifier": -1}}

# Once a battle, at the start of a phase: a 2+ invulnerable save for the
# model until the end of it.
PHASE_START_ABILITIES = {
    "The Emperor's Grace": PhaseStartAbility(
        phases=("shooting", "fight"),
        rules=(Rule(conditions=(ALWAYS,), effects=(INVULNERABLE_2,), side="defender"),),
        either_player=True,
        model_only=True,
    ),
}

# Once a battle, at the start of any phase: a friendly Battle-shocked ADEPTA
# SORORITAS unit within 12" is no longer Battle-shocked.
RALLIES = {"Laud Hailer": {"keywords": ("ADEPTA SORORITAS",), "range": 12.0, "once_per_battle": True}}

# At the start of its Shooting phase: an enemy unit within 12" of and visible
# to Ephrael Stern takes a Battle-shock test (-2 if CHAOS) - failing it, 3
# mortal wounds (see app/services/in_game/shooting_start.py).
START_OF_SHOOTING = {
    "Holy Judgement": {
        "range": 12.0,
        "visible": True,
        "battle_shock": 0,
        "keyword_modifier": ("CHAOS", -2),
        "fail_mortal_wounds": 3,
    },
}

# While leading a unit: +n OC for the models in it (see
# app/services/in_game/objectives.py).
LEADING_OC = {"Unflinching Determination": 1}

# Relics of the Matriarchs (the Triumph of Saint Katherine): at the start of
# each battle round, up to two of these (one while it's Damaged) - auras for
# friendly units within 6" until the next (see
# app/seeds/factions/adepta_sororitas/unit_abilities.py relics). Those with no
# combat rules are checked where they apply: The Fiery Heart (movement), the
# Censer (Battle-shock), the Ebon Chalice (Acts of Faith).
RELICS_OF_THE_MATRIARCHS = "Relics of the Matriarchs"
OPTIONS = {
    RELICS_OF_THE_MATRIARCHS: {
        "The Fiery Heart (Aura)": RuleOption(
            aura_range=6.0,
            description="+2\" Move, and +1 to Advance and Charge rolls.",
        ),
        "Censer of the Sacred Rose (Aura)": RuleOption(
            aura_range=6.0, description="Re-roll Battle-shock tests."
        ),
        "Simulacrum of the Ebon Chalice (Aura)": RuleOption(
            aura_range=6.0, description="Up to two Acts of Faith a phase."
        ),
        "Simulacrum of the Argent Shroud (Aura)": RuleOption(
            rules=(Rule(conditions=(RANGED_ATTACK,), effects=(REROLL_WOUND_ONES,)),),
            aura_range=6.0,
            description="Ranged attacks re-roll a Wound roll of 1.",
        ),
        "Icon of the Valorous Heart (Aura)": RuleOption(
            rules=(Rule(conditions=(ALWAYS,), effects=(FEEL_NO_PAIN_6,), side="defender"),),
            aura_range=6.0,
            description="Feel No Pain 6+.",
        ),
        "Petals of the Bloody Rose (Aura)": RuleOption(
            rules=(Rule(conditions=(MELEE_ATTACK,), effects=(IMPROVE_AP,)),),
            aura_range=6.0,
            description="Melee weapons' AP improved by 1.",
        ),
    },
}
# Virtue of Intolerance: a quarry selected at the start of the battle (see
# app/services/in_game/quarry.py) - and a new one, once it's destroyed, with a
# denuncia oratory.
QUARRIES = {
    "Virtue of Intolerance": {
        "effects": (PRECISION, REROLL_FAILED_HITS),
        "again_with": "Denuncia oratory",
        "hint": "attacks against its quarry have [PRECISION] and re-roll the Hit roll",
    }
}
