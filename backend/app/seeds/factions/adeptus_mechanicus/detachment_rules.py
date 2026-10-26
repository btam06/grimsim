from app.seeds.factions.adeptus_mechanicus.conditions import (
    ON_ACQUISITION,
    TARGET_ON_ACQUISITION,
)

# In a game: what Adeptus Mechanicus detachment rules and enhancements (see
# app/data/factions/adeptus_mechanicus/) do beyond the combat abilities they
# grant. The factions package combines every faction's.

ACQUISITION = "Acquisition"

# Detachment rules that have their player select an objective marker at the
# start of their Command phase (see app/services/in_game/selected_objectives.py):
# {rule name: {"name": the selection, "position": a unit within range of it,
# "target_position": an attack's target within range of it}} - Acquisition At
# Any Cost.
OBJECTIVE_SELECTIONS = {
    "Acquisition At Any Cost": {
        "name": ACQUISITION,
        "position": ON_ACQUISITION,
        "target_position": TARGET_ON_ACQUISITION,
    },
}

# Enhancements that gain 1CP at the end of the bearer's Command phase, on a
# `roll`+, while it's within range of one of its player's `within` objectives
# - Magos.
END_OF_COMMAND_CP = {"Magos": {"roll": 4, "within": ACQUISITION}}
