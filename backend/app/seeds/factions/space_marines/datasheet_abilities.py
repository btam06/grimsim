from app.combat_rules import Rule, RuleOption
from app.combat_rules.conditions import ALWAYS
from app.combat_rules.effects import (
    ADD_EXTRA_HIT,
    AUTO_PASS_WOUND,
    MINUS_ONE_TO_HIT,
    MINUS_ONE_TO_WOUND,
    PRECISION,
    REROLL_HIT_ONES,
    REROLL_WOUND_ONES,
)
from app.seeds.factions.space_marines.conditions import (
    ASSAULT_DOCTRINE_TARGET_WITHIN_9,
    CHARGED_CLAWS_CRITICAL_VS_NON_MONSTER_VEHICLE,
    CHARGED_HAMMER_CRITICAL_VS_MONSTER_VEHICLE,
    DEVASTATOR_DOCTRINE_CRITICAL_HIT,
    STANDARD_FALL,
    TACTICAL_DOCTRINE_CRITICAL_HIT,
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
]

# Code-defined rules for abilities above: {ability name: [Rule, ...]}.
RULES = {
    "Never Shall the Standard Fall": [
        Rule(
            conditions=(STANDARD_FALL,),
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
            conditions=(CHARGED_CLAWS_CRITICAL_VS_NON_MONSTER_VEHICLE,),
            effects=(ADD_EXTRA_HIT,),
            description=(
                "After charging: Lightning Claws have [SUSTAINED HITS 1] against a unit with no "
                "MONSTER or VEHICLE model."
            ),
        ),
        Rule(
            conditions=(CHARGED_HAMMER_CRITICAL_VS_MONSTER_VEHICLE,),
            effects=(ADD_EXTRA_HIT,),
            description=(
                "After charging: Thunder Hammers have [SUSTAINED HITS 1] against a unit with a "
                "MONSTER or VEHICLE model."
            ),
        ),
    ],
    "Furor Tactics": [
        Rule(
            conditions=(DEVASTATOR_DOCTRINE_CRITICAL_HIT,),
            effects=(ADD_EXTRA_HIT,),
            description="[SUSTAINED HITS 1] while the Devastator Doctrine is active.",
        ),
    ],
    "Malleus Tactics": [
        Rule(
            conditions=(TACTICAL_DOCTRINE_CRITICAL_HIT,),
            effects=(AUTO_PASS_WOUND,),
            description="[LETHAL HITS] while the Tactical Doctrine is active.",
        ),
    ],
    "Purgatus Tactics": [
        Rule(
            conditions=(ASSAULT_DOCTRINE_TARGET_WITHIN_9,),
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
OPTIONS = {
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
    "Psychic Hood": "Descriptive only: psychic attacks aren't modelled yet.",
    "Codex Adept": (
        "Pick the doctrines under Faction Rules in the calculator; in a game, all three are "
        "active for this unit."
    ),
    "Author of the Codex": "Descriptive only: not modelled in a game yet.",
    "Leader of Astartes": (
        "Descriptive only in the calculator; in a game, models more than 12\" away can't shoot "
        "it while it's within 3\" of a friendly ADEPTUS ASTARTES INFANTRY unit."
    ),
}

# In a game: abilities that gain their player CP at the start of each battle
# round while a model with one is their WARLORD (see
# app/services/in_game/battle_round.py).
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
SECURES_OBJECTIVES = {"Raise the Banner": "movement"}

# In a game: psyker levels, by the ability that gives one, and psychic
# abilities' levels (see app/services/in_game/psychic.py).
PSYKER_LEVELS = {"Librarian": 1}
PSYCHIC_ABILITIES = {"Shrouding": 1, "Soul Sight": 1}
