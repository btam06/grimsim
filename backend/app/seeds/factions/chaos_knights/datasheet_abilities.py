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
    "Karnivore": "Descriptive only: Advance and Charge rolls are outside the calculator.",
    "Protection Protocols": "Descriptive only: a stratagem rule.",
    "Malefic Surge": (
        "Pick the Malefic Surge ability the unit is using under Faction Rules; Unholy Hunger "
        "is movement, outside the calculator."
    ),
    "Fleshmetal Fusion": "The +1 to armour saves against Damage 1 attacks isn't modelled.",
}
