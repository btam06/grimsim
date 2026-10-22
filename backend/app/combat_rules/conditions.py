from __future__ import annotations

from collections.abc import Mapping

# Each condition is a hardcoded keyword + a function that inspects the current
# combat-resolution step and reports whether that condition is met. The keyword
# is what gets stored on a Condition row (app/models/condition.py) and seeded
# (app/seeds/conditions.py) so it can be attached to a WeaponAbility; the engine
# (app/services/combat.py) looks the function back up by that same keyword.
#
# To add another condition: write a `context -> bool` function below, register
# its keyword in CONDITIONS, then add a matching row in app/seeds/conditions.py.

CRITICAL_HIT = "critical_hit"
CRITICAL_WOUND = "critical_wound"
ALWAYS = "always"
ANTI_INFANTRY_2 = "anti_infantry_2"
ANTI_INFANTRY_3 = "anti_infantry_3"
ANTI_INFANTRY_4 = "anti_infantry_4"
ANTI_VEHICLE_2 = "anti_vehicle_2"
ANTI_VEHICLE_3 = "anti_vehicle_3"
ANTI_VEHICLE_4 = "anti_vehicle_4"
ANTI_MONSTER_4 = "anti_monster_4"
ANTI_FLY_2 = "anti_fly_2"
RANGED_CRITICAL_HIT = "ranged_critical_hit"
STATIONARY_RANGED_CRITICAL_HIT = "stationary_ranged_critical_hit"
WITHIN_HALF_RANGE = "within_half_range"
MOVED_LESS_THAN_3 = "moved_less_than_3"
TARGET_MONSTER_OR_VEHICLE = "target_monster_or_vehicle"
RANGED_MOVED_LESS_THAN_3 = "ranged_moved_less_than_3"
ATTACKER_IS_BATTLELINE = "attacker_is_battleline"
TARGET_NOT_MONSTER_OR_VEHICLE = "target_not_monster_or_vehicle"
CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE = "critical_hit_not_monster_or_vehicle"
RILED_UP_RANGED_CRITICAL_HIT = "riled_up_ranged_critical_hit"
PRE_WEAPON_NOT_MONSTER_OR_VEHICLE = "pre_weapon_not_monster_or_vehicle"
TARGET_HAS_CHARACTER = "target_has_character"
TARGET_LED_BY_CHARACTER = "target_led_by_character"
TARGET_INFANTRY = "target_infantry"
RANGED_ATTACK = "ranged_attack"
MELEE_ATTACK = "melee_attack"
HALF_RANGE_ATTACK = "half_range_attack"
ATTACKER_LED_BY_CHARACTER = "attacker_led_by_character"
TARGET_MODEL_CHARACTER = "target_model_character"
STRENGTH_EXCEEDS_TOUGHNESS = "strength_exceeds_toughness"
ANTI_INFANTRY_5 = "anti_infantry_5"
DEFENDER_BELOW_STARTING_STRENGTH = "defender_below_starting_strength"
DEFENDER_BELOW_HALF_STRENGTH = "defender_below_half_strength"
DEFENDER_BATTLE_SHOCKED = "defender_battle_shocked"
ATTACKER_DAMAGED = "attacker_damaged"
BEYOND_HALF_RANGE_ATTACK = "beyond_half_range_attack"
TARGET_ISOLATED = "target_isolated"
TARGET_TITANIC = "target_titanic"
RANGED_VS_OBJECTIVE_TARGET = "ranged_vs_objective_target"

# Positions a unit can be in that the calculator can't work out for itself,
# so the user says (see app/combat_rules/positions.py); conditions read them
# from the context's attacker_positions/defender_positions.
IN_RANGE_OF_OBJECTIVE = "in_range_of_objective"
REMAINED_STATIONARY = "remained_stationary"
DEFENDER_IN_RANGE_OF_OBJECTIVE = "defender_in_range_of_objective"
BELOW_STARTING_STRENGTH = "below_starting_strength"
BELOW_HALF_STRENGTH = "below_half_strength"
# "There are no other units from your opponent's army within 6\" of the target".
ISOLATED_TARGET = "isolated_target"

