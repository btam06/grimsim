from app.combat_rules.conditions import (
    SET_UP_THIS_TURN,
    attacker_led_by_character,
    critical_hit,
    defender_below_half_strength,
    defender_in_range_of_objective,
    half_range_attack,
)

# Necrons conditions - checks for its own rules (e.g. Power Matrix, Annihilation
# Protocol, Worthy Foes), shaped like the core ones in
# app/combat_rules/conditions.py, which combines them.

ATTACKER_IN_POWER_MATRIX = "attacker_in_power_matrix"
DESTROYER_CULT_RANGED_VS_CLOSEST = "destroyer_cult_ranged_vs_closest"
TARGET_IS_WORTHY_FOE = "target_is_worthy_foe"
ATTACKER_SET_UP_THIS_TURN = "attacker_set_up_this_turn"
COLD_FERVOUR_SPREAD = "cold_fervour_spread"
NON_MONSTER_VS_OBJECTIVE_TARGET = "non_monster_vs_objective_target"
HALF_RANGE_ATTACK_LED_BY_CHARACTER = "half_range_attack_led_by_character"
TARGET_NECRON_WARRIORS = "target_necron_warriors"
TARGET_IMMORTALS = "target_immortals"
ATTACKER_IS_CRYPTEK = "attacker_is_cryptek"
TARGET_IS_UNRAVELLING = "target_is_unravelling"
RANGED_ATTACK_SET_UP_THIS_TURN = "ranged_attack_set_up_this_turn"
TESLA_SPHERE_WEAPON = "tesla_sphere_weapon"
RANGED_ATTACK_LED_BY_CHARACTER = "ranged_attack_led_by_character"
CHARACTER_VS_BELOW_HALF_STRENGTH = "character_vs_below_half_strength"
RANGED_VS_CLOSEST = "ranged_vs_closest"
RANGED_VS_CLOSEST_ON_OBJECTIVE = "ranged_vs_closest_on_objective"
MURDER_MADNESS_CRITICAL_HIT = "murder_madness_critical_hit"
PROPHET_OF_DESTRUCTION_TARGET = "prophet_of_destruction_target"

# The calculator's Positioning (see app/combat_rules/positions.py).
WITHIN_POWER_MATRIX = "within_power_matrix"
TARGETING_CLOSEST_ELIGIBLE = "targeting_closest_eligible"
WORTHY_FOES_TARGET = "worthy_foes_target"
# SET_UP_THIS_TURN is a core position (see app/combat_rules/conditions.py).
COLD_FERVOUR_TRIGGERED = "cold_fervour_triggered"
TARGET_UNRAVELLING = "target_unravelling"
NEAR_PROPHET_OF_DESTRUCTION = "near_prophet_of_destruction"


def attacker_in_power_matrix(context: dict) -> bool:
    # True at every step while the attacking unit is wholly within its army's
    # Power Matrix (ticked under Positioning) - e.g. Power Matrix's re-rolls.
    return WITHIN_POWER_MATRIX in context.get("attacker_positions", set())


def destroyer_cult_ranged_vs_closest(context: dict) -> bool:
    # A ranged attack by a DESTROYER CULT model that targets the closest
    # eligible target (ticked under Positioning) - Annihilation Protocol.
    return (
        context.get("is_ranged", False)
        and "DESTROYER CULT" in context.get("attacker_model_keywords", set())
        and TARGETING_CLOSEST_ELIGIBLE in context.get("attacker_positions", set())
    )


def target_is_worthy_foe(context: dict) -> bool:
    # True at every step while the defending unit is the one selected for
    # Worthy Foes this battle round (ticked under Positioning).
    return WORTHY_FOES_TARGET in context.get("attacker_positions", set())


def attacker_set_up_this_turn(context: dict) -> bool:
    # True at every step when the attacking unit was set up on the battlefield
    # this turn (ticked under Positioning) - e.g. Arisen Tyrant.
    return SET_UP_THIS_TURN in context.get("attacker_positions", set())


def cold_fervour_spread(context: dict) -> bool:
    # Cold Fervour's second part: once a DESTROYER CULT unit has triggered it
    # this turn (ticked under Positioning), attacks by other NECRONS models -
    # not DESTROYER CULT, MONSTER or TITANIC ones - get +2 Strength.
    model_keywords = context.get("attacker_model_keywords", set())
    return (
        COLD_FERVOUR_TRIGGERED in context.get("attacker_positions", set())
        and "NECRONS" in model_keywords
        and not {"DESTROYER CULT", "MONSTER", "TITANIC"} & model_keywords
    )


def non_monster_vs_objective_target(context: dict) -> bool:
    # At the pre-hit check: an attack by a model that isn't a MONSTER, against
    # a unit within range of an objective marker - Relentless Onslaught.
    return (
        context.get("step") == "pre_hit"
        and "MONSTER" not in context.get("attacker_model_keywords", set())
        and defender_in_range_of_objective(context)
    )


