from app.combat_rules import Rule, RuleOption
from app.combat_rules.conditions import (
    ALWAYS,
    CRITICAL_HIT,
    DEFENDER_BATTLE_SHOCKED,
    DEFENDER_BELOW_HALF_STRENGTH,
    TARGET_ISOLATED,
    TARGET_MONSTER_OR_VEHICLE,
    MELEE_ATTACK,
    RANGED_ATTACK,
    RANGED_VS_OBJECTIVE_TARGET,
    TARGET_MODEL_CHARACTER,
)
from app.combat_rules.effects import (
    ADD_EXTRA_HIT,
    IGNORE_COVER,
    AUTO_PASS_WOUND,
    FEEL_NO_PAIN_6,
    INVULNERABLE_4,
    INVULNERABLE_5,
    PLUS_ONE_SKILL_MELEE,
    PLUS_ONE_TO_HIT,
    PLUS_ONE_TO_WOUND,
    PLUS_ONE_TOUGHNESS,
    REROLL_FAILED_WOUNDS,
    WORSEN_AP,
)
from app.seeds.factions.chaos_knights.conditions import (
    DIABOLIC_POWER,
    DIABOLIC_POWER_CHARGED_MELEE,
    MARKED_PREY_CRITICAL_HIT,
)

# Chaos Knights datasheet abilities - see app/seeds/datasheet_abilities.py for
# what each of these holds. Core abilities (e.g. Stealth) are defined there.

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Brigand",
        "Each time this model makes a ranged attack that targets a unit that is within range "
        "of one or more objective markers, that attack has the [IGNORES COVER] ability.",
        [RANGED_VS_OBJECTIVE_TARGET],
        [IGNORE_COVER],
    ),
    (
        "Executioner",
        "Each time this model makes an attack that targets a unit Below Half-strength, add 1 "
        "to the Hit roll. Each time an enemy unit is destroyed as the result of this model's "
        "attacks, before removing the last model in that unit from the battlefield, each other "
        "unit from your opponent's army that is within 3\" of it must take a Battle-shock test.",
        [DEFENDER_BELOW_HALF_STRENGTH],
        [PLUS_ONE_TO_HIT],
    ),
    (
        "Huntsman",
        "Each time this model makes an attack that targets a MONSTER or VEHICLE unit, you can "
        "re-roll the Wound roll.",
        [TARGET_MONSTER_OR_VEHICLE],
        [REROLL_FAILED_WOUNDS],
    ),
    (
        "Karnivore",
        "You can re-roll Advance and Charge rolls made for this model.",
        [],
        [],
    ),
    (
        "Stalker",
        "Each time this model makes an attack that targets an enemy unit, if there are no other "
        "units from your opponent's army within 6\" of that target, add 1 to the Wound roll.",
        [TARGET_ISOLATED],
        [PLUS_ONE_TO_WOUND],
    ),
    (
        "Protection Protocols",
        "You can target this unit with the Heroic Intervention Stratagem, regardless of any "
        "other uses of that Stratagem this phase. If you do, that use is -1CP, and it does not "
        "prevent any uses of that Stratagem on other units this phase.",
        [],
        [],
    ),
    # Granted by detachment rules (see detachments.json).
    (
        # Its options are in OPTIONS below.
        "Malefic Surge",
        "While this unit is Empowered it can use one of these Malefic Surge abilities, after "
        "which it is no longer Empowered. Unholy Hunger: when a model in this unit makes a "
        "Normal, Advance or Fall Back move, until the end of the phase, add 3\" to its Move "
        "characteristic. Diabolic Power: when this unit is selected to shoot or fight, select "
        "either the [LETHAL HITS] or [SUSTAINED HITS 1] ability; until the end of the phase, "
        "weapons equipped by models in this unit have it. Unnatural Fortitude: when this unit "
        "is selected as the target of an attack, until the end of the phase, models in this "
        "unit have a 5+ invulnerable save, or the Feel No Pain 6+ ability.",
        [],
        [],
    ),
    (
        "Marked Prey",
        "Each time a WAR DOG model in this unit makes an attack that targets the enemy unit "
        "selected for Marked Prey, if that unit is visible to the attacking model, that attack "
        "has the [SUSTAINED HITS 1] ability.",
        [],
        [],
    ),
    (
        "Annihilate the Unworthy",
        "This unit's attacks that target a Battle-shocked unit have +1 to the Hit roll.",
        [DEFENDER_BATTLE_SHOCKED],
        [PLUS_ONE_TO_HIT],
    ),
    # Granted by enhancements (see enhancements.json).
    (
        "Veil of Medrengard",
        "The bearer has a 4+ invulnerable save against ranged attacks, and a 5+ invulnerable "
        "save against melee attacks.",
        [],
        [],
    ),
    (
        "Knight Diabolus",
        "Improve the Weapon Skill characteristic of the bearer's melee weapons by 1. While the "
        "bearer is using the Diabolic Power ability, its melee weapons have the [LANCE] ability.",
        [ALWAYS],
        [PLUS_ONE_SKILL_MELEE],
    ),
    (
        "Fleshmetal Fusion",
        "Add 1 to the bearer's Toughness characteristic. While the bearer is using the "
        "Unnatural Fortitude ability, each time an attack with a Damage characteristic of 1 is "
        "allocated to the bearer, add 1 to any armour saving throw made against that attack.",
        [],
        [],
    ),
    (
        "Panoply of the Cursed Knight",
        "Each time an attack targets the bearer, worsen the Armour Penetration characteristic "
        "of that attack by 1.",
        [],
        [],
    ),
]