PRE_WEAPON = "pre_weapon"
CHARGED = "charged"

# Name of the Orks Waaagh! rule option that riles a unit up (see
# app/seeds/factions/orks/abilities.py), for "if this unit is riled up".
RILED_UP = "Riled Up"


def critical_hit(context: dict) -> bool:
    # True when the roll just made was a hit roll, and it came up a natural 6
    # (or 5+, for an attack that scores Critical Hits on a 5+ - see
    # critical_hit_5 in effects.py).
    return context.get("step") == "hit" and context.get("roll", 0) >= context.get(
        "critical_hit_on", 6
    )


def critical_wound(context: dict) -> bool:
    # True when the roll just made was a wound roll, and it came up a natural 6.
    return context.get("step") == "wound" and context.get("roll") == 6


def always(context: dict) -> bool:
    # Unconditional - an ability using this "condition" simply always applies
    # its effects, regardless of step or roll (e.g. a static weapon/wargear trait).
    return True


def anti_infantry_2(context: dict) -> bool:
    # True at the wound step if the wound roll was a 2+ against a defending
    # unit that contains an INFANTRY model (e.g. for "Anti-Infantry 2+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 2
        and "INFANTRY" in context.get("defender_keywords", set())
    )


def anti_infantry_3(context: dict) -> bool:
    # True at the wound step if the wound roll was a 3+ against a defending
    # unit that contains an INFANTRY model (e.g. for "Anti-Infantry 3+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 3
        and "INFANTRY" in context.get("defender_keywords", set())
    )


def anti_infantry_4(context: dict) -> bool:
    # True at the wound step if the wound roll was a 4+ against a defending
    # unit that contains an INFANTRY model (e.g. for "Anti-Infantry 4+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 4
        and "INFANTRY" in context.get("defender_keywords", set())
    )


def anti_infantry_5(context: dict) -> bool:
    # As anti_infantry_4, for a wound roll of 5+ (e.g. "Anti-Infantry 5+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 5
        and "INFANTRY" in context.get("defender_keywords", set())
    )


def anti_vehicle_2(context: dict) -> bool:
    # True at the wound step if the wound roll was a 2+ against a defending
    # unit that contains a VEHICLE model (e.g. for "Anti-Vehicle 2+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 2
        and "VEHICLE" in context.get("defender_keywords", set())
    )


def anti_vehicle_3(context: dict) -> bool:
    # True at the wound step if the wound roll was a 3+ against a defending
    # unit that contains a VEHICLE model (e.g. for "Anti-Vehicle 3+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 3
        and "VEHICLE" in context.get("defender_keywords", set())
    )


def anti_vehicle_4(context: dict) -> bool:
    # True at the wound step if the wound roll was a 4+ against a defending
    # unit that contains a VEHICLE model (e.g. for "Anti-Vehicle 4+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 4
        and "VEHICLE" in context.get("defender_keywords", set())
    )


def anti_monster_4(context: dict) -> bool:
    # True at the wound step if the wound roll was a 4+ against a defending
    # unit that contains a MONSTER model (e.g. for "Anti-Monster 4+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 4
        and "MONSTER" in context.get("defender_keywords", set())
    )


def within_half_range(context: dict) -> bool:
    # True at the once-per-weapon pre-weapon check if the shooting model is
    # within half the weapon's range (e.g. for a Rapid Fire weapon ability).
    return context.get("step") == "pre_weapon" and context.get("half_range", False)


def moved_less_than_3(context: dict) -> bool:
    # True at the pre-hit check if the attacking unit moved less than 3"
    # this turn (e.g. for a Heavy weapon ability).
    return context.get("step") == "pre_hit" and context.get("moved_less_than_3", False)


def target_monster_or_vehicle(context: dict) -> bool:
    # True at every step (like `always`) when the defending unit contains a
    # MONSTER or VEHICLE model - e.g. for a +1 to hit against big targets.
    defender_keywords = context.get("defender_keywords", set())
    return "MONSTER" in defender_keywords or "VEHICLE" in defender_keywords


