from app.combat_rules import (
    CommandChoice,
    FightAbility,
    FormationGrant,
    Rule,
    RuleOption,
    UnitEffect,
)
from app.combat_rules.conditions import (
    ALWAYS,
    CHARGED,
    CRITICAL_HIT,
    DEFENDER_CONTROLLING_OBJECTIVE,
    DEFENDER_IN_RANGE_OF_OBJECTIVE,
    MELEE_ATTACK,
    RANGED_ATTACK,
    STRENGTH_EXCEEDS_TOUGHNESS,
    TARGET_MONSTER_OR_VEHICLE,
    TARGET_NOT_MONSTER_OR_VEHICLE,
    TARGET_WITHIN_9,
)
from app.combat_rules.effects import (
    ADD_EXTRA_ATTACK,
    ADD_EXTRA_HIT,
    AUTO_PASS_WOUND,
    FEEL_NO_PAIN_4,
    MINUS_ONE_TO_HIT,
    MINUS_ONE_TO_WOUND,
    PLUS_ONE_STRENGTH,
    PLUS_ONE_TO_SAVE,
    PLUS_ONE_TO_WOUND,
    PRECISION,
    REROLL_DAMAGE,
    REROLL_HIT_ONES,
    REROLL_WOUND_ONES,
)
from app.seeds.factions.space_marines.conditions import (
    ASSAULT_DOCTRINE_ACTIVE,
    CALGARS_CHAMPION_ATTACK,
    MELEE_PRE_WEAPON,
    PSYCHIC_ATTACK,
    TARGET_MODEL_OTHER_CHARACTER,
    DEVASTATOR_DOCTRINE_ACTIVE,
    LIGHTNING_CLAWS_WEAPON,
    TACTICAL_DOCTRINE_ACTIVE,
    THUNDER_HAMMER_WEAPON,
)