# From the 11th edition datasheets (see the tables below for what each does in a game).
ENTRIES += [
    (
        "Fiery Faith",
        "While this model is leading a unit, you can re-roll Leadership tests taken for that unit.",
        [],
        [],
    ),
    (
        "Cursed Flames",
        "In your Shooting phase, after this model has shot, select one enemy INFANTRY unit hit by "
        "one or more of those attacks. That unit must take a Battle-shock test.",
        [],
        [],
    ),
    (
        "Faithful Flock",
        "While this unit is leading a unit and contains a CULT DEMAGOGUE model, models in that "
        "unit have a 5+ invulnerable save.",
        [],
        [],
    ),
    (
        "Dark Ritual",
        "Once per battle, in your Command phase, if this unit contains a CULT DEMAGOGUE model, it "
        "can use this ability. If it does, until the end of the turn, this unit can declare a "
        "charge in a turn in which it Advanced and each time a model in this unit makes an attack,"
        " add 1 to the Hit roll and add 1 to the Wound roll.",
        [],
        [],
    ),
    (
        "Brutal Example",
        "Once per turn, while this unit is leading a unit and contains a TRAITOR ENFORCER model, "
        "you can target that unit with the Fire Overwatch Stratagem for 0CP, and can do so even if"
        " you have already targeted a different unit from your army with that Stratagem this turn."
        " Each time you use this ability, one Bodyguard model in that unit is destroyed.",
        [],
        [],
    ),
    (
        "Mutated Bodyguard",
        "While this unit contains a Traitor Ogryn model, CHARACTER models in this unit have the "
        "Feel No Pain 4+ ability.",
        [],
        [],
    ),
    (
        "Vortex Terrors (Psychic)",
        "At the start of your Shooting phase, select one enemy unit within 24\" of and visible to "
        "this model. That enemy unit must take a Battle-shock test.",
        [],
        [],
    ),
    (
        "Warp Storms (Psychic)",
        "At the end of your Movement phase, roll one D6 for each enemy unit within 9\" of one or "
        "more models with this ability: on a 3+, that enemy unit suffers D3 mortal wounds.",
        [],
        [],
    ),
    (
        "Obsessive Ruthlessness",
        "This unit's ranged attacks that target a MONSTER/VEHICLE unit can ignore modifiers to "
        "this unit's: • BS. • Hit rolls and wound rolls.",
        [],
        [],
    ),
    (
        "Taskmaster (Aura)",
        "While a friendly WAR DOG model is within 9\" of this model, each time that WAR DOG model "
        "makes a ranged attack, re-roll a Hit roll of 1.",
        [],
        [],
    ),
    (
        "Dread Dominion (Aura)",
        "While a friendly WAR DOG model is within 9\" of this model, improve that WAR DOG model's "
        "Leadership and Objective Control characteristics by 1.",
        [],
        [],
    ),
    (
        "Seething Hatred",
        "Each time this model is selected to shoot or fight, you can re-roll one Hit roll or you "
        "can re-roll one Wound roll when resolving those attacks.",
        [],
        [],
    ),
    (
        "Bloodlust",
        "Each time this model makes a Charge move, until the end of the turn, its melee weapons "
        "have the [DEVASTATING WOUNDS] ability.",
        [],
        [],
    ),
    (
        "Frenzied Rampage (Aura)",
        "While a friendly WAR DOG model is within 9\" of this model, each time that WAR DOG model "
        "makes a melee attack, re-roll a Hit roll of 1.",
        [],
        [],
    ),
    (
        "Methodical Destruction",
        "At the start of the first battle round, select one unit from your opponent's army to be "
        "this model's victim. Each time this model makes an attack that targets its victim, you "
        "can re-roll the Wound roll. Each time this model's victim is destroyed, select one new "
        "enemy unit to be this model's victim.",
        [],
        [],
    ),
    (
        "Close-range Killers (Aura)",
        "While a friendly WAR DOG model is within 9\" of this model, each time that WAR DOG model "
        "makes an attack that targets the closest eligible target, improve the Armour Penetration "
        "characteristic of that attack by 1.",
        [],
        [],
    ),
    (
        "Infernal Aegis (Aura)",
        "While a friendly WAR DOG unit is within 6\" of this model, each time an attack targets "
        "that WAR DOG unit, models in it have the Benefit of Cover against that attack.",
        [],
        [],
    ),
    (
        "Bastion of Corruption",
        "Enemy units that are set up on the battlefield as Reinforcements cannot be set up within "
        "12\" of this model.",
        [],
        [],
    ),
    (
        "Searing Flames",
        "In your Shooting phase, after this model has shot, select one enemy unit hit by one or "
        "more of those attacks made with an Acheron flame cannon. Until the end of the phase, that"
        " enemy unit cannot have the Benefit of Cover.",
        [],
        [],
    ),
    (
        "Unrestrained Terror (Aura)",
        "While a friendly WAR DOG model is within 6\" of this model, it is affected by this "
        "ability. At the start of the Fight phase, each enemy unit within Engagement Range of one "
        "or more WAR DOG units affected by this ability must take a Battle-shock test.",
        [],
        [],
    ),
    (
        "Macro-extinction Protocols",
        "Each time this model makes an attack that targets a MONSTER or VEHICLE unit, add 1 to the"
        " Hit roll. If that target is TITANIC or TOWERING, add 1 to the Wound roll as well.",
        [],
        [],
    ),
    (
        "Consumed with Hunger (Aura)",
        "While a friendly WAR DOG model is within 6\" of this model, each time that WAR DOG model "
        "makes an attack that targets a TITANIC or TOWERING unit, you can re-roll the Hit roll.",
        [],
        [],
    ),
    (
        "Storm of Bolts",
        "In your Shooting phase, after this model has shot, select one unit (excluding MONSTERS "
        "and VEHICLES) hit by one or more of those attacks. Until the start of your next turn, "
        "while this model is on the battlefield, that enemy unit is suppressed. While a unit is "
        "suppressed, each time a model in that unit makes an attack, subtract 1 from the Hit roll.",
        [],
        [],
    ),
    (
        "Offerings for the Dark Gods (Aura)",
        "While a friendly WAR DOG model is within 6\" of this model, ranged weapons equipped by "
        "that WAR DOG model have the [SUSTAINED HITS 1] ability.",
        [],
        [],
    ),
    (
        "Dark Fervour (Aura)",
        "While a friendly WAR DOG model is within 6\" of this model, ranged weapons equipped by "
        "that War Dog model have the [ASSAULT] ability.",
        [],
        [],
    ),
    (
        "Huntmaster (Aura)",
        "While a friendly WAR DOG model is within 6\" of this model, ranged weapons equipped by "
        "that WAR DOG model have the [ASSAULT] ability.",
        [],
        [],
    ),
    (
        "Repair Auto-simulacra",
        "At the end of your Command phase, this model regains up to D3 lost wounds.",
        [],
        [],
    ),
    (
        "Preysight (Aura)",
        "While a friendly WAR DOG model is within 6\" of this model, ranged weapons equipped by "
        "that WAR DOG model have the [IGNORES COVER] ability.",
        [],
        [],
    ),
    (
        "Grav-pinned",
        "In your Shooting phase, after this model has shot, if an enemy INFANTRY unit was hit by "
        "one or more of those attacks made with a graviton crusher, until the end of your "
        "opponent's next turn, that enemy unit is grav-pinned. While a unit is grav-pinned, "
        "subtract 2 from that unit's Move characteristic and subtract 2 from Charge rolls made for"
        " that unit.",
        [],
        [],
    ),
    (
        "For the Dark Gods",
        "At the end of your Command phase, if this unit is within range of an objective marker you"
        " control, that objective marker remains under your control until your opponent's Level of"
        " Control over that objective marker is greater than yours at the end of a phase.",
        [],
        [],
    ),
    (
        "Howling Horde",
        "In your opponent's Shooting phase, when an enemy unit has shot, if a model from this unit"
        " was destroyed as a result of those attacks, this unit can make a surge move of up to "
        "D6\".",
        [],
        [],
    ),
    (
        "Bestial Raiders",
        "If this unit starts the game in Strategic Reserves, it can be set up in the "
        "Reinforcements step of your first, second or third Movement phase, regardless of any "
        "mission rules. If this unit is in Strategic Reserves, for the purposes of setting up this"
        " unit on the battlefield, treat the current battle round number as being one higher than "
        "it actually is.",
        [],
        [],
    ),
    (
        "Twisted Defence Force",
        "While this unit is within range of an objective, this unit has +1 Sv against ranged "
        "attacks.",
        [],
        [],
    ),
    (
        "Sunderer of Fortresses",
        "Each time this model makes an attack that targets a VEHICLE, improve the Strength and "
        "Damage characteristics of that attack by 1 (if that attack targets a FORTIFICATION, "
        "improve the Strength and Damage characteristics of that attack by 2 instead).",
        [],
        [],
    ),
    (
        "Bastion of Firepower",
        "Each time this model Remains Stationary, until the end of the turn, ranged weapons "
        "equipped by this model have the [LETHAL HITS] ability.",
        [],
        [],
    ),
]

