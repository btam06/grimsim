from app.combat_rules.conditions import (
    DEFENDER_IN_RANGE_OF_OBJECTIVE,
    IN_RANGE_OF_OBJECTIVE,
)
from app.seeds.factions.adeptus_mechanicus.conditions import (
    ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
    ATTACKER_NEAR_ADMECH_BATTLELINE,
    MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
    NEAR_ADMECH_BATTLELINE,
)

# Positions the calculator asks about, since it can't measure the table:
# {position: label}. A combat request lists each side's positions.
POSITIONS = {
    NEAR_ADMECH_BATTLELINE: 'Within 6" of a friendly ADEPTUS MECHANICUS BATTLELINE unit',
    IN_RANGE_OF_OBJECTIVE: "Within range of an objective marker",
}

# The conditions that read each position, by the side whose position it is -
# a position is only asked about for a unit with a rule using one of them
# (e.g. Doctrina Imperatives, Breaching Command).
POSITION_CONDITIONS = {
    NEAR_ADMECH_BATTLELINE: {
        "attacker": {
            ATTACKER_NEAR_ADMECH_BATTLELINE,
            ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
        },
        "defender": {MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE},
    },
    IN_RANGE_OF_OBJECTIVE: {"attacker": set(), "defender": {DEFENDER_IN_RANGE_OF_OBJECTIVE}},
}

# Positions asked about for every unit on a side, whatever its rules - board
# state as general as cover (e.g. stratagems like Scriptural Prognosis read
# whether the defender is on an objective): {position: sides}.
ALWAYS_ASKED = {IN_RANGE_OF_OBJECTIVE: {"defender"}}