# Space Marines datasheet abilities - see app/seeds/datasheet_abilities.py for
# what each of these holds. Core abilities (e.g. Stealth) are defined there,
# and some are shared with other factions (e.g. Supreme Commander, in the
# Adeptus Mechanicus file).

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Transhuman Strategist",
        "At the start of the battle round, if a model with this ability is your WARLORD, gain "
        "1CP.",
        [],
        [],
    ),
    (
        "Raise the Banner",
        "At the end of your Movement phase, if this unit is controlling an objective, that "
        "objective is secured.",
        [],
        [],
    ),
    (
        "Never Shall the Standard Fall",
        "While this unit is within range of an objective, attacks that target this unit with a "
        "S greater than this unit's T have -1 to wound rolls.",
        [],
        [],
    ),
    (
        "Teleport Homer",
        "Once per battle, per unit: at the start of the battle, you can set up one Teleport "
        "Homer token for this unit on the battlefield. If you do:\n"
        "- When you target this unit with the Rapid Ingress stratagem, you can use that Teleport "
        "Homer token. If you do, that use is -1 CP, but when resolving that stratagem, this unit "
        "must be set up within 3\" of that Teleport Homer token and not within 8\" of an enemy "
        "unit. That Teleport Homer token is then removed from the battlefield.\n"
        "- If an enemy unit ends a move within 1\" of that Teleport Homer token, that Teleport "
        "Homer token is removed from the battlefield.",
        [],
        [],
    ),
    (
        "Terminatus Assault",
        "If this unit made a charge move this turn, this unit's:\n"
        "- Lightning Claws weapons have [SUSTAINED HITS 1: non-Monster/Vehicle].\n"
        "- Thunder Hammer weapons have [SUSTAINED HITS 1: Monster/Vehicle].",
        [],
        [],
    ),
    (
        "Shrouding",
        "Psychic level 1. When an enemy unit targets this unit, if this unit is not "
        "battle-shocked, you can make a psychic roll for this unit by rolling one D6. If you "
        "do:\n"
        "- On a 1, this unit is battle-shocked.\n"
        "- Attacks that target this unit have -1 to hit rolls until the end of the phase.",
        [],
        [],
    ),
    (
        "Soul Sight",
        "Psychic level 1. In your Shooting phase, if this unit is not battle-shocked, you can "
        "make a psychic roll for this unit by rolling one D6. If you do:\n"
        "- On a 1, this unit is battle-shocked.\n"
        "- Select one visible enemy unit. Ranged attacks that target that enemy unit have "
        "[IGNORES COVER].",
        [],
        [],
    ),
    (
        "Librarian",
        "Psyker level 1. This model has the psychic abilities listed in the Psychic Abilities "
        "section.",
        [],
        [],
    ),
    (
        "Psychic Hood",
        "Psychic. This unit has Feel No Pain 4+ against psychic attacks.",
        [],
        [],
    ),
    (
        "Codex Adept",
        "The assault doctrine, devastator doctrine and tactical doctrine are active for this "
        "unit.",
        [],
        [],
    ),
    (
        # Its option is in OPTIONS below.
        "Primarch of the XIII (Aura)",
        "While a friendly ADEPTUS ASTARTES unit is within 6\" of this unit, that unit's attacks "
        "can:\n"
        "- Re-roll hit rolls of 1.\n"
        "- Re-roll wound rolls of 1.",
        [],
        [],
    ),
    (
        "Author of the Codex",
        "In your Movement phase, you can select one visible friendly ADEPTUS ASTARTES unit "
        "within 12\" of this model, and select one combat doctrine. That combat doctrine is "
        "active for that unit in addition to any other combat doctrines that are active for "
        "that unit until the start of your next Command phase.",
        [],
        [],
    ),
    (
        "Leader of Astartes",
        "While this unit is within 3\" of a friendly ADEPTUS ASTARTES INFANTRY unit, this unit "
        "has Lone Operative.",
        [],
        [],
    ),
    (
        "Unyielding in the Face of the Foe",
        "While this unit is controlling an objective, this unit has +1 to save rolls.",
        [],
        [],
    ),
    (
        # In a game, see SHOCK_DISEMBARK_AFTER below.
        "Rapid Disembarkation",
        "In your Movement phase, when this unit ends an advance move, units embarked within "
        "this unit can make a shock disembark move.",
        [],
        [],
    ),
    (
        # The Deathwatch Terminator Squad's - not the Terminator Assault
        # Squad's Terminatus Assault, which shares its name.
        "Terminatus Assault (Deathwatch)",
        "This unit can re-roll charge rolls. After this unit ends a charge move, each enemy unit "
        "engaged with this unit makes a battle-shock roll, with -1 to that battle-shock roll if "
        "it's a non-IMPERIUM/CHAOS unit.",
        [],
        [],
    ),
    (
        "Total Obliteration",
        "This unit's ranged attacks can re-roll damage rolls.",
        [],
        [],
    ),
    (
        "Flexible Asset",
        "When this unit is selected to make an advance/fall-back move, that advance/fall-back "
        "move does not prevent this unit from being eligible to start an action.",
        [],
        [],
    ),
    # Granted to KILL TEAM units by Deathwatch Support's Mission Tactics (see
    # detachments.json).
    (
        "Furor Tactics",
        "If the devastator doctrine is active for your unit, your unit's attacks have "
        "[SUSTAINED HITS 1].",
        [],
        [],
    ),
    (
        "Malleus Tactics",
        "If the tactical doctrine is active for your unit, your unit's attacks have "
        "[LETHAL HITS].",
        [],
        [],
    ),
    (
        "Purgatus Tactics",
        "If the assault doctrine is active for your unit, your unit's attacks that target an "
        "enemy unit within 9\" of this unit have [PRECISION].",
        [],
        [],
    ),
    (
        "Master Tactician",
        "In your Movement phase, you can select one visible friendly ADEPTUS ASTARTES unit "
        "within 9\" of this model, and select one combat doctrine. That combat doctrine is "
        "active for that unit until the start of your next Command phase.",
        [],
        [],
    ),
    (
        "Thunderhawk Insertion",
        "In the Declare Battle Formations step, you can select one friendly GRAVIS/PHOBOS/"
        "TACTICUS unit. That unit has Deep Strike.",
        [],
        [],
    ),
    (
        "Veteran Bodyguard",
        "While this model is attached to a unit, other CHARACTER models in this unit have Feel "
        "No Pain 4+.",
        [],
        [],
    ),
    (
        "Calgar's Champion",
        "This model's attacks that target a CHARACTER unit can:\n"
        "- Re-roll hit rolls of 1.\n"
        "- Re-roll wound rolls of 1.",
        [],
        [],
    ),
    (
        "Glory of Ultramar",
        "In your opponent's Shooting phase, when an enemy unit has shot, if a model in this unit "
        "was destroyed by those attacks, this unit can make a surge move of up to D6\".",
        [],
        [],
    ),
    (
        "Honour Guard of Macragge",
        "Attacks that target this unit have -1 to wound rolls.",
        [],
        [],
    ),
    (
        "Banner of Macragge",
        "- At the end of your Movement phase, if this unit is controlling an objective, that "
        "objective is secured.\n"
        "- (Once per battle, per army) When this unit is selected to fight, you can use this "
        "ability. If you do, this unit's melee attacks have +1 A and S.",
        [],
        [],
    ),
    (
        "Command Squad",
        "Attacks that target this unit have -1 to wound rolls.",
        [],
        [],
    ),
    (
        "Thunderstrike",
        "This unit's ranged attacks that target a MONSTER/VEHICLE unit have +1 to wound rolls.",
        [],
        [],
    ),
    (
        "Shattered Defences",
        "In your Shooting phase, when this unit has shot, select one enemy MONSTER/VEHICLE unit "
        "hit by those attacks. Friendly ADEPTUS ASTARTES units' ranged attacks that target that "
        "enemy unit have +1 AP.",
        [],
        [],
    ),
]

