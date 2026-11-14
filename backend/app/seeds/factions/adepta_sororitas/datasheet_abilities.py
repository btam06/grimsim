from app.combat_rules import FightAbility, Rule, UnitEffect
from app.combat_rules.conditions import (
    ALWAYS,
    PRE_WEAPON,
    ATTACKER_LED_BY_CHARACTER,
    CRITICAL_HIT,
    MELEE_ATTACK,
    RANGED_ATTACK,
    TARGET_MONSTER_OR_VEHICLE,
    TARGET_LED_BY_CHARACTER,
    TARGET_MODEL_CHARACTER,
)
from app.combat_rules.effects import (
    AUTO_PASS_WOUND,
    REROLL_ATTACKS,
    MINUS_ONE_TO_WOUND,
    REROLL_HIT_ONES,
    REROLL_WOUND_ONES,
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
]

RULES = {
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