def ranged_moved_less_than_3(context: dict) -> bool:
    # Like moved_less_than_3, but only for a ranged weapon - e.g. for granting
    # Heavy to a unit's ranged weapons without affecting its melee weapons.
    return moved_less_than_3(context) and context.get("is_ranged", False)




def attacker_is_battleline(context: dict) -> bool:
    # True at every step (like `always`) when the attacking unit contains a
    # BATTLELINE model (e.g. Conqueror Imperative's improved AP).
    return "BATTLELINE" in context.get("attacker_keywords", set())








def target_not_monster_or_vehicle(context: dict) -> bool:
    # The opposite of target_monster_or_vehicle, at every step - e.g. for a
    # HUNTER: MONSTER/VEHICLE profile that can't attack anything else.
    return not target_monster_or_vehicle(context)


def anti_fly_2(context: dict) -> bool:
    # True at the wound step if the wound roll was a 2+ against a defending
    # unit that contains a FLY model (e.g. for "Anti-Fly 2+").
    return (
        context.get("step") == "wound"
        and context.get("roll", 0) >= 2
        and "FLY" in context.get("defender_keywords", set())
    )


def ranged_critical_hit(context: dict) -> bool:
    # A critical hit with a ranged weapon (e.g. "ranged weapons have
    # [SUSTAINED HITS 1]").
    return critical_hit(context) and context.get("is_ranged", False)


def stationary_ranged_critical_hit(context: dict) -> bool:
    # As ranged_critical_hit, while the attacking unit Remained Stationary
    # (ticked under the calculator's Positioning) - e.g. Punishing Salvoes.
    return ranged_critical_hit(context) and REMAINED_STATIONARY in context.get(
        "attacker_positions", set()
    )


def critical_hit_not_monster_or_vehicle(context: dict) -> bool:
    # A critical hit against a defending unit with no MONSTER or VEHICLE model
    # (e.g. for "LETHAL HITS: non-MONSTER/VEHICLE").
    return critical_hit(context) and target_not_monster_or_vehicle(context)


def riled_up_ranged_critical_hit(context: dict) -> bool:
    # A critical hit with a ranged weapon while the attacking unit is riled up
    # (e.g. Even More Dakka's [SUSTAINED HITS 1]).
    return (
        critical_hit(context)
        and context.get("is_ranged", False)
        and RILED_UP in context.get("attacker_options", set())
    )


def pre_weapon_not_monster_or_vehicle(context: dict) -> bool:
    # Checked once per weapon (not per attack): the defending unit has no
    # MONSTER or VEHICLE model - e.g. for Blitz Dem Gitz!'s extra attacks.
    return context.get("step") == "pre_weapon" and target_not_monster_or_vehicle(context)


def defender_in_range_of_objective(context: dict) -> bool:
    # True at every step while the defending unit is within range of an
    # objective marker (ticked under the calculator's Positioning) - e.g.
    # Scriptural Prognosis.
    return IN_RANGE_OF_OBJECTIVE in context.get("defender_positions", set())


def charged(context: dict) -> bool:
    # True at every step when the attacking unit made a Charge move this turn
    # (the calculator's "charged this turn" modifier) - e.g. [LANCE].
    return bool(context.get("charged"))


def pre_weapon(context: dict) -> bool:
    # Checked once per weapon (not per attack) - for effects that add attacks
    # to the weapon (e.g. "+2 Attacks"), which would otherwise be added again
    # at every step of every attack.
    return context.get("step") == "pre_weapon"






def target_has_character(context: dict) -> bool:
    # True at every step when the defending unit contains a CHARACTER model -
    # e.g. "while a CHARACTER model is leading this unit" on a defensive rule.
    return "CHARACTER" in context.get("defender_keywords", set())


def target_led_by_character(context: dict) -> bool:
    # True at every step when the defending unit is a CHARACTER leading a unit:
    # it has at least one CHARACTER model and at least one other model. (A lone
    # CHARACTER isn't leading anything.)
    per_model = context.get("defender_model_keywords", [])
    return any("CHARACTER" in keywords for keywords in per_model) and any(
        "CHARACTER" not in keywords for keywords in per_model
    )