# Code-defined rules for abilities above: {ability name: [Rule, ...]}.
RULES = {
    "Psychic Hood": [
        Rule(
            conditions=(PSYCHIC_ATTACK,),
            effects=(FEEL_NO_PAIN_4,),
            side="defender",
            description="Feel No Pain 4+ against attacks with [PSYCHIC] weapons.",
        ),
    ],
    "Veteran Bodyguard": [
        Rule(
            conditions=(TARGET_MODEL_OTHER_CHARACTER,),
            effects=(FEEL_NO_PAIN_4,),
            side="defender",
            description="Other CHARACTER models in its unit have Feel No Pain 4+.",
        ),
    ],
    "Calgar's Champion": [
        Rule(conditions=(CALGARS_CHAMPION_ATTACK,), effects=(REROLL_HIT_ONES,)),
        Rule(
            conditions=(CALGARS_CHAMPION_ATTACK,),
            effects=(REROLL_WOUND_ONES,),
            description=(
                "This model's attacks (not its unit's) against a unit with a CHARACTER re-roll "
                "hit rolls of 1 and wound rolls of 1."
            ),
        ),
    ],
    "Honour Guard of Macragge": [
        Rule(
            conditions=(ALWAYS,),
            effects=(MINUS_ONE_TO_WOUND,),
            side="defender",
            description="Attacks that target this unit are -1 to wound.",
        ),
    ],
    "Command Squad": [
        Rule(
            conditions=(ALWAYS,),
            effects=(MINUS_ONE_TO_WOUND,),
            side="defender",
            description="Attacks that target this unit are -1 to wound.",
        ),
    ],
    "Thunderstrike": [
        Rule(
            conditions=(RANGED_ATTACK, TARGET_MONSTER_OR_VEHICLE),
            effects=(PLUS_ONE_TO_WOUND,),
            description="Ranged attacks against a MONSTER or VEHICLE unit are +1 to wound.",
        ),
    ],
    "Never Shall the Standard Fall": [
        Rule(
            conditions=(DEFENDER_IN_RANGE_OF_OBJECTIVE, STRENGTH_EXCEEDS_TOUGHNESS),
            effects=(MINUS_ONE_TO_WOUND,),
            side="defender",
            description=(
                "Attacks against this unit with Strength greater than its Toughness are -1 to "
                "wound while it's within range of an objective (ticked under Positioning)."
            ),
        ),
    ],
    "Terminatus Assault": [
        Rule(
            conditions=(
                CRITICAL_HIT, CHARGED, LIGHTNING_CLAWS_WEAPON, TARGET_NOT_MONSTER_OR_VEHICLE
            ),
            effects=(ADD_EXTRA_HIT,),
            description=(
                "After charging: Lightning Claws have [SUSTAINED HITS 1] against a unit with no "
                "MONSTER or VEHICLE model."
            ),
        ),
        Rule(
            conditions=(CRITICAL_HIT, CHARGED, THUNDER_HAMMER_WEAPON, TARGET_MONSTER_OR_VEHICLE),
            effects=(ADD_EXTRA_HIT,),
            description=(
                "After charging: Thunder Hammers have [SUSTAINED HITS 1] against a unit with a "
                "MONSTER or VEHICLE model."
            ),
        ),
    ],
    "Total Obliteration": [
        Rule(
            conditions=(RANGED_ATTACK,),
            effects=(REROLL_DAMAGE,),
            description="Ranged attacks re-roll a damage roll below its average.",
        ),
    ],
    "Unyielding in the Face of the Foe": [
        Rule(
            conditions=(DEFENDER_CONTROLLING_OBJECTIVE,),
            effects=(PLUS_ONE_TO_SAVE,),
            side="defender",
            description=(
                "+1 to save rolls while this unit is controlling an objective (ticked under "
                "Positioning)."
            ),
        ),
    ],
    "Furor Tactics": [
        Rule(
            conditions=(CRITICAL_HIT, DEVASTATOR_DOCTRINE_ACTIVE),
            effects=(ADD_EXTRA_HIT,),
            description="[SUSTAINED HITS 1] while the Devastator Doctrine is active.",
        ),
    ],
    "Malleus Tactics": [
        Rule(
            conditions=(CRITICAL_HIT, TACTICAL_DOCTRINE_ACTIVE),
            effects=(AUTO_PASS_WOUND,),
            description="[LETHAL HITS] while the Tactical Doctrine is active.",
        ),
    ],
    "Purgatus Tactics": [
        Rule(
            conditions=(ASSAULT_DOCTRINE_ACTIVE, TARGET_WITHIN_9),
            effects=(PRECISION,),
            description=(
                "[PRECISION] while the Assault Doctrine is active, against a target within 9\" "
                "(ticked under Positioning)."
            ),
        ),
    ],
}

