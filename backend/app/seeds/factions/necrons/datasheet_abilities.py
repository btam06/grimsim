from app.combat_rules import FightAbility, Rule, RuleOption
from app.combat_rules.conditions import (
    ALWAYS,
    ATTACKER_LED_BY_CHARACTER,
    CHARGED,
    CRITICAL_WOUND,
    DEFENDER_IN_RANGE_OF_OBJECTIVE,
    MELEE_ATTACK,
    STRENGTH_EXCEEDS_TOUGHNESS,
    TARGET_LED_BY_CHARACTER,
    TARGET_MODEL_CHARACTER,
)
from app.combat_rules.effects import (
    ADD_EXTRA_HIT,
    AUTO_PASS_WOUND,
    FEEL_NO_PAIN_5,
    MINUS_ONE_TO_WOUND,
    NO_SAVE,
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
    ENMITIC_EXTERMINATOR_VS_NON_MONSTER,
    GAUSS_DESTRUCTOR_VS_MONSTER,
    IMPLACABLE_TARGET_MODEL,
    MELEE_CRITICAL_HIT,
    TARGET_LED_BY_NOBLE,
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
        "Nanoscarab Reanimation Beam (Aura)",
        "While a friendly NECRONS unit is within 3\" of this model, each time that unit's "
        "Reanimation Protocols activate, that unit heals an additional D3 wounds.",
        [],
        [],
    ),
    (
        "Tunnelling Horrors",
        "At the end of your opponent's turn, if this unit is unengaged, you can use this "
        "ability. If you do:\n"
        "- Place this unit in strategic reserves.\n"
        "- This unit must make an ingress move in your next Movement phase (including in your "
        "first turn).",
        [],
        [],
    ),
    (
        "Rites of Reanimation",
        "While this model is leading a unit, models in that unit have the Feel No Pain 5+ "
        "ability.",
        [],
        [],
    ),
    (
        "Technomancer",
        "At the end of your Movement phase, you can select one friendly NECRONS model within 6\" "
        "of the bearer. That model regains up to D3 lost wounds. Each model can only be selected "
        "for this ability once per turn.",
        [],
        [],
    ),
    (
        "Wraith Form",
        "Each time this unit ends a Normal move, you can select one enemy unit it moved over "
        "during that move and roll one D6 for each model in this unit: for each 4+, that enemy "
        "unit suffers 1 mortal wound.",
        [],
        [],
    ),
    (
        "Optimised for Slaughter",
        "Each time a model in this unit makes an attack with an enmitic exterminator that "
        "targets a unit (excluding MONSTERS and VEHICLES), re-roll a Wound roll of 1. Each time "
        "a model in this unit makes an attack with a gauss destructor that targets a MONSTER or "
        "VEHICLE, re-roll a Wound roll of 1.",
        [],
        [],
    ),
    (
        "My Will Be Done",
        "Once per battle round, one unit from your army with this ability can use it when its "
        "unit is targeted with a Stratagem. If it does, reduce the CP cost of that use of that "
        "Stratagem by 1CP.",
        [],
        [],
    ),
    (
        "Implacable Resilience",
        "Each time an attack is allocated to this model, subtract 1 from that attack's Damage "
        "characteristic.",
        [],
        [],
    ),
    (
        "Guardian Protocols",
        "While a NOBLE model is leading this unit, each time an attack targets this unit, if the "
        "Strength characteristic of that attack is greater than this unit's Toughness "
        "characteristic, subtract 1 from the Wound roll.",
        [],
        [],
    ),
    (
        "United In Destruction",
        "While this model is leading a unit, melee weapons equipped by models in that unit have "
        "the [LETHAL HITS] ability.",
        [],
        [],
    ),
    (
        "Crimson Harvest",
        "Each time this model ends a Charge move, select one enemy unit within Engagement Range "
        "of this model and roll one D6: on a 2-5, that unit suffers D3 mortal wounds; on a 6, "
        "that unit suffers D3+3 mortal wounds.",
        [],
        [],
    ),
    (
        "Whirling Onslaught",
        "Each time a model in this unit makes a melee attack, re-roll a Hit roll of 1. If this "
        "unit made a Charge move this turn, you can re-roll the Hit roll instead.",
        [],
        [],
    ),
    (
        "Plasmacyte",
        "Once per battle for each Plasmacyte this unit has, when this unit is selected to fight, "
        "you can use this ability. If you do, until the end of the phase, melee weapons equipped "
        "by models in this unit have the [DEVASTATING WOUNDS] ability.",
        [],
        [],
    ),
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