def half_range_attack_led_by_character(context: dict) -> bool:
    # As half_range_attack, while a CHARACTER is leading the attacking unit -
    # Protocol of the Conquering Tyrant's full re-roll.
    return half_range_attack(context) and attacker_led_by_character(context)


def target_necron_warriors(context: dict) -> bool:
    # True at every step when the defending unit has NECRON WARRIORS models -
    # Microscarab Swarm's 5+ invulnerable save.
    return "NECRON WARRIORS" in context.get("defender_keywords", set())


def target_immortals(context: dict) -> bool:
    # As target_necron_warriors, for IMMORTALS (Microscarab Swarm's 4+).
    return "IMMORTALS" in context.get("defender_keywords", set())


def attacker_is_cryptek(context: dict) -> bool:
    # True at every step when the attacking unit has a CRYPTEK model - e.g.
    # Molecular Targeting also ignoring Wound roll modifiers.
    return "CRYPTEK" in context.get("attacker_keywords", set())


def target_is_unravelling(context: dict) -> bool:
    # True at every step while the defending unit is unravelling - within a
    # NECRONS MONSTER's Distortion Fields (ticked under Positioning).
    return TARGET_UNRAVELLING in context.get("attacker_positions", set())


def ranged_attack_set_up_this_turn(context: dict) -> bool:
    # At the pre-hit check: a ranged attack by a unit that was set up on the
    # battlefield (made an ingress move) this turn - Transdimensional Deployment.
    return (
        context.get("step") == "pre_hit"
        and context.get("is_ranged", False)
        and attacker_set_up_this_turn(context)
    )


def tesla_sphere_weapon(context: dict) -> bool:
    # True at every step for a weapon whose name includes "Tesla Sphere" -
    # Cosmic Storm.
    return "tesla sphere" in context.get("weapon_name", "").lower()


def ranged_attack_led_by_character(context: dict) -> bool:
    # At the pre-hit check: a ranged attack while a CHARACTER is leading the
    # attacking unit - e.g. the Lokhust Lord's Destroyer Cult ability.
    return (
        context.get("step") == "pre_hit"
        and context.get("is_ranged", False)
        and attacker_led_by_character(context)
    )


def character_vs_below_half_strength(context: dict) -> bool:
    # An attack by a CHARACTER model against a unit ticked as Below
    # Half-strength - e.g. Driven by Hatred ("each time this model makes an
    # attack"). Per attacking model, so never at the unit-wide check.
    return "CHARACTER" in context.get(
        "attacker_model_keywords", set()
    ) and defender_below_half_strength(context)


def ranged_vs_closest(context: dict) -> bool:
    # A ranged attack that targets the closest eligible target (ticked under
    # Positioning) - e.g. Hard-wired for Destruction.
    return context.get("is_ranged", False) and TARGETING_CLOSEST_ELIGIBLE in context.get(
        "attacker_positions", set()
    )


def ranged_vs_closest_on_objective(context: dict) -> bool:
    # As ranged_vs_closest, against a unit within range of an objective marker
    # (the calculator doesn't track who controls it).
    return ranged_vs_closest(context) and defender_in_range_of_objective(context)


def murder_madness_critical_hit(context: dict) -> bool:
    # Infectious Murder-madness: a critical hit by a model (not a MONSTER or
    # TITANIC one) that's DESTROYER CULT or targeting the closest eligible
    # target - [SUSTAINED HITS 1].
    model_keywords = context.get("attacker_model_keywords", set())
    return (
        critical_hit(context)
        and not {"MONSTER", "TITANIC"} & model_keywords
        and (
            "DESTROYER CULT" in model_keywords
            or TARGETING_CLOSEST_ELIGIBLE in context.get("attacker_positions", set())
        )
    )


def prophet_of_destruction_target(context: dict) -> bool:
    # True at every step for a DESTROYER CULT attacking unit ticked as within 9"
    # of Nekrosor Ammentar after it destroyed a unit this phase - Prophet of
    # Destruction's re-roll of Wound rolls of 1.
    return "DESTROYER CULT" in context.get(
        "attacker_keywords", set()
    ) and NEAR_PROPHET_OF_DESTRUCTION in context.get("attacker_positions", set())