# Selectable options for abilities above: {ability name: {option name:
# RuleOption}} - here, an aura that's always on.
# Banner of Macragge's once-a-battle boost: +1 A and S to melee attacks.
_BANNER_RULES = (
    Rule(conditions=(MELEE_PRE_WEAPON,), effects=(ADD_EXTRA_ATTACK,)),
    Rule(conditions=(MELEE_ATTACK,), effects=(PLUS_ONE_STRENGTH,)),
)

OPTIONS = {
    "Banner of Macragge": {
        "Banner of Macragge (fight)": RuleOption(
            rules=_BANNER_RULES,
            description=(
                "Its once-a-battle use when selected to fight: this unit's melee attacks have "
                "+1 A and S."
            ),
        ),
    },
    # In a game, active for the phase once it's used (see
    # app/services/in_game/psychic.py).
    "Shrouding": {
        "Shrouded": RuleOption(
            rules=(Rule(conditions=(ALWAYS,), effects=(MINUS_ONE_TO_HIT,), side="defender"),),
            description="Attacks that target this unit are -1 to hit (Shrouding used this phase).",
        ),
    },
    "Primarch of the XIII (Aura)": {
        "Primarch of the XIII": RuleOption(
            rules=(
                Rule(conditions=(ALWAYS,), effects=(REROLL_HIT_ONES,)),
                Rule(conditions=(ALWAYS,), effects=(REROLL_WOUND_ONES,)),
            ),
            army_wide=True,
            aura_range=6.0,
            description=(
                "This unit, or another ADEPTUS ASTARTES unit in the army list, is within 6\": "
                "re-roll hit rolls of 1 and wound rolls of 1."
            ),
        ),
    },
}

