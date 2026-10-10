from __future__ import annotations

import random
import re
from collections import deque
from dataclasses import dataclass, field

from app.combat_rules import CONDITIONS, EFFECTS
from app.models import Model, Unit, WargearAbility, WeaponAbility

_DICE_PATTERN = re.compile(r"^(?:(?P<flat>[0-9]+)|(?P<count>[0-9]*)D(?P<die>[36]))$")


def roll_dice(notation: str) -> int:
    # notation is either a flat number or dice notation (D3/D6/2D6/...); roll it to
    # a value. Used for both a weapon's damage and its number of attacks.
    match = _DICE_PATTERN.match(notation)
    if match["flat"] is not None:
        return int(match["flat"])
    count = int(match["count"]) if match["count"] else 1
    die = int(match["die"])
    return sum(random.randint(1, die) for _ in range(count))


def wound_threshold(strength: int, toughness: int) -> int:
    # The wound roll needed scales with how attacker strength compares to defender
    # toughness: double (or more) strength wounds easiest, double toughness hardest.
    if strength >= 2 * toughness:
        return 2
    if strength > toughness:
        return 3
    if strength == toughness:
        return 4
    if toughness >= 2 * strength:
        return 6
    return 5


def _effective_save(model: Model) -> int:
    # A model's invulnerable save isn't worsened by AP, so it protects the model
    # whenever it's better than (lower than) the modified armor save would be.
    if model.invulnerable is not None:
        return min(model.save, model.invulnerable)
    return model.save


def _target_priority(model: Model) -> tuple[int, int]:
    # Supports and leaders are targeted last, regardless of their save. Within that
    # grouping, the worst-saving models (highest save value) are targeted first.
    is_priority_target = not (model.is_support or model.is_leader)
    return (0 if is_priority_target else 1, -_effective_save(model))


def _apply_triggered_effects(
    abilities: list[WeaponAbility] | list[WargearAbility],
    context: dict,
    state: dict,
    pending: deque[dict],
) -> None:
    # Checked at every step (pre-hit/hit/wound/save): for each ability in play
    # - whether from the weapon itself or from wargear equipped on the same
    # model - if *any* of its conditions match the current step, apply *all*
    # of its effects. Unknown keywords (a condition/effect row with no matching
    # hardcoded implementation) are simply ignored.
    for ability in abilities:
        matched = any(
            CONDITIONS[condition.keyword](context)
            for condition in ability.conditions
            if condition.keyword in CONDITIONS
        )
        if not matched:
            continue
        for effect in ability.effects:
            handler = EFFECTS.get(effect.keyword)
            if handler is not None:
                handler(state, pending)


@dataclass
class _Target:
    toughness        : int
    save             : int
    invulnerable     : int | None
    feel_no_pain     : int | None
    remaining_wounds : int


@dataclass
class WeaponCombatResult:
    # The same breakdown as CombatResult below, scoped to a single weapon
    # profile (every weapon instance sharing one name, across every model in
    # the attacking unit that fired it) rather than the whole combat.
    name             : str
    attack_rolls     : list[int] = field(default_factory=list)
    attack_rerolls   : list[int] = field(default_factory=list)
    wound_rolls      : list[int] = field(default_factory=list)
    save_rolls       : list[int] = field(default_factory=list)
    total_damage     : int       = field(default=0)
    models_destroyed : int       = field(default=0)
    hazardous_rolls  : list[int] = field(default_factory=list)
    hazardous_wounds : int       = field(default=0)


@dataclass
class CombatResult:
    # Raw die values (1-6) rolled at each step, in the order they were rolled,
    # rather than pass/fail counts - callers can see exactly what was rolled.
    attack_rolls               : list[int] = field(default_factory=list)
    attack_rerolls             : list[int] = field(default_factory=list)
    wound_rolls                : list[int] = field(default_factory=list)
    save_rolls                 : list[int] = field(default_factory=list)
    total_damage               : int       = field(default=0)
    models_destroyed           : int       = field(default=0)
    defending_models_remaining : int       = field(default=0)
    # Self-inflicted hazard checks made by the attacking unit (one per
    # hazardous weapon fired), and the total wounds they dealt after FNP.
    hazardous_rolls: list[int] = field(default_factory=list)
    hazardous_wounds: int = field(default=0)
    # How many attacking models were destroyed outright by their own
    # hazardous wounds (checked once a model is done firing all its weapons).
    hazardous_models_destroyed: int = field(default=0)
    # The same totals above, broken down per weapon profile (grouped by
    # weapon name) instead of pooled across the whole attacking unit.
    weapon_results: list[WeaponCombatResult] = field(default_factory=list)