# From the 11th edition datasheets (see the tables below for what each does in a game).
ENTRIES += [
    (
        "Starstele Deployment",
        "When this unit is first set up on the battlefield, its models do not have to be set up "
        "in Unit Coherency. Instead, each model must be set up wholly within 12\" of one other "
        "model from its unit. From that point on, each model in this unit is treated as a "
        "separate unit. (In a game: its models need only be within 12\" of another of them.)",
        [],
        [],
    ),
    (
        "Illuminor",
        "While this model is within 3\" of one or more other friendly NECRONS units, this model has"
        " the Lone Operative ability.",
        [],
        [],
    ),
    (
        "Mechanical Augmentation (Aura)",
        "While a friendly NECRONS BATTLELINE unit is within 3\" of this model, each time a model in"
        " that unit makes an attack, improve the Armour Penetration characteristic of that attack "
        "by 1, and each time an attack targets that unit, worsen the Armour Penetration "
        "characteristic of that attack by 1.",
        [],
        [],
    ),
    (
        "Atomic Energy Manipulator",
        "At the end of the Fight phase, if this model destroyed one or more models this phase, "
        "until the end of the battle, add 3\" to the range of its Mechanical Augmentation ability "
        "(to a maximum of 12\").",
        [],
        [],
    ),
    (
        "Grand Strategist",
        "At the start of your Command phase, if this model is on the battlefield, you gain 1CP.",
        [],
        [],
    ),
    (
        "Lord of the Storm",
        "Once per battle, at the end of your Command phase, this model can use this ability. If it"
        " does, roll one D6 for each enemy unit within 12\" of this model: on a 2-5, that enemy "
        "unit suffers D3 mortal wounds; on a 6, that enemy unit suffers D3+3 mortal wounds.",
        [],
        [],
    ),
    (
        "Master Chronomancer",
        "While this model is leading a unit, models in that unit have a 4+ invulnerable save.",
        [],
        [],
    ),
    (
        "The Stars Are Right",
        "Once per battle, at the start of the Fight phase, this model can use this ability. If it "
        "does, until the end of the phase, triple the Attacks and Strength characteristics of this"
        " model's Staff of Tomorrow and every successful Wound roll made for this model's attacks "
        "scores a Critical Wound.",
        [],
        [],
    ),
    (
        "Ancient Collector",
        "While this model is leading a unit, at the end of your Command phase, if this unit is "
        "within range of an objective marker you control, that objective marker remains under your"
        " control until your opponent's Level of Control over that objective marker is greater "
        "than yours at the end of a phase.",
        [],
        [],
    ),
    (
        "Surrogate Hosts",
        "At the start of your Command phase, if this model is on the battlefield, you can select "
        "one other friendly NECRONS INFANTRY CHARACTER model on the battlefield (excluding "
        "SKORPEKH LORD or EPIC HERO models). The selected model is destroyed (ignoring any rules "
        "that are triggered when a model is destroyed) and this model is put in its place, with "
        "all of its wounds remaining (if the selected model was leading a unit, this model now "
        "attaches to that unit as its Leader).",
        [],
        [],
    ),
    (
        "Grand Illusion",
        "If your army includes this model, after both players have deployed their armies, select "
        "up to three NECRONS units from your army and redeploy them. When doing so, any of those "
        "units can be placed into Strategic Reserves, regardless of how many units are already in "
        "Strategic Reserves.",
        [],
        [],
    ),
    (
        "Drain Life",
        "At the end of the Fight phase, roll one D6 for each enemy unit within 6\" of this model: "
        "on a 4+, that enemy unit suffers D3 mortal wounds.",
        [],
        [],
    ),
    (
        "Triarch Abilities",
        "At the start of the battle round, select one Triarch ability (see left). Until the start "
        "of the next battle round, this unit has that ability.",
        [],
        [],
    ),
    (
        "The Silent King",
        "While a friendly NECRONS unit is within 6\" of this unit's Szarekh model, improve that "
        "unit's Leadership characteristic by 1.",
        [],
        [],
    ),
    (
        "Triarchal Menhirs",
        "If this unit's Szarekh model is destroyed, all of this unit's remaining Triarchal Menhir "
        "models are also destroyed.",
        [],
        [],
    ),
    (
        "Timesplinter Mantle",
        "• This unit has Stealth. • Melee attacks that target this unit have ‐1 to hit rolls.",
        [],
        [],
    ),
    (
        "Chronometron",
        "In your Shooting phase, after this model's unit has shot, if it is not within Engagement "
        "Range of any enemy units, that unit can make a Normal move of up to 5\" as if it were your"
        " Movement phase. If it does, until the end of the turn, that unit is not eligible to "
        "declare a charge.",
        [],
        [],
    ),
    (
        "Tectonic Reverberations",
        "In your Movement phase, you can select one enemy unit within 18\" of and visible to this "
        "model. Until the start of your next Movement phase that enemy unit is pinned. While a "
        "unit is pinned, subtract 2 from that unit's Move characteristic and subtract 2 from "
        "Charge rolls made for it.",
        [],
        [],
    ),
    (
        "Obelisk Node Control",
        "While this model is within range of an objective marker you control, enemy units that are"
        " set up on the battlefield from Reserves cannot be set up within 12\" of this model.",
        [],
        [],
    ),
    (
        "Vanguard Protocols",
        "If this model is attached to a CANOPTEK MACROCYTES unit during the Declare Battle "
        "Formations step, this model has the Scouts 8\" ability.",
        [],
        [],
    ),
    (
        "Inescapable Death",
        "Once per turn, one unit from your army with this ability can be targeted with the Fire "
        "Overwatch Stratagem for 0CP, even if you have already used that Stratagem on a different "
        "unit this phase. In addition, each time you target this unit with the Fire Overwatch "
        "Stratagem, while resolving that Stratagem, hits are scored on unmodified Hit rolls of 2+.",
        [],
        [],
    ),
    (
        "Multi-threat Eliminator",
        "Once per turn, in your opponent's Shooting phase, when an enemy unit makes a ranged "
        "attack that targets a friendly NECRONS unit within 3\" of a model with this ability, after"
        " that enemy unit has shot, one model with this ability that is within 3\" of that target "
        "can shoot as if it were your Shooting phase, but it must target only that enemy unit when"
        " doing so, and can only do so if that enemy unit is an eligible target.",
        [],
        [],
    ),
    (
        "Translocation Shroud",
        "Each time this model's unit Advances, do not make an Advance roll for it. Instead, until "
        "the end of the phase, add 6\" to the Move characteristic of models in that unit. In "
        "addition, each time a model in that unit makes a Normal, Advance or Fall Back move, until"
        " that move is finished, it can move horizontally through models and terrain features (it "
        "cannot finish a move on top of another model or its base).",
        [],
        [],
    ),
    (
        "Harbinger of Destruction",
        "While this model is leading a unit, each time a model in that unit makes a ranged attack,"
        " a successful unmodifed Hit roll of 5+ scores a Critical Hit.",
        [],
        [],
    ),
    (
        "Living Lightning",
        "In your Shooting phase, select one enemy unit within 18\" of and visible to this model "
        "(excluding units with the Lone Operative ability that are not part of an Attached unit "
        "and are not within 12\" of this model) and roll four D6: for each 4+, that enemy unit "
        "suffers 1 mortal wound.",
        [],
        [],
    ),
    (
        "Nightmare Shroud (Aura)",
        "In the Battle-Shock step of your opponent's Command phase, if an enemy unit that is below"
        " its Starting Strength is within 6\" of this model, that enemy unit must take a "
        "Battle-Shock test, subtracting 1 from the test when it does so.",
        [],
        [],
    ),
    (
        "Harbinger of Despair",
        "Once per turn, at the start of your Command, Movement, Shooting, Charge or Fight phase, "
        "you can select one enemy unit within 18\" of this model. That unit must take a "
        "Battle-Shock test, subtracting 1 from the test when it does so.",
        [],
        [],
    ),
    (
        "Adaptive Strategy",
        "This model's unit is eligible to shoot and declare a charge in a turn in which it Fell "
        "Back.",
        [],
        [],
    ),
    (
        "Engrammatic Logic",
        "Once per battle, at the start of any phase, you can select one friendly NECRONS unit that"
        " is Battle-shocked and within 12\" of this model. That unit is no longer Battle-shocked.",
        [],
        [],
    ),
    (
        "Transdimensional Displacement",
        "In your Movement phase, when this unit is selected to make an advance move, you can use "
        "this ability. If you do: • That advance move has no maximum distance. • This unit can "
        "move through all types of model (including enemy models and MONSTER/VEHICLE models). • "
        "After moving, this unit must be more than 8\" horizontally from all enemy units.",
        [],
        [],
    ),
    (
        "C'tan Shard",
        "This model cannot be given Enhancements.",
        [],
        [],
    ),
    (
        "Carrier Wave (Aura)",
        "While a friendly NECRONS unit is within 6\" of this model, add 1 to the Objective Control "
        "characteristic of models in that unit.",
        [],
        [],
    ),
    (
        "Advanced Quantum Shielding",
        "Each time an attack targets this model, if the Strength characteristic of that attack is "
        "greater than this model's Toughness characteristic, subtract 1 from the Wound roll.",
        [],
        [],
    ),
    (
        "Implacable Eradication",
        "Each time a model in this unit makes an attack, re-roll a Wound roll of 1. If the target "
        "of that attack is an enemy unit within range of an objective marker, you can re-roll the "
        "Wound roll instead.",
        [],
        [],
    ),
    (
        "Their Number is Legion",
        "Each time this unit's Reanimation Protocols activate, you can re-roll the dice to see how"
        " many wounds are reanimated.",
        [],
        [],
    ),
    (
        "Repair Barge",
        "Once per turn, just after an enemy unit finishes making its attacks, if one or more "
        "friendly NECRON WARRIORS units within 3\" of this model lost one or more wounds as a "
        "result of those attacks, this model can use this ability. If it does, select one of those"
        " NECRON WARRIORS units; that unit's Reanimation Protocols activate. The same NECRON "
        "WARRIORS unit cannot be selected for this ability more than once per turn.",
        [],
        [],
    ),
    (
        "Atavistic Instigation",
        "Each time this model targets an enemy unit with its heavy death ray, your opponent must "
        "declare if that unit will stand firm or duck for cover: • If it stands firm, when "
        "resolving ranged attacks against that unit this phase, a successful unmodified Hit roll "
        "of 5+ scores a Critical Hit. • If it ducks for cover, until the start of your next "
        "Shooting phase, each time a model in that unit makes an attack, subtract 1 from the Hit "
        "roll.",
        [],
        [],
    ),
    (
        "Harassment Swarm (Aura)",
        "While an enemy unit (excluding MONSTERS and VEHICLES) is within 3\" of this unit, each "
        "time a model in that unit makes an attack, subtract 1 from the Hit roll.",
        [],
        [],
    ),
    (
        "Weapon Sentinels",
        "Each time a model in this unit makes a ranged attack that targets a unit within 12\", you "
        "can ignore any or all modifiers to the following: that attack's Ballistic Skill "
        "characteristic; the Hit roll; the Wound roll.",
        [],
        [],
    ),
    (
        "Canoptek Retinue",
        "At the start of the Declare Battle Formations step, this unit can join one other unit "
        "from your army that is being led by a CRYPTEK model (a unit cannot have more than one "
        "TOMB CRAWLERS unit joined to it and cannot have both a TOMB CRAWLERS and a CRYPTOTHRALLS "
        "unit joined to it). If it does, until the end of the battle, every model in this unit "
        "counts as being part of that Bodyguard unit, and that Bodyguard unit's Starting Strength "
        "is increased accordingly. ARMY RULESReanimation Protocols",
        [],
        [],
    ),
    (
        "Bound Creation",
        "While this unit is in the same unit as a CRYPTEK model, that CRYPTEK model has the Feel "
        "No Pain 4+ ability.",
        [],
        [],
    ),
    (
        "Systematic Vigour",
        "Each time a CRYPTOTHRALL model in this unit is destroyed by a melee attack, if that model"
        " has not fought this phase, roll one D6: on a 2+, do not remove it from play. The "
        "destroyed model can fight after the attacking model's unit has finished making its "
        "attacks, and it is then removed from play.",
        [],
        [],
    ),
    (
        "Cryptek Retinue",
        "At the start of the Declare Battle Formations step, this unit can join one other unit "
        "from your army that is being led by a CRYPTEK model (a unit cannot have more than one "
        "CRYPTOTHRALLS unit joined to it). If it does, until the end of the battle, every model in"
        " this unit counts as being part of that Bodyguard unit, and that Bodyguard unit's "
        "Starting Strength is increased accordingly.",
        [],
        [],
    ),
    (
        "Hyperspace Hunters",
        "Once per turn, in the Reinforcements step of your opponent's Movement phase, when an "
        "enemy unit is set up on the battlefield from Reserves within 18\" of and visible to this "
        "unit, this unit can shoot as if it were your Shooting phase, but must only target that "
        "enemy unit when doing so, and can only do so if that enemy unit is an eligible target.",
        [],
        [],
    ),
    (
        "Flesh Hunger",
        "Each time a model in this unit makes a melee attack, if the target of that attack is "
        "Below Half-strength, a successful Hit roll scores a Critical Hit.",
        [],
        [],
    ),
    (
        "Relentless Combatants",
        "You can re-roll Charge rolls made for this unit, and this unit is eligible to declare a "
        "charge in a turn in which it Fell Back.",
        [],
        [],
    ),
    (
        "Evasion Engrams",
        "In your Shooting phase, after this unit has shot, it can make a Normal move of up to 6\". "
        "If it does, until the end of the turn, this unit is not eligible to declare a charge.",
        [],
        [],
    ),
    (
        "Self-destruction",
        "At the start of the Fight phase, if this unit is within Engagement Range of one or more "
        "enemy units, you can select one model in this unit to destroy. If you do, select one "
        "enemy unit within Engagement Range of that model and roll one D6, adding 1 to the result "
        "if that unit is a VEHICLE. On a 2-5, that unit suffers D3 mortal wounds; on a 6+, that "
        "unit suffers 3 mortal wounds.",
        [],
        [],
    ),
    (
        "Chittering swarm",
        "While an enemy unit is within Engagement Range of this unit, subtract 1 from the "
        "Objective Control characteristic of models in that enemy unit (to a minimum of 1). While "
        "this unit is within 6\" of one or more friendly CRYPTEK models, the Objective Control "
        "characteristic of models in this unit is 1.",
        [],
        [],
    ),
    (
        "Eternity Gate",
        "In your Movement phase (excluding the first battle round), you can select one friendly "
        "NECRONS INFANTRY unit that is either in strategic reserves or on the battlefield (if you "
        "select a unit on the battlefield, remove that unit from the battlefield and place it into"
        " strategic reserves). That unit can make an ingress move, and while making that ingress "
        "move, that unit must be set up wholly within 6\" of this unit and unengaged (instead of "
        "more than 8\" horizontally from all enemy units), even if that is within your opponent's "
        "deployment zone. That unit cannot make a charge move this turn.",
        [],
        [],
    ),
    (
        "Gravitic Pulse",
        "At the start of your opponent's Movement phase, you can select one enemy unit within 18\" "
        "of and visible to this model. Until the end of the turn, halve the Move characteristic of"
        " models in that unit and halve Advance and Charge rolls made for that unit. In addition, "
        "if that unit can FLY, until the start of your next Movement phase, roll one D6 each time "
        "that unit ends any type of move: on a 4+, that unit suffers D3 mortal wounds.",
        [],
        [],
    ),
    (
        "Powers of the C'tan",
        "In your Shooting phase, when this model is selected to shoot, first select up to two "
        "different C'tan Powers weapons (see left). Until the end of the phase, this model is "
        "equipped with those weapons in addition to its other weapons (this model cannot make "
        "attacks with any other C'tan Powers weapon you did not select in this way this phase).",
        [],
        [],
    ),
    (
        "Terrifying Monstrosity",
        "At the start of the Fight phase, each enemy unit within Engagement Range of one or more "
        "units with this ability must take a Battle-shock test.",
        [],
        [],
    ),
    (
        "Invasion Beams",
        "At the end of the Fight phase, if there are no models currently embarked within this "
        "TRANSPORT, you can select one friendly NECRONS INFANTRY unit wholly within 6\" of this "
        "TRANSPORT. Unless that unit is within Engagement Range of one or more enemy units, it can"
        " embark within this TRANSPORT.",
        [],
        [],
    ),
    (
        "Quantum Invader",
        "This model can be set up in the Reinforcements step of your first, second or third "
        "Movement phase, regardless of any mission rules.",
        [],
        [],
    ),
    (
        "Malevolent Arcing",
        "In your Shooting phase, each time you select a target for this model's twin tesla "
        "destructor, roll one D6 for the target unit and one D6 for every other enemy unit within "
        "3\" of the target unit. On a 5+, the unit being rolled for is struck by arcing energies; "
        "after resolving all of this model's attacks against the target unit, each unit struck by "
        "arcing energies suffers D3 mortal wounds.",
        [],
        [],
    ),
    (
        "Canoptek Swarm",
        "In your Command phase, select one friendly CANOPTEK SCARAB SWARM unit within 6\" of this "
        "unit. One destroyed model is returned to that CANOPTEK SCARAB SWARM unit for each SPYDER "
        "model in this unit.",
        [],
        [],
    ),
    (
        "Overwhelming Obliteration",
        "In your Movement phase, if this model Remains Stationary, until the end of the turn, its "
        "doomsday cannon has the [DEVASTATING WOUNDS] ability.",
        [],
        [],
    ),
    (
        "Sentinel Construct",
        "Each time you target this unit with the Fire Overwatch Stratagem, while resolving that "
        "Stratagem, hits are scored on unmodified Hit rolls of 5+.",
        [],
        [],
    ),
    (
        "Targeting Relay",
        "In your Shooting phase, each time this model is selected to shoot, after resolving its "
        "attacks, select one enemy unit that was hit by one or more of those attacks. Until the "
        "end of the phase, that unit cannot have the Benefit of Cover.",
        [],
        [],
    ),
    (
        "Reanimation Nodes (Aura)",
        "While a friendly NECRONS INFANTRY unit is within 6\" of this Fortification, models in that"
        " unit have Feel No Pain 6+ ability.",
        [],
        [],
    ),
    (
        "Ancient Cover",
        "Each time a ranged attack is allocated to a model, if that model is not fully visible to "
        "every model in the attacking unit because of this FORTIFICATION, that model has the "
        "Benefit of Cover against that attack.",
        [],
        [],
    ),
    (
        "Fortification",
        "While an enemy unit is only within Engagement Range of one or more FORTIFICATIONS from "
        "your army: • That unit can still be selected as the target of ranged attacks, but each "
        "time such an attack is made, unless it is made with a Pistol, subtract 1 from the Hit "
        "roll. • Models in that unit do not need to take Desperate Escape tests due to Falling "
        "Back while Battle-shocked, except for those that will move over enemy models when doing "
        "so.",
        [],
        [],
    ),
    (
        "Damaged: 1-6 Wounds Remaining (Szarekh)",
        "While this unit's Szarekh model has 1-6 wounds remaining, halve the Attacks "
        "characteristic of that model's weapons, and each time this unit makes an attack, subtract"
        " 1 from the Hit roll.",
        [],
        [],
    ),
    (
        "Damaged: 1-8 Wounds Remaining (Tesseract Vault)",
        "While this model has 1-8 wounds remaining, subtract 4 from its Objective Control "
        "characteristic and you can only select one of the C'tan Powers weapons in your Shooting "
        "phase, instead of two.",
        [],
        [],
    ),
]