# How the calculator handles abilities above, where that needs saying.
CALCULATOR_NOTES = {
    "Master Tactician": (
        "Pick the doctrine under Faction Rules for the unit selected; in a game, it's selected "
        "in your Movement phase for a visible friendly ADEPTUS ASTARTES unit within 9\"."
    ),
    "Thunderhawk Insertion": (
        "Descriptive only in the calculator; in a game, its player selects the GRAVIS, PHOBOS "
        "or TACTICUS unit given Deep Strike as they declare their battle formations."
    ),
    "Glory of Ultramar": (
        "Descriptive only in the calculator; in a game, its surge move (D6\") starts when an "
        "enemy unit's shooting destroys one of its models."
    ),
    "Banner of Macragge": (
        "Pick its fight option for its once-a-battle +1 A and S; in a game, objectives it's "
        "controlling at the end of your Movement phase are secured, and its player can use the "
        "+1 A and S when it's selected to fight (once a battle, for the army)."
    ),
    "Shattered Defences": (
        "Descriptive only in the calculator (tick +1 AP for the attacker); in a game, the "
        "MONSTER or VEHICLE unit it shoots and hits in its Shooting phase gives friendly "
        "ADEPTUS ASTARTES units' ranged attacks against it +1 AP, for the rest of the turn."
    ),
    "Transhuman Strategist": (
        "Descriptive only in the calculator; in a game, its player gains 1CP at the start of "
        "each battle round while it's their Warlord."
    ),
    "Raise the Banner": (
        "Descriptive only in the calculator; in a game, objectives it's controlling at the end "
        "of your Movement phase are secured."
    ),
    "Teleport Homer": (
        "Descriptive only in the calculator; in a game, its token is set up at the start of the "
        "battle and can be used with Rapid Ingress."
    ),
    "Shrouding": (
        "Pick Shrouded for the defending unit when it's been used this phase; in a game, its "
        "player uses it as an enemy attacks it."
    ),
    "Soul Sight": (
        "Descriptive only in the calculator (untick cover for the target); in a game, ranged "
        "attacks against the unit it picks ignore cover that phase."
    ),
    "Librarian": "Descriptive only; in a game, it's this unit's psyker level (1).",
    "Codex Adept": (
        "Pick the doctrines under Faction Rules in the calculator; in a game, all three are "
        "active for this unit."
    ),
    "Author of the Codex": (
        "Pick the doctrine under Faction Rules for the unit selected; in a game, it's selected "
        "in your Movement phase for a visible friendly ADEPTUS ASTARTES unit within 12\"."
    ),
    "Terminatus Assault (Deathwatch)": (
        "Descriptive only in the calculator; in a game, the unit can re-roll its charge roll, "
        "and enemy units engaged with it after its charge move take Battle-shock tests."
    ),
    "Flexible Asset": (
        "Descriptive only in the calculator; in a game, Advancing or Falling Back doesn't stop "
        "it starting an action."
    ),
    "Rapid Disembarkation": (
        "Descriptive only in the calculator; in a game, units can disembark from it after it "
        "Advanced (a shock disembark: they can't declare a charge that turn)."
    ),
    "Leader of Astartes": (
        "Descriptive only in the calculator; in a game, models more than 12\" away can't shoot "
        "it while it's within 3\" of a friendly ADEPTUS ASTARTES INFANTRY unit."
    ),
}

# In a game: abilities that gain their player CP at the start of each battle
# round while a model with one is their WARLORD (see
# app/services/in_game/battle_round.py).
# In a game: abilities whose option is selected in one of their owner's
# phases (see app/services/in_game/command_phase.py) - Author of the Codex:
# in the Movement phase, for a visible friendly ADEPTUS ASTARTES unit within
# 12", until the start of their next Command phase - its options Combat
# Doctrines' (the doctrine is active for that unit as if its own Combat
# Doctrines had it, so its rules come from there).
COMMAND_CHOICES = {
    # Master Tactician: the same, within 9".
    "Master Tactician": CommandChoice(
        required=False,
        target_keywords=("ADEPTUS ASTARTES",),
        target_range=9.0,
        target_visible=True,
        phase="movement",
        faction_options=("Space Marines", "Combat Doctrines"),
    ),
    "Author of the Codex": CommandChoice(
        required=False,
        target_keywords=("ADEPTUS ASTARTES",),
        target_range=12.0,
        target_visible=True,
        phase="movement",
        faction_options=("Space Marines", "Combat Doctrines"),
    ),
}