# {keyword: check}
CONDITIONS = {
    ATTACKER_IN_POWER_MATRIX: attacker_in_power_matrix,
    DESTROYER_CULT_RANGED_VS_CLOSEST: destroyer_cult_ranged_vs_closest,
    TARGET_IS_WORTHY_FOE: target_is_worthy_foe,
    ATTACKER_SET_UP_THIS_TURN: attacker_set_up_this_turn,
    COLD_FERVOUR_SPREAD: cold_fervour_spread,
    NON_MONSTER_VS_OBJECTIVE_TARGET: non_monster_vs_objective_target,
    HALF_RANGE_ATTACK_LED_BY_CHARACTER: half_range_attack_led_by_character,
    TARGET_NECRON_WARRIORS: target_necron_warriors,
    TARGET_IMMORTALS: target_immortals,
    ATTACKER_IS_CRYPTEK: attacker_is_cryptek,
    TARGET_IS_UNRAVELLING: target_is_unravelling,
    RANGED_ATTACK_SET_UP_THIS_TURN: ranged_attack_set_up_this_turn,
    TESLA_SPHERE_WEAPON: tesla_sphere_weapon,
    RANGED_ATTACK_LED_BY_CHARACTER: ranged_attack_led_by_character,
    CHARACTER_VS_BELOW_HALF_STRENGTH: character_vs_below_half_strength,
    RANGED_VS_CLOSEST: ranged_vs_closest,
    RANGED_VS_CLOSEST_ON_OBJECTIVE: ranged_vs_closest_on_objective,
    MURDER_MADNESS_CRITICAL_HIT: murder_madness_critical_hit,
    PROPHET_OF_DESTRUCTION_TARGET: prophet_of_destruction_target,
}

# Seeded Condition rows: (keyword, name, description).
ENTRIES = [
    (
        ATTACKER_IN_POWER_MATRIX,
        "Attacker in Power Matrix",
        "The attacking unit is wholly within its army's Power Matrix.",
    ),
    (
        DESTROYER_CULT_RANGED_VS_CLOSEST,
        "Destroyer Cult Ranged Attack vs Closest Target",
        "A ranged attack by a DESTROYER CULT model that targets the closest eligible target.",
    ),
    (
        TARGET_IS_WORTHY_FOE,
        "Target is the Worthy Foe",
        "The defending unit is the enemy unit selected for Worthy Foes.",
    ),
    (
        ATTACKER_SET_UP_THIS_TURN,
        "Attacker Set Up This Turn",
        "The attacking unit was set up on the battlefield this turn.",
    ),
    (
        COLD_FERVOUR_SPREAD,
        "Cold Fervour Triggered",
        "Cold Fervour has triggered this turn, and the attacking model is NECRONS but not "
        "DESTROYER CULT, MONSTER or TITANIC.",
    ),
    (
        NON_MONSTER_VS_OBJECTIVE_TARGET,
        "Non-Monster Attack vs Target on Objective",
        "An attack by a model that isn't a MONSTER, against a unit within range of an "
        "objective marker.",
    ),
    (
        HALF_RANGE_ATTACK_LED_BY_CHARACTER,
        "Half Range Attack While Led by Character",
        "An attack against a target within half range, while a CHARACTER is leading the "
        "attacking unit.",
    ),
    (
        TARGET_NECRON_WARRIORS,
        "Target is Necron Warriors",
        "The defending unit has NECRON WARRIORS models. Applies at every step.",
    ),
    (
        TARGET_IMMORTALS,
        "Target is Immortals",
        "The defending unit has IMMORTALS models. Applies at every step.",
    ),
    (
        ATTACKER_IS_CRYPTEK,
        "Attacker is Cryptek",
        "The attacking unit has a CRYPTEK model. Applies at every step.",
    ),
    (
        TARGET_IS_UNRAVELLING,
        "Target is Unravelling",
        "The defending unit is unravelling (within a NECRONS MONSTER's Distortion Fields).",
    ),
    (
        RANGED_ATTACK_SET_UP_THIS_TURN,
        "Ranged Attack After Arriving This Turn",
        "A ranged attack by a unit that was set up on the battlefield this turn.",
    ),
    (
        TESLA_SPHERE_WEAPON,
        "Tesla Sphere Weapon",
        "The weapon's name includes \"Tesla Sphere\".",
    ),
    (
        RANGED_ATTACK_LED_BY_CHARACTER,
        "Ranged Attack While Led by Character",
        "A ranged attack while a CHARACTER is leading the attacking unit.",
    ),
    (
        CHARACTER_VS_BELOW_HALF_STRENGTH,
        "Character Attack vs Below Half-strength",
        "An attack by a CHARACTER model against a unit that is Below Half-strength.",
    ),
    (
        RANGED_VS_CLOSEST,
        "Ranged Attack vs Closest Target",
        "A ranged attack that targets the closest eligible target.",
    ),
    (
        RANGED_VS_CLOSEST_ON_OBJECTIVE,
        "Ranged Attack vs Closest Target on Objective",
        "A ranged attack that targets the closest eligible target, which is within range "
        "of an objective marker.",
    ),
    (
        MURDER_MADNESS_CRITICAL_HIT,
        "Infectious Murder-madness Critical Hit",
        "A critical hit by a DESTROYER CULT model, or one targeting the closest eligible "
        "target (not a MONSTER or TITANIC model).",
    ),
    (
        PROPHET_OF_DESTRUCTION_TARGET,
        "Prophet of Destruction Target",
        "A DESTROYER CULT attacking unit within 9\" of Nekrosor Ammentar after it destroyed "
        "a unit this phase.",
    ),
]