# Code-defined rules for abilities above, by name.
RULES = {
    "Marked Prey": [
        Rule(
            conditions=(MARKED_PREY_CRITICAL_HIT,),
            effects=(ADD_EXTRA_HIT,),
            description=(
                "WAR DOG models' attacks have [SUSTAINED HITS 1] when Targeting the Marked "
                "Prey unit is ticked under Positioning."
            ),
        ),
    ],
    "Veil of Medrengard": [
        Rule(
            conditions=(RANGED_ATTACK,),
            effects=(INVULNERABLE_4,),
            side="defender",
            description="4+ invulnerable save against ranged attacks.",
        ),
        Rule(
            conditions=(MELEE_ATTACK,),
            effects=(INVULNERABLE_5,),
            side="defender",
            description="5+ invulnerable save against melee attacks.",
        ),
    ],
    "Knight Diabolus": [
        Rule(
            conditions=(DIABOLIC_POWER_CHARGED_MELEE,),
            effects=(PLUS_ONE_TO_WOUND,),
            description=(
                "[LANCE] (+1 to wound after charging) while a Diabolic Power option of "
                "Malefic Surge is picked."
            ),
        ),
    ],
    "Fleshmetal Fusion": [
        Rule(
            conditions=(TARGET_MODEL_CHARACTER,),
            effects=(PLUS_ONE_TOUGHNESS,),
            side="defender",
            description="+1 Toughness for the bearer (the CHARACTER model in its unit).",
        ),
    ],
    "Panoply of the Cursed Knight": [
        Rule(
            conditions=(ALWAYS,),
            effects=(WORSEN_AP,),
            side="defender",
            description="Attacks against the bearer's unit have their AP worsened by 1.",
        ),
    ],
}

