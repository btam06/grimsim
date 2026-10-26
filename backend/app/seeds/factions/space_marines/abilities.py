from app.combat_rules import Rule
from app.combat_rules.conditions import ALWAYS
from app.combat_rules.effects import ASSAULT

COMBAT_DOCTRINES = "Combat Doctrines"
LIBRARIUS = "Librarius"

# (ability name, description)
ENTRIES = [
    (
        "Oath of Moment",
        "The army designates one enemy unit as the target of its Oath of Moment, improving rolls against it.",
    ),
    (
        # Its options are in OPTIONS below; in a game, it's chosen in the
        # Command phase (COMMAND_PHASE_CHOICES).
        COMBAT_DOCTRINES,
        "At the start of your Command phase, you can select one combat doctrine listed below. "
        "If you do, that combat doctrine is active for friendly ADEPTUS ASTARTES units with this "
        "ability until the start of your next Command phase.\n"
        "Assault Doctrine: When this unit is selected to make an advance move, that advance move "
        "does not prevent this unit from being eligible to declare a charge.\n"
        "Devastator Doctrine: This unit's ranged attacks have [ASSAULT].\n"
        "Tactical Doctrine: When this unit is selected to make a fall-back move, that fall-back "
        "move does not prevent this unit from being eligible to shoot and eligible to declare a "
        "charge.\n"
        "Unless otherwise stated:\n"
        "- You can only select each combat doctrine once per battle.\n"
        "- Only one combat doctrine can be active for each unit. If a rule makes a combat "
        "doctrine active for a unit, any combat doctrine previously active for that unit is no "
        "longer active for that unit.",
    ),
    (
        # In a game, see app/services/in_game/psychic.py.
        LIBRARIUS,
        "ADEPTUS ASTARTES PSYKER units with this ability have a psyker level of 1 or higher, "
        "specified in that unit's abilities. Each psychic ability has a psychic level of 1 or "
        "higher, specified in that ability's name.\n"
        "In a battle round, a friendly ADEPTUS ASTARTES PSYKER unit can use a number of psychic "
        "abilities whose total psychic level does not exceed that PSYKER unit's psyker level.\n"
        "Example: In a battle round, a psyker level 3 PSYKER unit could use three psychic level "
        "1 abilities, or one psychic level 1 ability and one psychic level 2 ability, or one "
        "psychic level 3 ability.",
    ),
]

# Rule options for abilities above: {ability name: {option name: [Rule, ...]}}.
# Only the Devastator Doctrine matters in the calculator (its weapons'
# [ASSAULT]); the Assault and Tactical Doctrines are about what a unit can do
# after Advancing or Falling Back (ELIGIBLE_AFTER, in a game).
OPTIONS = {
    COMBAT_DOCTRINES: {
        "Assault Doctrine": [],
        "Devastator Doctrine": [
            Rule(
                conditions=(ALWAYS,),
                effects=(ASSAULT,),
                description="Ranged weapons have [ASSAULT].",
            ),
        ],
        "Tactical Doctrine": [],
    },
}

# How the calculator handles abilities above, where that needs saying.
CALCULATOR_NOTES = {
    LIBRARIUS: (
        "Descriptive only in the calculator; in a game, each PSYKER unit's psychic abilities "
        "are limited by its psyker level each battle round."
    ),
    COMBAT_DOCTRINES: (
        "Pick the Devastator Doctrine under Faction Rules for [ASSAULT] ranged weapons; the "
        "Assault and Tactical Doctrines change what a unit can do after Advancing or Falling "
        "Back (in a game, they're applied)."
    ),
}

# In a game (see app/services/in_game/command_phase.py): army rules whose
# option is selected in the player's Command phase (or none), active until
# the start of their next one - each option only once per battle
# (ONCE_PER_BATTLE) - with what each option does there.
COMMAND_PHASE_CHOICES = {COMBAT_DOCTRINES}
ONCE_PER_BATTLE = {COMBAT_DOCTRINES}
COMMAND_PHASE_DESCRIPTIONS = {
    COMBAT_DOCTRINES: {
        "Assault Doctrine": "Advancing doesn't stop a unit declaring a charge.",
        "Devastator Doctrine": "Ranged attacks have [ASSAULT]: a unit can shoot after "
        "Advancing.",
        "Tactical Doctrine": "Falling Back doesn't stop a unit shooting or declaring a charge.",
    },
}
# What an option lets a unit with the rule still do after Advancing
# ("advanced") or Falling Back ("fell_back") in its turn: "shoot", "charge".
ELIGIBLE_AFTER = {
    "Assault Doctrine": {"advanced": ("charge",)},
    "Tactical Doctrine": {"fell_back": ("shoot", "charge")},
}