# Code-defined rules for abilities above, by name.
RULES = {
    "Rites of Reanimation": [
        Rule(
            conditions=(TARGET_LED_BY_CHARACTER,),
            effects=(FEEL_NO_PAIN_5,),
            side="defender",
            description="Feel No Pain 5+ for its unit while this CHARACTER leads it.",
        ),
    ],
    "Optimised for Slaughter": [
        Rule(
            conditions=(ENMITIC_EXTERMINATOR_VS_NON_MONSTER,),
            effects=(REROLL_WOUND_ONES,),
            description=(
                "Enmitic exterminators re-roll wound rolls of 1 against units with no MONSTER "
                "or VEHICLE model."
            ),
        ),
        Rule(
            conditions=(GAUSS_DESTRUCTOR_VS_MONSTER,),
            effects=(REROLL_WOUND_ONES,),
            description="Gauss destructors re-roll wound rolls of 1 against MONSTERS and VEHICLES.",
        ),
    ],
    "Implacable Resilience": [
        Rule(
            conditions=(IMPLACABLE_TARGET_MODEL,),
            effects=(MINUS_ONE_DAMAGE,),
            side="defender",
            description="-1 Damage (to a minimum of 1) for attacks allocated to this model.",
        ),
    ],
    "Guardian Protocols": [
        Rule(
            conditions=(STRENGTH_EXCEEDS_TOUGHNESS, TARGET_LED_BY_NOBLE),
            effects=(MINUS_ONE_TO_WOUND,),
            side="defender",
            description=(
                "While a NOBLE leads it, attacks against it with Strength greater than its "
                "Toughness are -1 to wound."
            ),
        ),
    ],
    "United In Destruction": [
        Rule(
            conditions=(ATTACKER_LED_BY_CHARACTER, MELEE_CRITICAL_HIT),
            effects=(AUTO_PASS_WOUND,),
            description="While this CHARACTER leads its unit, its melee weapons have [LETHAL HITS].",
        ),
    ],
    "Whirling Onslaught": [
        Rule(conditions=(MELEE_ATTACK,), effects=(REROLL_HIT_ONES,)),
        Rule(
            conditions=(MELEE_ATTACK, CHARGED),
            effects=(REROLL_FAILED_HITS,),
            description=(
                "Melee attacks re-roll hit rolls of 1 - any failed hit roll if it made a Charge "
                "move this turn."
            ),
        ),
    ],
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
    "Nanoscarab Reanimation Beam (Aura)": (
        "Descriptive only in the calculator; in a game, units within 3\" heal an additional D3 "
        "as their Reanimation Protocols activate."
    ),
    "Tunnelling Horrors": (
        "Descriptive only in the calculator; in a game, its player declares it in the "
        "opponent's turn, and at its end the unit goes into Strategic Reserves - to arrive in "
        "their next Movement phase, even the first."
    ),
    "Technomancer": (
        "Descriptive only in the calculator; in a game, at the end of your Movement phase a "
        "friendly NECRONS model within 6\" regains up to D3 wounds."
    ),
    "Wraith Form": (
        "Descriptive only in the calculator; in a game, after a Normal move a D6 for each of its "
        "models (4+: a mortal wound) against an enemy unit it moved over."
    ),
    "My Will Be Done": (
        "Descriptive only in the calculator; in a game, the first Stratagem each battle round "
        "that targets a unit with it costs 1CP less."
    ),
    "Crimson Harvest": (
        "Descriptive only in the calculator; in a game, mortal wounds on an enemy unit within "
        "Engagement Range of it after its Charge move."
    ),
    "Plasmacyte": (
        "Pick its fight option for [DEVASTATING WOUNDS] on melee weapons; in a game, its player "
        "can use it when the unit's selected to fight - once a battle for each Plasmacyte."
    ),
    "Resurrection Orb": (
        "Descriptive only in the calculator; in a game, its player declares it during a phase "
        "and the unit heals D6 wounds as the phase ends (once a battle; one unit a turn)."
    ),
    "Protective Disciples": (
        "Descriptive only in the calculator; in a game, models more than 12\" away can't shoot "
        "it while it's within 3\" of another friendly DESTROYER CULT unit (Lone Operative)."
    ),
    "Matter Absorption": (
        "Descriptive only in the calculator; in a game, used at the start of its player's "
        "Shooting phase on an enemy VEHICLE unit within 12\"."
    ),
    "Enslaved Star God": "An army-building restriction: a list can't make it its Warlord.",
    "Command Protocols": (
        "Leader attachment is approximated: a unit with a CHARACTER model and other models "
        "counts as led."
    ),
}