# Selectable options for abilities above: {ability name: {option name:
# RuleOption}}.
OPTIONS = {
    "Malefic Surge": {
        f"{DIABOLIC_POWER}: Lethal Hits": RuleOption(
            rules=(Rule(conditions=(CRITICAL_HIT,), effects=(AUTO_PASS_WOUND,)),),
            description="This unit's weapons have [LETHAL HITS].",
        ),
        f"{DIABOLIC_POWER}: Sustained Hits 1": RuleOption(
            rules=(Rule(conditions=(CRITICAL_HIT,), effects=(ADD_EXTRA_HIT,)),),
            description="This unit's weapons have [SUSTAINED HITS 1].",
        ),
        "Unnatural Fortitude: 5+ Invulnerable": RuleOption(
            rules=(
                Rule(conditions=(ALWAYS,), effects=(INVULNERABLE_5,), side="defender"),
            ),
            description="Models in this unit have a 5+ invulnerable save.",
        ),
        "Unnatural Fortitude: Feel No Pain 6+": RuleOption(
            rules=(
                Rule(conditions=(ALWAYS,), effects=(FEEL_NO_PAIN_6,), side="defender"),
            ),
            description="Models in this unit have the Feel No Pain 6+ ability.",
        ),
    },
}

# How the calculator handles abilities above, where that needs saying.
CALCULATOR_NOTES = {
    "Executioner": "Its Battle-shock tests are outside the calculator.",
    "Karnivore": (
        "Descriptive only in the calculator; in a game, it can re-roll its Advance and Charge "
        "rolls."
    ),
    "Protection Protocols": "Descriptive only: a stratagem rule.",
    "Malefic Surge": (
        "Pick the Malefic Surge ability the unit is using under Faction Rules; Unholy Hunger "
        "is movement, outside the calculator."
    ),
    "Fleshmetal Fusion": "The +1 to armour saves against Damage 1 attacks isn't modelled.",
}


