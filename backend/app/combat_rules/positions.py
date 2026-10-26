from app.combat_rules.conditions import (
    BELOW_HALF_STRENGTH,
    BELOW_STARTING_STRENGTH,
    CONTROLLING_OBJECTIVE,
    DEFENDER_BELOW_HALF_STRENGTH,
    DEFENDER_BELOW_STARTING_STRENGTH,
    DEFENDER_CONTROLLING_OBJECTIVE,
    DEFENDER_IN_RANGE_OF_OBJECTIVE,
    IN_RANGE_OF_OBJECTIVE,
    ISOLATED_TARGET,
    REMAINED_STATIONARY,
    STATIONARY_RANGED_CRITICAL_HIT,
    TARGET_ISOLATED,
    TARGET_WITHIN_9,
    WITHIN_9_OF_TARGET,
)
from app.seeds.factions.adeptus_mechanicus.conditions import (
    ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
    ATTACKER_NEAR_ADMECH_BATTLELINE,
    MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
    NEAR_ADMECH_BATTLELINE,
    VENGEANCE,
    VENGEANCE_ACTIVE,
)
from app.seeds.factions.chaos_knights.conditions import (
    MARKED_PREY_CRITICAL_HIT,
    MARKED_PREY_TARGET,
)
from app.seeds.factions.necrons.conditions import (
    ATTACKER_IN_POWER_MATRIX,
    ATTACKER_SET_UP_THIS_TURN,
    COLD_FERVOUR_SPREAD,
    COLD_FERVOUR_TRIGGERED,
    RANGED_ATTACK_SET_UP_THIS_TURN,
    TARGET_IS_UNRAVELLING,
    TARGET_UNRAVELLING,
    DESTROYER_CULT_RANGED_VS_CLOSEST,
    MURDER_MADNESS_CRITICAL_HIT,
    NEAR_PROPHET_OF_DESTRUCTION,
    PROPHET_OF_DESTRUCTION_TARGET,
    RANGED_VS_CLOSEST,
    RANGED_VS_CLOSEST_ON_OBJECTIVE,
    SET_UP_THIS_TURN,
    TARGET_IS_WORTHY_FOE,
    TARGETING_CLOSEST_ELIGIBLE,
    WITHIN_POWER_MATRIX,
    WORTHY_FOES_TARGET,
)

# Positions the calculator asks about, since it can't measure the table:
# {position: label}. A combat request lists each side's positions.
POSITIONS = {
    NEAR_ADMECH_BATTLELINE: 'Within 6" of a friendly ADEPTUS MECHANICUS BATTLELINE unit',
    IN_RANGE_OF_OBJECTIVE: "Within range of an objective marker",
    REMAINED_STATIONARY: "Remained Stationary this turn",
    ISOLATED_TARGET: 'Target has no other units from its army within 6"',
    BELOW_STARTING_STRENGTH: "Below Starting Strength",
    BELOW_HALF_STRENGTH: "Below Half-strength",
    SET_UP_THIS_TURN: "Set up on the battlefield this turn",
    WITHIN_POWER_MATRIX: "Wholly within the army's Power Matrix",
    TARGETING_CLOSEST_ELIGIBLE: "Targeting the closest eligible target",
    WORTHY_FOES_TARGET: "Targeting the unit selected for Worthy Foes",
    COLD_FERVOUR_TRIGGERED: "A DESTROYER CULT unit triggered Cold Fervour this turn",
    TARGET_UNRAVELLING: "Target is unravelling (within a NECRONS MONSTER's Distortion Fields)",
    NEAR_PROPHET_OF_DESTRUCTION: (
        'Within 9" of Nekrosor Ammentar after it destroyed a unit this phase'
    ),
    MARKED_PREY_TARGET: "Targeting the unit selected for Marked Prey",
    WITHIN_9_OF_TARGET: 'Target is within 9" of the attacking unit',
    CONTROLLING_OBJECTIVE: "Controlling an objective",
    VENGEANCE: (
        'A friendly ADEPTUS MECHANICUS VEHICLE model was destroyed within 12" '
        "(Vengeance for the Omnissiah)"
    ),
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
    REMAINED_STATIONARY: {"attacker": {STATIONARY_RANGED_CRITICAL_HIT}, "defender": set()},
    ISOLATED_TARGET: {"attacker": {TARGET_ISOLATED}, "defender": set()},
    BELOW_STARTING_STRENGTH: {"attacker": set(), "defender": {DEFENDER_BELOW_STARTING_STRENGTH}},
    BELOW_HALF_STRENGTH: {
        "attacker": set(),
        "defender": {DEFENDER_BELOW_STARTING_STRENGTH, DEFENDER_BELOW_HALF_STRENGTH},
    },
    SET_UP_THIS_TURN: {
        "attacker": {ATTACKER_SET_UP_THIS_TURN, RANGED_ATTACK_SET_UP_THIS_TURN},
        "defender": set(),
    },
    WITHIN_POWER_MATRIX: {"attacker": {ATTACKER_IN_POWER_MATRIX}, "defender": set()},
    TARGETING_CLOSEST_ELIGIBLE: {
        "attacker": {
            DESTROYER_CULT_RANGED_VS_CLOSEST,
            RANGED_VS_CLOSEST,
            RANGED_VS_CLOSEST_ON_OBJECTIVE,
            MURDER_MADNESS_CRITICAL_HIT,
        },
        "defender": set(),
    },
    WORTHY_FOES_TARGET: {"attacker": {TARGET_IS_WORTHY_FOE}, "defender": set()},
    COLD_FERVOUR_TRIGGERED: {"attacker": {COLD_FERVOUR_SPREAD}, "defender": set()},
    TARGET_UNRAVELLING: {"attacker": {TARGET_IS_UNRAVELLING}, "defender": set()},
    NEAR_PROPHET_OF_DESTRUCTION: {
        "attacker": {PROPHET_OF_DESTRUCTION_TARGET},
        "defender": set(),
    },
    MARKED_PREY_TARGET: {"attacker": {MARKED_PREY_CRITICAL_HIT}, "defender": set()},
    WITHIN_9_OF_TARGET: {"attacker": {TARGET_WITHIN_9}, "defender": set()},
    CONTROLLING_OBJECTIVE: {"attacker": set(), "defender": {DEFENDER_CONTROLLING_OBJECTIVE}},
    VENGEANCE: {"attacker": {VENGEANCE_ACTIVE}, "defender": set()},
}

# In a game, positions about being near friendly units, measured on the
# battlefield: {position: (keywords one of their models has, inches)}.
NEAR_FRIENDLY = {NEAR_ADMECH_BATTLELINE: (("ADEPTUS MECHANICUS", "BATTLELINE"), 6.0)}

# Positions asked about for every unit on a side, whatever its rules - board
# state as general as cover (e.g. stratagems like Scriptural Prognosis read
# whether the defender is on an objective; Remaining Stationary also counts
# as moving less than 3" for [HEAVY]; stratagems like The Spoor of Frailty
# read whether the target is below strength): {position: sides}.
ALWAYS_ASKED = {
    IN_RANGE_OF_OBJECTIVE: {"defender"},
    REMAINED_STATIONARY: {"attacker"},
    BELOW_STARTING_STRENGTH: {"defender"},
    BELOW_HALF_STRENGTH: {"defender"},
}