def attacker_led_by_character(context: dict) -> bool:
    # As target_led_by_character, for the attacking unit - e.g. "while a
    # CHARACTER model is leading this unit, add 1 to the Hit roll".
    per_model = context.get("attacker_unit_model_keywords", [])
    return any("CHARACTER" in keywords for keywords in per_model) and any(
        "CHARACTER" not in keywords for keywords in per_model
    )


def target_model_character(context: dict) -> bool:
    # A defending CHARACTER model (checked per model) - e.g. an enhancement's
    # Feel No Pain for its bearer alone, rather than the unit it's leading.
    return "CHARACTER" in context.get("target_model_keywords", set())


def target_infantry(context: dict) -> bool:
    # True at every step when the defending unit contains an INFANTRY model -
    # e.g. "each time this model makes an attack ... that targets an INFANTRY
    # unit, add 1 to the Hit roll".
    return "INFANTRY" in context.get("defender_keywords", set())


def ranged_attack(context: dict) -> bool:
    # True at the pre-hit check of a ranged attack - e.g. Stealth's -1 to hit
    # for ranged attacks targeting the unit.
    return context.get("step") == "pre_hit" and context.get("is_ranged", False)


def melee_attack(context: dict) -> bool:
    # As ranged_attack, for a melee attack - e.g. "each time a melee attack
    # targets this unit, subtract 1 from the Hit roll".
    return context.get("step") == "pre_hit" and not context.get("is_ranged", True)


def half_range_attack(context: dict) -> bool:
    # True at the pre-hit check of an attack whose target is within half range
    # - e.g. "each time a model makes an attack that targets a unit within half
    # range, re-roll a Hit roll of 1". (within_half_range is the once-per-weapon
    # check, for abilities that add attacks.)
    return context.get("step") == "pre_hit" and context.get("half_range", False)


def strength_exceeds_toughness(context: dict) -> bool:
    # True at the wound step when the attack's Strength is greater than the
    # Toughness of the model it's against - e.g. Unyielding Forms' -1 to wound.
    return (
        context.get("step") == "wound"
        and context.get("strength", 0) > context.get("toughness", 0)
    )


def defender_below_starting_strength(context: dict) -> bool:
    # True at every step while the defending unit is below its Starting
    # Strength (ticked under the calculator's Positioning) - Below
    # Half-strength counts too.
    positions = context.get("defender_positions", set())
    return BELOW_STARTING_STRENGTH in positions or BELOW_HALF_STRENGTH in positions


def defender_below_half_strength(context: dict) -> bool:
    # As defender_below_starting_strength, for Below Half-strength.
    return BELOW_HALF_STRENGTH in context.get("defender_positions", set())


def defender_battle_shocked(context: dict) -> bool:
    # True at every step while the defending unit is Battle-shocked (the
    # calculator's "defender is Battle-shocked" modifier) - e.g. the Chaos
    # Knights' Doom.
    return bool(context.get("defender_battle_shocked"))


def attacker_damaged(context: dict) -> bool:
    # True at the pre-hit check while the attacking model is on its Damaged
    # profile (the calculator's "attacking model is Damaged" modifier) - e.g.
    # "Damaged: 1-5 wounds remaining ... subtract 1 from the Hit roll".
    return context.get("step") == "pre_hit" and bool(context.get("attacker_damaged"))


def beyond_half_range_attack(context: dict) -> bool:
    # The opposite of half_range_attack: an attack whose target isn't within
    # half range, at its pre-hit check - e.g. [CONVERSION] ("not within 12\""
    # on a 24\" weapon).
    return context.get("step") == "pre_hit" and not context.get("half_range", False)


def target_isolated(context: dict) -> bool:
    # True at every step while no other units from the defender's army are
    # within 6\" of it (ticked under Positioning) - e.g. the War Dog Stalker.
    return ISOLATED_TARGET in context.get("attacker_positions", set())


def target_titanic(context: dict) -> bool:
    # True at every step when the defending unit has a TITANIC model - e.g.
    # Titanic Duel's full re-rolls.
    return "TITANIC" in context.get("defender_keywords", set())


def ranged_vs_objective_target(context: dict) -> bool:
    # A ranged attack against a unit within range of an objective marker
    # (ticked under Positioning) - e.g. the War Dog Brigand's [IGNORES COVER].
    return context.get("is_ranged", False) and defender_in_range_of_objective(context)