# In a game: abilities that let their unit re-roll its charge roll, and its
# Advance roll (see app/services/in_game/charging.py, movement.py).
CHARGE_REROLLS = {"Karnivore"}
ADVANCE_REROLLS = {"Karnivore"}


# --- The 11th edition datasheets' abilities (see ENTRIES above) ---

from app.combat_rules import UnitEffect  # noqa: E402
from app.combat_rules.conditions import (  # noqa: E402
    CHARGED,
    CRITICAL_WOUND,
    DEFENDER_IN_RANGE_OF_OBJECTIVE,
    MELEE_WEAPON,
    RANGED_WEAPON,
    STATIONARY_RANGED_CRITICAL_HIT,
    TARGET_FORTIFICATION,
    TARGET_IS_CLOSEST,
    TARGET_LED_BY_CHARACTER,
    TARGET_TITANIC_OR_TOWERING,
    TARGET_VEHICLE,
)
from app.combat_rules.effects import (  # noqa: E402
    ASSAULT,
    BENEFIT_OF_COVER,
    FEEL_NO_PAIN_4,
    IGNORE_HIT_PENALTIES,
    IGNORE_WOUND_PENALTIES,
    IMPROVE_AP,
    NO_SAVE,
    PLUS_ONE_DAMAGE,
    PLUS_ONE_STRENGTH,
    PLUS_ONE_TO_SAVE,
    REROLL_FAILED_HITS,
    REROLL_HIT_ONES,
    REROLL_ONE_HIT_OR_WOUND,
)
from app.services.in_game.quarry import ALWAYS as _EVERY_TIME  # noqa: E402