# Selectable options for abilities above: {ability name: {option name:
# RuleOption}}. In the calculator, picking one means the unit is within
# range; in a game, it applies by itself to units within its aura_range.
# Plasmacyte: [DEVASTATING WOUNDS] for its unit's melee weapons (it's used
# fighting, so its attacks are melee ones).
_PLASMACYTE_RULES = (Rule(conditions=(CRITICAL_WOUND,), effects=(NO_SAVE,)),)

OPTIONS = {
    "Plasmacyte": {
        "Plasmacyte (fight)": RuleOption(
            rules=_PLASMACYTE_RULES,
            description="Its unit's melee weapons have [DEVASTATING WOUNDS] (a Plasmacyte used).",
        ),
    },
    "Infectious Murder-madness (Aura)": {
        "Infectious Murder-madness": RuleOption(
            rules=(Rule(conditions=(MURDER_MADNESS_CRITICAL_HIT,), effects=(ADD_EXTRA_HIT,)),),
            army_wide=True,
            aura_range=6.0,
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
            aura_range=6.0,
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


# In a game: abilities that let their player repair a model (see
# app/services/in_game/repair.py) - Technomancer: at the end of their
# Movement phase.
REPAIRS = {
    "Technomancer": {"keywords": ("NECRONS",), "range": 6.0, "heal": "D3", "phase": "movement"},
}

# In a game: abilities their unit can use when it's selected to fight (see
# app/services/in_game/fight_abilities.py).
FIGHT_ABILITIES = {
    "Plasmacyte": FightAbility(rules=_PLASMACYTE_RULES, uses_wargear="Plasmacyte"),
}

# In a game: abilities that take CP off a Stratagem that targets their unit,
# the first time each battle round for their army (see
# app/services/in_game/game.py) - how much.
STRATAGEM_DISCOUNTS = {"My Will Be Done": 1}

# In a game: abilities whose unit, ending a move of one of these kinds, rolls
# a D6 for each of its models against an enemy unit it moved over - each
# roll of `roll` or more, 1 mortal wound (see app/services/in_game/movement.py).
MOVED_OVER_MORTALS = {"Wraith Form": {"kinds": ("normal",), "roll": 4}}

# In a game: abilities whose model, ending a Charge move, rolls a D6 against
# an enemy unit within Engagement Range of it - the mortal wounds for each
# result, highest first (see app/services/in_game/charging.py).
CHARGE_MORTALS = {"Crimson Harvest": ((6, "D3+3"), (2, "D3"))}


# In a game: abilities that put their unit in Strategic Reserves at the end of
# its opponent's turn, to arrive in its player's next Movement phase (see
# app/services/in_game/reinforcements.py).
TURN_END_RESERVES = {"Tunnelling Horrors": {"must_arrive": True}}


# In a game: abilities used at the start of their player's Shooting phase
# (see app/services/in_game/shooting_start.py) - Matter Absorption: an enemy
# VEHICLE unit within 12", 2+, D3 mortal wounds, and the model regains up to
# that many.
START_OF_SHOOTING = {
    "Matter Absorption": {
        "target_keywords": ("VEHICLE",),
        "range": 12.0,
        "roll": 2,
        "mortal_wounds": "D3",
        "heal_self": True,
    },
}

# In a game: abilities that give their unit Lone Operative while within a
# distance of another friendly unit with some keywords (see
# app/services/in_game/shooting.py).
CONDITIONAL_LONE_OPERATIVE = {"Protective Disciples": (3.0, ("DESTROYER CULT",))}

# Abilities whose model can't be its list's Warlord (see
# app/services/list_building/warlord.py).
CANNOT_BE_WARLORD = {"Enslaved Star God"}


# --- The 11th edition datasheets' abilities (see ENTRIES above) ---

from app.combat_rules.conditions import (  # noqa: E402
    ATTACKER_STATIONARY,
    DAMAGED_6,
    DEFENDER_BELOW_HALF_STRENGTH,
    MELEE_WEAPON,
    PRE_WEAPON,
    RANGED_ATTACK,
    TARGET_WITHIN_12,
)
from app.combat_rules.effects import (  # noqa: E402
    BENEFIT_OF_COVER,
    FEEL_NO_PAIN_6,
    HALVE_ATTACKS,
    IGNORE_HIT_PENALTIES,
    IGNORE_WOUND_PENALTIES,
    INVULNERABLE_4,
    SUCCESSFUL_HITS_CRITICAL,
    WORSEN_AP,
)
from app.combat_rules import UnitEffect  # noqa: E402
from app.seeds.datasheet_abilities import CORE_RULES as _CORE  # noqa: E402
from app.seeds.factions.necrons.conditions import DOOMSDAY_CANNON_WEAPON  # noqa: E402

RULES.update(
    {
        "Master Chronomancer": [
            Rule(
                conditions=(TARGET_LED_BY_CHARACTER,),
                effects=(INVULNERABLE_4,),
                side="defender",
                description="While it's leading a unit, the unit's models have a 4+ invulnerable save.",
            ),
        ],
        "Timesplinter Mantle": [
            *_CORE["Stealth"],
            Rule(
                conditions=(MELEE_ATTACK,),
                effects=(MINUS_ONE_TO_HIT,),
                side="defender",
                description="Melee attacks against this unit are -1 to hit.",
            ),
        ],
        "Harbinger of Destruction": RULES["Destroyer Cult"],
        "Advanced Quantum Shielding": [
            Rule(
                conditions=(STRENGTH_EXCEEDS_TOUGHNESS,),
                effects=(MINUS_ONE_TO_WOUND,),
                side="defender",
                description="-1 to wound against it when the attack's Strength exceeds its Toughness.",
            ),
        ],
        "Implacable Eradication": [
            Rule(conditions=(ALWAYS,), effects=(REROLL_WOUND_ONES,), description="Re-roll Wound rolls of 1."),
            Rule(
                conditions=(DEFENDER_IN_RANGE_OF_OBJECTIVE,),
                effects=(REROLL_FAILED_WOUNDS,),
                description="Re-roll the Wound roll against a unit within range of an objective marker.",
            ),
        ],
        "Flesh Hunger": [
            Rule(
                conditions=(MELEE_WEAPON, DEFENDER_BELOW_HALF_STRENGTH),
                effects=(SUCCESSFUL_HITS_CRITICAL,),
                description="Against a Below Half-strength unit, successful melee Hit rolls are Critical Hits.",
            ),
        ],
        "Weapon Sentinels": [
            Rule(
                conditions=(RANGED_ATTACK, TARGET_WITHIN_12),
                effects=(IGNORE_HIT_PENALTIES, IGNORE_WOUND_PENALTIES),
                description="Ranged attacks against a unit within 12\" ignore Hit and Wound penalties.",
            ),
        ],
        "Overwhelming Obliteration": [
            Rule(
                conditions=(ATTACKER_STATIONARY, DOOMSDAY_CANNON_WEAPON, CRITICAL_WOUND),
                effects=(NO_SAVE,),
                description="Having Remained Stationary, its doomsday cannon has [DEVASTATING WOUNDS].",
            ),
        ],
        "Damaged: 1-6 Wounds Remaining (Szarekh)": [
            *_CORE["Damaged: 1-4 Wounds Remaining"],
            Rule(
                conditions=(PRE_WEAPON, DAMAGED_6),
                effects=(HALVE_ATTACKS,),
                description="Szarekh's weapons have half their Attacks while it's Damaged.",
            ),
        ],
    }
)

_IMPROVE_AP_AURA = Rule(conditions=(ALWAYS,), effects=(IMPROVE_AP,))
OPTIONS.update(
    {
        "Mechanical Augmentation (Aura)": {
            "Mechanical Augmentation": RuleOption(
                rules=(_IMPROVE_AP_AURA, Rule(conditions=(ALWAYS,), effects=(WORSEN_AP,), side="defender")),
                army_wide=True,
                aura_range=3.0,
                aura_keywords=("BATTLELINE",),
                description=(
                    "A NECRONS BATTLELINE unit within 3\": +1 AP to its attacks, and -1 AP to "
                    "attacks against it."
                ),
            ),
        },
        "Gloom Prism (Aura)": {
            "Gloom Prism": RuleOption(
                rules=(Rule(conditions=(ALWAYS,), effects=(FEEL_NO_PAIN_MORTAL_5,), side="defender"),),
                army_wide=True,
                aura_range=6.0,
                description="A NECRONS unit within 6\": Feel No Pain 5+ against mortal wounds.",
            ),
        },
        "Fabricator Claw Array (Aura)": {
            "Fabricator Claw Array": RuleOption(
                rules=(Rule(conditions=(ALWAYS,), effects=(FEEL_NO_PAIN_6,), side="defender"),),
                army_wide=True,
                aura_range=6.0,
                aura_keywords=("VEHICLE",),
                description="A NECRONS VEHICLE unit within 6\": Feel No Pain 6+.",
            ),
        },
        "Reanimation Nodes (Aura)": {
            "Reanimation Nodes": RuleOption(
                rules=(Rule(conditions=(ALWAYS,), effects=(FEEL_NO_PAIN_6,), side="defender"),),
                army_wide=True,
                aura_range=6.0,
                aura_keywords=("INFANTRY",),
                description="A NECRONS INFANTRY unit within 6\": Feel No Pain 6+.",
            ),
        },
    }
)

# Atomic Energy Manipulator: +3" to Mechanical Augmentation's range each Fight
# phase it destroyed models, to at most 12" (see app/services/in_game/auras.py).
AURA_RANGE_GROWTH = {
    "Atomic Energy Manipulator": {"aura": "Mechanical Augmentation (Aura)", "by": 3.0, "most": 12.0}
}

CONDITIONAL_LONE_OPERATIVE.update({"Illuminor": (3.0, ("NECRONS",))})

# After shooting, a Normal move (see app/services/in_game/shoot_scoot.py) -
# Chronometron: 5" (if it's not engaged), Evasion Engrams: 6"; then no charge.
SHOOT_SCOOT = {
    "Chronometron": {"reach": 5.0, "no_charge": True},
    "Evasion Engrams": {"reach": 6.0, "no_charge": True},
}

ELIGIBLE_AFTER = {
    "Adaptive Strategy": {"fell_back": ("shoot", "charge")},
    "Relentless Combatants": {"fell_back": ("charge",)},
}
CHARGE_REROLLS = {"Relentless Combatants"}
RALLIES = {"Engrammatic Logic": {"keywords": ("NECRONS",), "range": 12.0, "once_per_battle": True}}

# Fire Overwatch: hits on unmodified 5+ (Sentinel Construct), 2+ (Inescapable
# Death - and once a turn, for 0CP even if it's been used this phase).
SNAP_SHOTS_ON = {"Sentinel Construct": 5, "Inescapable Death": 2}
STRATAGEM_COSTS = {"Inescapable Death": {"Fire Overwatch": (0, True)}}

# It can be set up from Reserves in the first battle round (Quantum Invader).
FIRST_ROUND_INGRESS = {"Quantum Invader"}

# After it shoots, the unit it hit can't have the Benefit of Cover this phase.
AFTER_SHOOTING_EFFECTS = {"Targeting Relay": UnitEffect(no_cover=True, lasts="this phase")}

# Systematic Vigour: a Cryptothrall destroyed by a melee attack before it's
# fought fights on, on a 2+.
FIGHTS_ON_DEATH = {"Systematic Vigour": 2}

# Drain Life: at the end of the Fight phase, each enemy unit within 6": 4+,
# D3 mortal wounds.
END_OF_PHASE_EACH_ENEMY = {
    "Drain Life": {"phase": "fight", "turn": "any", "range": 6.0, "on": 4, "wounds": "D3"},
}

# Obelisk Node Control: enemy units can't be set up from Reserves within 12"
# while this model's unit controls an objective it's within range of.
REINFORCEMENT_DENIAL = {"Obelisk Node Control": {"range": 12.0, "on_controlled_objective": True}}

# Grand Strategist: 1CP at the start of its player's Command phase.
COMMAND_START_CP = {"Grand Strategist": 1}

# Ancient Collector: while leading, objectives its unit controls at the end of
# its player's Command phase stay theirs.
SECURES_OBJECTIVES = {"Ancient Collector": "command"}
LEADING_ONLY = {"Ancient Collector"}

# Carrier Wave (Aura): +1 OC for NECRONS units within 6".
OC_AURAS = {"Carrier Wave (Aura)": {"range": 6.0, "keywords": ("NECRONS",), "bonus": 1}}
# The Silent King: +1 Leadership for NECRONS units within 6" of Szarekh.
LEADERSHIP_AURAS = {"The Silent King": {"range": 6.0, "keywords": ("NECRONS",), "bonus": 1}}

# Terrifying Monstrosity: enemy units engaged with it take a Battle-shock test
# at the start of the Fight phase.
FIGHT_START_BATTLE_SHOCK = {"Terrifying Monstrosity"}

# Living Lightning: in its Shooting phase (at its start, here), four D6
# against a visible enemy unit within 18" (not a Lone Operative more than 12"
# away) - 1 mortal wound per 4+.
START_OF_SHOOTING.update(
    {"Living Lightning": {"range": 18.0, "visible": True, "dice": 4, "roll": 4, "lone_operative_within": 12.0}}
)

# Shieldvanes: the bearer has a 3+ Save and an 8" Move.
WARGEAR_CHARACTERISTICS = {"Shieldvanes": {"movement": 8, "save": 3}}

# Harassment Swarm (Aura): an enemy unit (not a MONSTER or VEHICLE) within 3"
# of this unit is -1 to hit (see app/services/in_game/auras.py enemy_rules).
ENEMY_AURAS = {
    "Harassment Swarm (Aura)": {
        "range": 3.0,
        "excluded": ("MONSTER", "VEHICLE"),
        "rules": (Rule(conditions=(ALWAYS,), effects=(MINUS_ONE_TO_HIT,)),),
    },
}

# The Silent King's Triarch Abilities: one selected at the start of each
# battle round (here, in the activations panel), until the next - auras
# from Szarekh for NECRONS units (not MONSTERS) within 6".
from app.combat_rules.effects import PLUS_ONE_STRENGTH  # noqa: E402

_NOT_MONSTERS = ("MONSTER",)
OPTIONS["Triarch Abilities"] = {
    "Phaeron of the Stars": RuleOption(
        rules=(Rule(conditions=(ALWAYS,), effects=(REROLL_HIT_ONES, REROLL_WOUND_ONES)),),
        army_wide=True, aura_range=6.0, aura_excluded=_NOT_MONSTERS,
        description="NECRONS units within 6\" of Szarekh: re-roll Hit and Wound rolls of 1.",
    ),
    "Phaeron of the Blades": RuleOption(
        rules=(Rule(conditions=(MELEE_ATTACK,), effects=(PLUS_ONE_STRENGTH,)),),
        army_wide=True, aura_range=6.0, aura_excluded=_NOT_MONSTERS, charge_rerolls=True,
        description="NECRONS units within 6\" of Szarekh: re-roll Charge rolls, +1 S to melee attacks.",
    ),
    "Relentless March": RuleOption(
        army_wide=True, aura_range=6.0, aura_excluded=_NOT_MONSTERS, move=2,
        description="NECRONS units within 6\" of Szarekh: +2\" Move.",
    ),
}

_PINNED = UnitEffect(move=-2, charge=-2, lasts="my next turn")
_PULSED = UnitEffect(lasts="this turn")
ACTIVATIONS = {
    "Lord of the Storm": {
        "when": "end", "phases": ("command",), "turn": "own", "once": "battle", "effect": "mortals_each_enemy",
        "range": 12.0, "bands": ((6, "D3+3"), (2, "D3")),
        "describe": "Each enemy unit within 12\": 2-5, D3 mortal wounds; 6, D3+3 (end of Command phase).",
    },
    "Tectonic Reverberations": {
        "phases": ("movement",), "turn": "own", "once": "phase", "effect": "unit_effect",
        "target": "enemy", "range": 18.0, "visible": True, "unit_effect": _PINNED,
        "describe": "A visible enemy unit within 18\" is pinned: -2\" Move, -2 to Charge rolls.",
    },
    "Gravitic Pulse": {
        "when": "start", "phases": ("movement",), "turn": "opponent", "once": "phase", "effect": "unit_effect",
        "target": "enemy", "range": 18.0, "visible": True, "unit_effect": _PULSED, "halve": True,
        "describe": (
            "A visible enemy unit within 18\": halve its Move, Advance and Charge rolls this turn; "
            "if it can FLY, D3 mortal wounds on a 4+ each time it ends a move."
        ),
    },
    "Harbinger of Despair": {
        "when": "start", "phases": ("command", "movement", "shooting", "charge", "fight"), "turn": "own",
        "once": "turn", "effect": "battle_shock", "target": "enemy", "range": 18.0, "modifier": -1,
        "describe": "An enemy unit within 18\" takes a Battle-shock test at -1 (start of a phase).",
    },
    "Accelerator Mandible": {
        "when": "start", "phases": ("fight",), "turn": "any", "once": "phase", "effect": "skill", "target": "friendly",
        "range": 3.0, "from_unit": True, "include_self": True, "keywords": ("CANOPTEK",),
        "describe": "A friendly CANOPTEK unit within 3\": +1 Weapon Skill this phase (start of Fight).",
    },
    "Self-destruction": {
        "when": "start", "phases": ("fight",), "turn": "any", "once": "phase", "effect": "self_destruct",
        "target": "enemy", "engaged": True,
        "describe": (
            "Destroy one of its engaged models: an enemy unit engaged with it, D6 (+1 vs VEHICLE): "
            "2-5, D3 mortal wounds; 6+, 3 (start of Fight)."
        ),
    },
    "Invasion Beams": {
        "when": "end", "phases": ("fight",), "turn": "any", "once": "phase", "effect": "embark", "target": "friendly",
        "range": 6.0, "from_unit": True, "keywords": ("NECRONS", "INFANTRY"),
        "describe": "End of Fight: a friendly NECRONS INFANTRY unit wholly within 6\" embarks (if empty).",
    },
    "Triarch Abilities": {
        "phases": "round_start", "required": True, "turn": "any", "once": "round", "effect": "choose", "target": "option",
        "options": ("Phaeron of the Stars", "Phaeron of the Blades", "Relentless March"),
        "from_model": "Szarekh",
        "describe": "Select a Triarch ability until the next battle round (start of the round).",
    },
    "Eternity Gate": {
        "phases": ("movement",), "turn": "own", "once": "phase", "effect": "gate", "target": "friendly",
        "anywhere": True, "keywords": ("NECRONS", "INFANTRY"), "not_first_round": True,
        "describe": (
            "A friendly NECRONS INFANTRY unit (in Reserves, or taken off the battlefield) arrives "
            "wholly within 6\" of the Monolith this phase - and can't charge."
        ),
    },
    "Surrogate Hosts": {
        "when": "start", "phases": ("command",), "turn": "own", "once": "phase", "effect": "surrogate",
        "target": "friendly", "anywhere": True, "keywords": ("NECRONS", "INFANTRY", "CHARACTER"),
        "describe": "Another NECRONS INFANTRY CHARACTER model is destroyed, and Trazyn takes its place.",
    },
    "Grand Illusion": {
        "phases": "pre_battle", "turn": "own", "once": "battle", "effect": "grand_illusion",
        "target": "friendly", "anywhere": True, "keywords": ("NECRONS",), "uses": 3,
        "describe": "After deployment: up to three NECRONS units go into Strategic Reserves.",
    },
}

# Shots in the opponent's turn (see app/services/in_game/reactive_shots.py):
# Hyperspace Hunters - at an enemy unit set up from Reserves within 18" of and
# visible to it; Multi-threat Eliminator - at an enemy unit that shot a
# friendly NECRONS unit within 3" of it. Once a turn each.
REACTIVE_SHOTS = {
    "Hyperspace Hunters": {"trigger": "arrived", "range": 18.0},
    "Multi-threat Eliminator": {"trigger": "shot_friend", "range": 3.0, "keywords": ("NECRONS",)},
}

# Bound Creation: while Cryptothralls are in the same unit as a CRYPTEK model
# (a Cryptek Retinue joined to it), that model has Feel No Pain 4+.
from app.seeds.factions.necrons.conditions import TARGET_MODEL_CRYPTEK  # noqa: E402

RULES["Bound Creation"] = [
    Rule(
        conditions=(TARGET_MODEL_CRYPTEK,),
        effects=(FEEL_NO_PAIN_4,),
        side="defender",
        description="A CRYPTEK model in the same unit has Feel No Pain 4+.",
    ),
]
