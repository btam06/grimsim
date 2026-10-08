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
    toughness: int
    save: int
    invulnerable: int | None
    feel_no_pain: int | None
    remaining_wounds: int


@dataclass
class CombatResult:
    # Raw die values (1-6) rolled at each step, in the order they were rolled,
    # rather than pass/fail counts - callers can see exactly what was rolled.
    attack_rolls: list[int] = field(default_factory=list)
    wound_rolls: list[int] = field(default_factory=list)
    save_rolls: list[int] = field(default_factory=list)
    total_damage: int = field(default=0)
    models_destroyed: int = field(default=0)
    defending_models_remaining: int = field(default=0)


def resolve_combat(
    attacker: Unit,
    defender: Unit,
    selected_weapon_ids: set[int],
    in_engagement_range: bool,
    visible: bool,
    in_range: bool,
    in_cover: bool,
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

            for weapon in unit_model.weapons:
                # Only weapons the caller chose to fire/swing with this attack count.
                if weapon.id not in selected_weapon_ids:
                    continue
                # Being in engagement range swaps which weapons are usable: melee
                # weapons fight instead of ranged weapons shooting.
                is_ranged = weapon.weapon_type != "melee"
                if is_ranged == in_engagement_range:
                    continue

                abilities = list(weapon.abilities) + wargear_abilities

                # Attacks characteristic: how many attack sequences this weapon makes,
                # rolled once per weapon (flat or dice notation, e.g. "2", "D3", "2D6").
                # This is a queue rather than a fixed range because an effect (e.g.
                # "add an extra hit") can append more attacks onto it mid-resolution.
                pending_attacks: deque[dict] = deque(
                    {"auto_hit": False} for _ in range(roll_dice(weapon.attacks))
                )

                while pending_attacks:
                    if not targets:
                        break  # defending unit has no models left to attack
                    attack = pending_attacks.popleft()

                    if attack["auto_hit"]:
                        # Granted outright by an effect (e.g. sustained hits) - it's
                        # already a hit, so no hit roll and no hit-step triggers.
                        pass
                    else:
                        # Pre-hit: lets a static trait (e.g. "always ignore cover")
                        # mark this attack before the hit roll's threshold is set.
                        _apply_triggered_effects(
                            abilities, {"step": "pre_hit"}, attack, pending_attacks
                        )
                        # A ranged attack against a target in cover needs a roll 1
                        # higher to hit, unless this attack ignores cover.
                        effective_skill = weapon.skill
                        if in_cover and is_ranged and not attack.get("ignore_cover"):
                            effective_skill += 1

                        # Hit roll: succeeds (hits) on a roll equal to or greater than skill.
                        hit_roll = random.randint(1, 6)
                        result.attack_rolls.append(hit_roll)
                        _apply_triggered_effects(
                            abilities, {"step": "hit", "roll": hit_roll}, attack, pending_attacks
                        )
                        if hit_roll < effective_skill:
                            continue

                    # Wound roll: threshold depends on this weapon's strength versus the
                    # toughness of whichever model is currently being targeted. An effect
                    # (e.g. auto-pass wound) can mark this attack to skip the roll entirely.
                    target = targets[0]
                    threshold = wound_threshold(weapon.strength, target.toughness)
                    if attack.get("auto_pass_wound"):
                        wound_passed = True
                    else:
                        wound_roll = random.randint(1, 6)
                        result.wound_rolls.append(wound_roll)
                        _apply_triggered_effects(
                            abilities, {"step": "wound", "roll": wound_roll}, attack, pending_attacks
                        )
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
                        target.remaining_wounds -= 1
                        if target.remaining_wounds <= 0:
                            targets.popleft()
                            result.models_destroyed += 1
                            break  # this model is destroyed - no spillover to the next

    result.defending_models_remaining = len(targets)
    return result