_PLUS_SD = (PLUS_ONE_STRENGTH, PLUS_ONE_DAMAGE)
RULES.update(
    {
        "Faithful Flock": [
            Rule(
                conditions=(TARGET_LED_BY_CHARACTER,),
                effects=(INVULNERABLE_5,),
                side="defender",
                description="While it's leading a unit, the unit's models have a 5+ invulnerable save.",
            ),
        ],
        "Mutated Bodyguard": [
            Rule(
                conditions=(TARGET_MODEL_CHARACTER,),
                effects=(FEEL_NO_PAIN_4,),
                side="defender",
                description="While the Traitor Ogryn's in the unit, its CHARACTER models have Feel No Pain 4+.",
            ),
        ],
        "Obsessive Ruthlessness": [
            Rule(
                conditions=(RANGED_ATTACK, TARGET_MONSTER_OR_VEHICLE),
                effects=(IGNORE_HIT_PENALTIES, IGNORE_WOUND_PENALTIES),
                description="Ranged attacks against MONSTER/VEHICLE units ignore Hit and Wound penalties.",
            ),
        ],
        "Seething Hatred": [
            Rule(
                conditions=(ALWAYS,),
                effects=(REROLL_ONE_HIT_OR_WOUND,),
                description="Each time it shoots or fights, re-roll one failed Hit or Wound roll.",
            ),
        ],
        "Bloodlust": [
            Rule(
                conditions=(CHARGED, MELEE_WEAPON, CRITICAL_WOUND),
                effects=(NO_SAVE,),
                description="Having charged this turn, its melee weapons have [DEVASTATING WOUNDS].",
            ),
        ],
        "Macro-extinction Protocols": [
            Rule(
                conditions=(TARGET_MONSTER_OR_VEHICLE,),
                effects=(PLUS_ONE_TO_HIT,),
                description="+1 to hit against MONSTER and VEHICLE units.",
            ),
            Rule(
                conditions=(TARGET_MONSTER_OR_VEHICLE, TARGET_TITANIC_OR_TOWERING),
                effects=(PLUS_ONE_TO_WOUND,),
                description="...and +1 to wound if it's TITANIC or TOWERING.",
            ),
        ],
        "Twisted Defence Force": [
            Rule(
                conditions=(RANGED_ATTACK, DEFENDER_IN_RANGE_OF_OBJECTIVE),
                effects=(PLUS_ONE_TO_SAVE,),
                side="defender",
                description="+1 to its saves against ranged attacks while it's within range of an objective.",
            ),
        ],
        "Sunderer of Fortresses": [
            Rule(conditions=(TARGET_VEHICLE,), effects=_PLUS_SD, description="+1 S and D against VEHICLES."),
            Rule(
                conditions=(TARGET_FORTIFICATION,),
                effects=_PLUS_SD,
                description="...+2 against FORTIFICATIONS.",
            ),
        ],
        "Bastion of Firepower": [
            Rule(
                conditions=(STATIONARY_RANGED_CRITICAL_HIT,),
                effects=(AUTO_PASS_WOUND,),
                description="Having Remained Stationary, its ranged weapons have [LETHAL HITS].",
            ),
        ],
    }
)


def _war_dog_aura(name, reach, rules, description):
    return {
        name: RuleOption(
            rules=tuple(rules), army_wide=True, aura_range=reach, aura_keywords=("WAR DOG",),
            description=description,
        )
    }