ROUND_START_CP = {"Transhuman Strategist": 1}

# In a game: abilities that make army rule options active for their unit all
# the time (see app/services/in_game/command_phase.py).
ALWAYS_ACTIVE_OPTIONS = {
    "Codex Adept": ("Assault Doctrine", "Devastator Doctrine", "Tactical Doctrine"),
}

# In a game: abilities that give their unit Lone Operative while within a
# distance of a friendly unit with some keywords (see
# app/services/in_game/shooting.py).
CONDITIONAL_LONE_OPERATIVE = {"Leader of Astartes": (3.0, ("ADEPTUS ASTARTES", "INFANTRY"))}

# Wargear that adds to its bearer's Wounds characteristic, by wargear name.
WARGEAR_WOUNDS = {"Storm Shield": 1}

# In a game: abilities that secure the objectives their unit is controlling at
# the end of one of their player's phases (see
# app/services/in_game/objectives.py).
SECURES_OBJECTIVES = {"Raise the Banner": "movement", "Banner of Macragge": "movement"}

# In a game: psyker levels, by the ability that gives one, and psychic
# abilities' levels (see app/services/in_game/psychic.py).
PSYKER_LEVELS = {"Librarian": 1}
PSYCHIC_ABILITIES = {"Shrouding": 1, "Soul Sight": 1}

# In a game: transport abilities that let units embarked in it make a shock
# disembark move after it made one of these moves (see
# app/services/in_game/embarked.py).
SHOCK_DISEMBARK_AFTER = {"Rapid Disembarkation": ("advance",)}

# In a game (see app/services/in_game/charging.py): abilities that let their
# unit re-roll its charge roll, and that make the enemy units engaged with it
# after its charge move take a Battle-shock test - with this modifier, unless
# they have one of these keywords.
CHARGE_REROLLS = {"Terminatus Assault (Deathwatch)"}
AFTER_CHARGE_BATTLE_SHOCK = {"Terminatus Assault (Deathwatch)": (-1, ("IMPERIUM", "CHAOS"))}

# In a game: abilities whose unit can still start an action after these moves
# (see app/services/in_game/actions.py).
ACTION_AFTER = {"Flexible Asset": ("advanced", "fell_back")}


# In a game: abilities whose unit, after shooting in its Shooting phase, does
# something to an enemy unit it hit (see app/services/in_game/unit_effects.py)
# - Shattered Defences: for the rest of the turn (the text gives no end; its
# effect is on ranged attacks, so in practice that Shooting phase).
AFTER_SHOOTING_EFFECTS = {
    "Shattered Defences": UnitEffect(
        required_keywords=("MONSTER", "VEHICLE"),
        ranged_ap=1,
        by_keyword="ADEPTUS ASTARTES",
        lasts="this turn",
    ),
}

# In a game: abilities that let their unit surge after an enemy unit's
# shooting destroys one of its models, in its opponent's Shooting phase - how
# far (see app/services/in_game/surge.py).
SURGE_WHEN_SHOT = {"Glory of Ultramar": "D6"}


# In a game: abilities that, at Declare Battle Formations, give one of their
# player's units an ability (see app/services/in_game/battle_formations.py).
FORMATION_GRANTS = {
    "Thunderhawk Insertion": FormationGrant(
        keywords=("GRAVIS", "PHOBOS", "TACTICUS"), grants="Deep Strike"
    ),
}

# In a game: abilities their unit can use when it's selected to fight (see
# app/services/in_game/fight_abilities.py).
FIGHT_ABILITIES = {
    "Banner of Macragge": FightAbility(rules=_BANNER_RULES, per_army=True),
}