CORE_CONDITIONS = {
    CRITICAL_HIT: critical_hit,
    CRITICAL_WOUND: critical_wound,
    ALWAYS: always,
    ANTI_INFANTRY_2: anti_infantry_2,
    ANTI_INFANTRY_3: anti_infantry_3,
    ANTI_INFANTRY_4: anti_infantry_4,
    ANTI_VEHICLE_2: anti_vehicle_2,
    ANTI_VEHICLE_3: anti_vehicle_3,
    ANTI_VEHICLE_4: anti_vehicle_4,
    ANTI_MONSTER_4: anti_monster_4,
    WITHIN_HALF_RANGE: within_half_range,
    MOVED_LESS_THAN_3: moved_less_than_3,
    TARGET_MONSTER_OR_VEHICLE: target_monster_or_vehicle,
    RANGED_MOVED_LESS_THAN_3: ranged_moved_less_than_3,
    ATTACKER_IS_BATTLELINE: attacker_is_battleline,
    TARGET_NOT_MONSTER_OR_VEHICLE: target_not_monster_or_vehicle,
    CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE: critical_hit_not_monster_or_vehicle,
    RILED_UP_RANGED_CRITICAL_HIT: riled_up_ranged_critical_hit,
    PRE_WEAPON_NOT_MONSTER_OR_VEHICLE: pre_weapon_not_monster_or_vehicle,
    TARGET_HAS_CHARACTER: target_has_character,
    TARGET_LED_BY_CHARACTER: target_led_by_character,
    TARGET_INFANTRY: target_infantry,
    RANGED_ATTACK: ranged_attack,
    PRE_WEAPON: pre_weapon,
    DEFENDER_IN_RANGE_OF_OBJECTIVE: defender_in_range_of_objective,
    CHARGED: charged,
    ANTI_FLY_2: anti_fly_2,
    RANGED_CRITICAL_HIT: ranged_critical_hit,
    STATIONARY_RANGED_CRITICAL_HIT: stationary_ranged_critical_hit,
    MELEE_ATTACK: melee_attack,
    HALF_RANGE_ATTACK: half_range_attack,
    ATTACKER_LED_BY_CHARACTER: attacker_led_by_character,
    TARGET_MODEL_CHARACTER: target_model_character,
    STRENGTH_EXCEEDS_TOUGHNESS: strength_exceeds_toughness,
    ANTI_INFANTRY_5: anti_infantry_5,
    DEFENDER_BELOW_STARTING_STRENGTH: defender_below_starting_strength,
    DEFENDER_BELOW_HALF_STRENGTH: defender_below_half_strength,
    DEFENDER_BATTLE_SHOCKED: defender_battle_shocked,
    ATTACKER_DAMAGED: attacker_damaged,
    BEYOND_HALF_RANGE_ATTACK: beyond_half_range_attack,
    TARGET_ISOLATED: target_isolated,
    TARGET_TITANIC: target_titanic,
    RANGED_VS_OBJECTIVE_TARGET: ranged_vs_objective_target,
}


class _Conditions(Mapping):
    # CORE_CONDITIONS plus each faction's own (its conditions.py CONDITIONS,
    # where it has one), looked up like a dict. Built on first use rather than
    # at import, since faction files import this one.
    _combined: dict | None = None

    def _all(self) -> dict:
        if self._combined is None:
            from app.seeds.factions import FACTIONS

            combined = dict(CORE_CONDITIONS)
            for faction in FACTIONS:
                for keyword, check in getattr(
                    getattr(faction, "conditions", None), "CONDITIONS", {}
                ).items():
                    if keyword in combined:
                        raise ValueError(f"condition {keyword!r} is defined more than once")
                    combined[keyword] = check
            self._combined = combined
        return self._combined

    def __getitem__(self, keyword: str):
        return self._all()[keyword]

    def __iter__(self):
        return iter(self._all())

    def __len__(self) -> int:
        return len(self._all())


# Every condition, core and faction: {keyword: check}.
CONDITIONS = _Conditions()