OPTIONS.update(
    {
        "Taskmaster (Aura)": _war_dog_aura(
            "Taskmaster", 9.0, [Rule(conditions=(RANGED_ATTACK,), effects=(REROLL_HIT_ONES,))],
            "A WAR DOG within 9\": its ranged attacks re-roll Hit rolls of 1.",
        ),
        "Frenzied Rampage (Aura)": _war_dog_aura(
            "Frenzied Rampage", 9.0, [Rule(conditions=(MELEE_ATTACK,), effects=(REROLL_HIT_ONES,))],
            "A WAR DOG within 9\": its melee attacks re-roll Hit rolls of 1.",
        ),
        "Close-range Killers (Aura)": _war_dog_aura(
            "Close-range Killers", 9.0, [Rule(conditions=(TARGET_IS_CLOSEST,), effects=(IMPROVE_AP,))],
            "A WAR DOG within 9\": +1 AP to attacks against the closest eligible target.",
        ),
        "Infernal Aegis (Aura)": _war_dog_aura(
            "Infernal Aegis", 6.0, [Rule(conditions=(ALWAYS,), effects=(BENEFIT_OF_COVER,), side="defender")],
            "A WAR DOG unit within 6\": the Benefit of Cover against attacks.",
        ),
        "Consumed with Hunger (Aura)": _war_dog_aura(
            "Consumed with Hunger", 6.0,
            [Rule(conditions=(TARGET_TITANIC_OR_TOWERING,), effects=(REROLL_FAILED_HITS,))],
            "A WAR DOG within 6\": re-roll the Hit roll against TITANIC or TOWERING units.",
        ),
        "Offerings for the Dark Gods (Aura)": _war_dog_aura(
            "Offerings for the Dark Gods", 6.0,
            [Rule(conditions=(RANGED_WEAPON, CRITICAL_HIT), effects=(ADD_EXTRA_HIT,))],
            "A WAR DOG within 6\": its ranged weapons have [SUSTAINED HITS 1].",
        ),
        "Dark Fervour (Aura)": _war_dog_aura(
            "Dark Fervour", 6.0, [Rule(conditions=(ALWAYS,), effects=(ASSAULT,))],
            "A WAR DOG within 6\": its ranged weapons have [ASSAULT].",
        ),
        "Huntmaster (Aura)": _war_dog_aura(
            "Huntmaster", 6.0, [Rule(conditions=(ALWAYS,), effects=(ASSAULT,))],
            "A WAR DOG within 6\": its ranged weapons have [ASSAULT].",
        ),
        "Preysight (Aura)": _war_dog_aura(
            "Preysight", 6.0, [Rule(conditions=(RANGED_WEAPON,), effects=(IGNORE_COVER,))],
            "A WAR DOG within 6\": its ranged weapons have [IGNORES COVER].",
        ),
    }
)

# Dread Dominion (Aura): WAR DOG models within 9" have +1 Leadership and OC.
OC_AURAS = {"Dread Dominion (Aura)": {"range": 9.0, "keywords": ("WAR DOG",), "bonus": 1}}
LEADERSHIP_AURAS = {"Dread Dominion (Aura)": {"range": 9.0, "keywords": ("WAR DOG",), "bonus": 1}}

# Methodical Destruction: a victim selected at the start of the first battle
# round - re-roll the Wound roll against it; a new one each time it's
# destroyed (see app/services/in_game/quarry.py).
QUARRIES = {
    "Methodical Destruction": {
        "effects": (REROLL_FAILED_WOUNDS,),
        "again_with": _EVERY_TIME,
        "hint": "its attacks against its victim can re-roll the Wound roll",
    }
}

REINFORCEMENT_DENIAL = {"Bastion of Corruption": 12.0}