def resolve_combat(
    attacker: Unit,
    defender: Unit,
    selected_weapon_ids: set[int],
    in_engagement_range: bool,
    visible: bool,
    in_range: bool,
    in_cover: bool,
    half_range: bool,
    moved_less_than_3: bool,
) -> CombatResult:
    # The defending unit is a queue of individual models, each with its own wound pool.
    # Each attack targets whichever model is at the front of the queue; once that
    # model is destroyed it's popped, and the *next* attack targets the model now
    # at the front - a single attack's damage never spills onto a second model.
    # The queue is pre-sorted so supports/leaders die last, and otherwise worst
    # saves (including invulnerable) die before better ones.
    ordered_unit_models = sorted(
        defender.unit_models, key=lambda unit_model: _target_priority(unit_model.model)
    )
    # The full set of keywords across every model in the defending unit's
    # original composition - used by conditions like "target has INFANTRY"
    # (e.g. for Anti-Infantry/Anti-Vehicle), independent of casualties so far.
    defender_keywords = {
        keyword.name
        for unit_model in defender.unit_models
        for keyword in unit_model.model.keywords
    }

    # Some wargear/datasheet abilities apply to the whole attacking unit rather
    # than just the model carrying them (e.g. "Ignore Cover (Unit)", or a
    # datasheet ability granting the unit a reroll) - checked once, across
    # every model's wargear and datasheet abilities, regardless of which
    # weapon is firing.
    unit_wide_state: dict = {}
    all_unit_wide_abilities = [
        ability
        for unit_model in attacker.unit_models
        for gear in unit_model.wargear
        for ability in gear.abilities
    ] + [
        ability
        for unit_model in attacker.unit_models
        for ability in unit_model.model.abilities
    ]
    _apply_triggered_effects(
        all_unit_wide_abilities, {"step": "unit_wide"}, unit_wide_state, deque()
    )
    unit_ignores_cover = unit_wide_state.get("ignore_cover_unit", False)
    unit_rerolls_failed_hits = unit_wide_state.get("reroll_failed_hits", False)

    targets: deque[_Target] = deque(
        _Target(
            toughness=unit_model.model.toughness,
            save=unit_model.model.save,
            invulnerable=unit_model.model.invulnerable,
            feel_no_pain=unit_model.model.feel_no_pain,
            remaining_wounds=unit_model.model.wounds,
        )
        for unit_model in ordered_unit_models
    )

    result = CombatResult()
    # Accumulates the same breakdown as `result`, but bucketed per weapon name
    # - every weapon instance sharing a name (e.g. five models each carrying
    # their own "Boltgun") feeds into the same bucket. Built up alongside the
    # pooled totals below, then flattened onto result.weapon_results at the end.
    weapon_results_by_name: dict[str, WeaponCombatResult] = {}

    # A unit that can't see its target makes no attacks at all - this is checked
    # once for the whole attacking unit, since visibility is a property of the
    # engagement as a whole, not of any one model within it.
    if visible:
        for unit_model in attacker.unit_models:
            # Range, by contrast, is checked per attacking model: models within the
            # same unit can be spread out, so one model being out of range doesn't
            # stop the rest of the unit from attacking.
            if not in_range:
                continue

            # Abilities on wargear equipped by this model are in play for every
            # weapon it fires, same as the weapon's own abilities.
            wargear_abilities = [
                ability for gear in unit_model.wargear for ability in gear.abilities
            ]

            # Hazardous wounds taken by this model accumulate across every one
            # of its weapons, in case more than one is hazardous - checked
            # against its own wounds once it's done firing (see below).
            model_hazardous_damage = 0

            for weapon in unit_model.weapons:
                # Only weapons the caller chose to fire/swing with this attack count.
                if weapon.id not in selected_weapon_ids:
                    continue
                # Being in engagement range swaps which weapons are usable: melee
                # weapons fight instead of ranged weapons shooting.
                is_ranged = weapon.weapon_type != "melee"
                if is_ranged == in_engagement_range:
                    continue

                weapon_result = weapon_results_by_name.setdefault(
                    weapon.name, WeaponCombatResult(name=weapon.name)
                )

                abilities = list(weapon.abilities) + wargear_abilities

                # Attacks characteristic: how many attack sequences this weapon makes,
                # rolled once per weapon (flat or dice notation, e.g. "2", "D3", "2D6").
                # This is a queue rather than a fixed range because an effect (e.g.
                # "add an extra hit") can append more attacks onto it mid-resolution.
                pending_attacks: deque[dict] = deque(
                    {"auto_hit": False} for _ in range(roll_dice(weapon.attacks))
                )

                # Pre-weapon: checked once per weapon (not per individual attack),
                # for traits that apply to the whole shooting sequence rather than
                # any one attack - e.g. Rapid Fire adding attacks to the queue when
                # within half range, or Hazardous risking a self-inflicted wound.
                pre_weapon_state: dict = {}
                _apply_triggered_effects(
                    abilities,
                    {"step": "pre_weapon", "half_range": half_range},
                    pre_weapon_state,
                    pending_attacks,
                )
                if pre_weapon_state.get("hazardous"):
                    # Hazard roll: a 1-2 means the firing model takes damage based
                    # on its own keywords, reduced by its own feel no pain.
                    hazard_roll = random.randint(1, 6)
                    result.hazardous_rolls.append(hazard_roll)
                    weapon_result.hazardous_rolls.append(hazard_roll)
                    if hazard_roll <= 2:
                        shooter_keywords = {k.name for k in unit_model.model.keywords}
                        if "VEHICLE" in shooter_keywords:
                            self_wounds = 3
                        elif "INFANTRY" in shooter_keywords:
                            self_wounds = 1
                        else:
                            self_wounds = 0
                        shooter_fnp = unit_model.model.feel_no_pain
                        for _ in range(self_wounds):
                            if shooter_fnp is not None and random.randint(1, 6) >= shooter_fnp:
                                continue  # feel no pain negated this point of damage
                            result.hazardous_wounds += 1
                            weapon_result.hazardous_wounds += 1
                            model_hazardous_damage += 1

                while pending_attacks:
                    if not targets:
                        break  # defending unit has no models left to attack
                    attack = pending_attacks.popleft()

                    if attack["auto_hit"]:
                        # Granted outright by an effect (e.g. sustained hits) - it's
                        # already a hit, so no hit roll and no hit-step triggers.
                        pass
                    else:
                        # Pre-hit: lets a static trait (e.g. "always ignore cover",
                        # or Heavy when the unit moved less than 3") mark this
                        # attack before the hit roll's threshold is set.
                        _apply_triggered_effects(
                            abilities,
                            {"step": "pre_hit", "moved_less_than_3": moved_less_than_3},
                            attack,
                            pending_attacks,
                        )
                        # A ranged attack against a target in cover needs a roll 1
                        # higher to hit, unless this attack (or the whole unit)
                        # ignores cover.
                        effective_skill = weapon.skill
                        if (
                            in_cover
                            and is_ranged
                            and not unit_ignores_cover
                            and not attack.get("ignore_cover")
                        ):
                            effective_skill += 1
                        if attack.get("plus_one_to_hit"):
                            effective_skill -= 1
                        if is_ranged and attack.get("plus_one_skill_ranged"):
                            effective_skill -= 1
                        if not is_ranged and attack.get("plus_one_skill_melee"):
                            effective_skill -= 1

                        # Hit roll: succeeds (hits) on a roll equal to or greater than skill.
                        hit_roll = random.randint(1, 6)
                        result.attack_rolls.append(hit_roll)
                        weapon_result.attack_rolls.append(hit_roll)
                        _apply_triggered_effects(
                            abilities, {"step": "hit", "roll": hit_roll}, attack, pending_attacks
                        )
                        if hit_roll < effective_skill and (
                            attack.get("reroll_failed_hits") or unit_rerolls_failed_hits
                        ):
                            # Re-roll a failed hit once, replacing the original
                            # result - hit-step triggers (e.g. Sustained Hits) are
                            # re-checked against the new roll too.
                            hit_roll = random.randint(1, 6)
                            result.attack_rerolls.append(hit_roll)
                            weapon_result.attack_rerolls.append(hit_roll)
                            _apply_triggered_effects(
                                abilities, {"step": "hit", "roll": hit_roll}, attack, pending_attacks
                            )
                        if hit_roll < effective_skill:
                            continue

                    # Wound roll: threshold depends on this weapon's strength versus the
                    # toughness of whichever model is currently being targeted.
                    target = targets[0]
                    threshold = wound_threshold(weapon.strength, target.toughness)

                    if attack.get("auto_pass_wound"):
                        wound_passed = True
                    else:
                        wound_roll = random.randint(1, 6)
                        result.wound_rolls.append(wound_roll)
                        weapon_result.wound_rolls.append(wound_roll)
                        _apply_triggered_effects(
                            abilities,
                            {"step": "wound", "roll": wound_roll, "defender_keywords": defender_keywords},
                            attack,
                            pending_attacks,
                        )
                        if attack.get("critical_wound"):
                            # An Anti-X-style ability (e.g. Anti-Infantry 4+) matched
                            # this roll against the defending unit's keywords - it
                            # counts as a critical wound regardless of the actual roll,
                            # so re-run the wound-step trigger check with a synthetic
                            # natural-6 context to also fire any other critical-wound-
                            # dependent effects (e.g. Devastating Wounds), same as an
                            # actual natural 6 would.
                            _apply_triggered_effects(
                                abilities,
                                {"step": "wound", "roll": 6, "defender_keywords": defender_keywords},
                                attack,
                                pending_attacks,
                            )
                            wound_passed = True
                        else:
                            wound_passed = wound_roll >= threshold
                    if not wound_passed:
                        continue

                    # Save roll: armor save is worsened by the weapon's AP, but the
                    # defender may use their invulnerable save instead if it's better.
                    # An effect (e.g. devastating wounds) can mark this attack to skip
                    # the roll entirely - no save of any kind, armor or invulnerable.
                    if attack.get("no_save"):
                        save_passed = False
                    else:
                        save_needed = target.save - weapon.ap
                        if target.invulnerable is not None:
                            save_needed = min(save_needed, target.invulnerable)
                        save_roll = random.randint(1, 6)
                        result.save_rolls.append(save_roll)
                        weapon_result.save_rolls.append(save_roll)
                        _apply_triggered_effects(
                            abilities, {"step": "save", "roll": save_roll}, attack, pending_attacks
                        )
                        save_passed = save_roll >= save_needed
                    if save_passed:
                        continue  # save succeeded - no damage from this attack

                    # Damage roll: how many wounds this one failed save inflicts.
                    damage = roll_dice(weapon.damage)

                    # Apply damage a single point at a time, each rolling feel no pain
                    # separately, against the one model this attack is targeting. If
                    # that model dies partway through, this attack's remaining damage
                    # is wasted rather than carrying onto the next model - the next
                    # attack (if any) simply finds that next model at the front of
                    # the queue instead.
                    for _ in range(damage):
                        if (
                            target.feel_no_pain is not None
                            and random.randint(1, 6) >= target.feel_no_pain
                        ):
                            continue  # feel no pain negated this point of damage

                        result.total_damage += 1
                        weapon_result.total_damage += 1
                        target.remaining_wounds -= 1
                        if target.remaining_wounds <= 0:
                            targets.popleft()
                            result.models_destroyed += 1
                            weapon_result.models_destroyed += 1
                            break  # this model is destroyed - no spillover to the next

            # End of combat for this attacking model: if the hazardous wounds it
            # took while firing added up to (or past) its own wounds, it died.
            if model_hazardous_damage >= unit_model.model.wounds:
                result.hazardous_models_destroyed += 1

    result.defending_models_remaining = len(targets)
    result.weapon_results = list(weapon_results_by_name.values())
    return result