# After it shoots in its Shooting phase, the enemy unit it hit (see
# app/services/in_game/unit_effects.py).
AFTER_SHOOTING_EFFECTS = {
    # With its Acheron flame cannon: no Benefit of Cover this phase.
    "Searing Flames": UnitEffect(no_cover=True, lasts="this phase", weapon="Acheron flame cannon"),
    # Not a MONSTER or VEHICLE: suppressed (-1 to hit) until the start of
    # its next turn, while this model's on the battlefield.
    "Storm of Bolts": UnitEffect(
        hit=-1, excluded_keywords=("MONSTER", "VEHICLE"), lasts="my next turn", while_source=True
    ),
    # INFANTRY, with its graviton crusher: grav-pinned (-2" Move, -2 to Charge
    # rolls) until the end of its next turn.
    "Grav-pinned": UnitEffect(
        move=-2, charge=-2, required_keywords=("INFANTRY",), weapon="Graviton crusher"
    ),
}

# Cursed Flames: after it shoots, an INFANTRY unit it hit takes a Battle-shock
# test.
AFTER_SHOOTING_BATTLE_SHOCK = {"Cursed Flames": 0}
AFTER_SHOOTING_TARGET_KEYWORDS = {"Cursed Flames": ("INFANTRY",)}

# Fiery Faith: while leading, its unit re-rolls Leadership tests.
LEADING_BATTLE_SHOCK_REROLLS = {"Fiery Faith"}

# Repair Auto-simulacra: regains up to D3 lost wounds at the end of its
# Command phase.
COMMAND_HEALS = {"Repair Auto-simulacra": 3}
COMMAND_END_HEALS = {"Repair Auto-simulacra"}

# Vortex Terrors: at the start of its Shooting phase, a visible enemy unit
# within 24" takes a Battle-shock test.
START_OF_SHOOTING = {"Vortex Terrors (Psychic)": {"range": 24.0, "visible": True, "battle_shock": 0}}

# Warp Storms: at the end of its Movement phase, each enemy unit within 9":
# 3+, D3 mortal wounds.
END_OF_PHASE_EACH_ENEMY = {
    "Warp Storms (Psychic)": {"phase": "movement", "turn": "own", "range": 9.0, "on": 3, "wounds": "D3"},
}

# For the Dark Gods: objectives it controls at the end of its Command phase
# stay its player's.
SECURES_OBJECTIVES = {"For the Dark Gods": "command"}

# Howling Horde: a surge move of up to D6" when enemy shooting destroys one of
# its models.
SURGE_WHEN_SHOT = {"Howling Horde": "D6"}

# Bestial Raiders: it can arrive from Reserves in battle rounds 1-3, setting
# up as if the battle round were one later.
FIRST_ROUND_INGRESS = {"Bestial Raiders"}
RESERVE_ROUND_BONUS = {"Bestial Raiders": 1}

# Brutal Example: Fire Overwatch on its unit for 0CP even if it's been used
# this turn (see app/routers/games.py: a Bodyguard model is destroyed).
STRATAGEM_COSTS = {"Brutal Example": {"Fire Overwatch": (0, True)}}

# Unrestrained Terror (Aura): at the start of the Fight phase, enemy units
# engaged with WAR DOG units within 6" of it take a Battle-shock test.
FIGHT_START_BATTLE_SHOCK_AURAS = {"Unrestrained Terror (Aura)": {"range": 6.0, "keywords": ("WAR DOG",)}}

# Dark Ritual: once a battle, in its Command phase (with its Cult Demagogue),
# until the end of the turn: it can charge after Advancing, +1 to hit and
# wound (see app/services/in_game/activations.py).
ACTIVATIONS = {
    "Dark Ritual": {
        "phases": ("command",), "turn": "own", "once": "battle", "effect": "empowered",
        "rules": (Rule(conditions=(ALWAYS,), effects=(PLUS_ONE_TO_HIT, PLUS_ONE_TO_WOUND)),),
        "eligible_after": {"advanced": ("charge",)},
        "describe": "Until the end of the turn: charge after Advancing, +1 to hit and wound.",
    },
}
