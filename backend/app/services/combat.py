from __future__ import annotations

import random
import re
from collections import deque
from dataclasses import dataclass, field

from app.models import Unit

_DAMAGE_PATTERN = re.compile(r"^(?:(?P<flat>[0-9]+)|(?P<count>[0-9]*)D(?P<die>[36]))$")


def roll_damage(damage: str) -> int:
    match = _DAMAGE_PATTERN.match(damage)
    if match["flat"] is not None:
        return int(match["flat"])
    count = int(match["count"]) if match["count"] else 1
    die = int(match["die"])
    return sum(random.randint(1, die) for _ in range(count))


def wound_threshold(strength: int, toughness: int) -> int:
    if strength >= 2 * toughness:
        return 2
    if strength > toughness:
        return 3
    if strength == toughness:
        return 4
    if toughness >= 2 * strength:
        return 6
    return 5


@dataclass
class _Target:
    toughness: int
    save: int
    invulnerable: int | None
    feel_no_pain: int | None
    remaining_wounds: int


@dataclass
class CombatResult:
    total_attacks: int = field(default=0)
    total_hits: int = field(default=0)
    total_wounds: int = field(default=0)
    failed_saves: int = field(default=0)
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
) -> CombatResult:
    targets: deque[_Target] = deque(
        _Target(
            toughness=unit_model.model.toughness,
            save=unit_model.model.save,
            invulnerable=unit_model.model.invulnerable,
            feel_no_pain=unit_model.model.feel_no_pain,
            remaining_wounds=unit_model.model.wounds,
        )
        for unit_model in defender.unit_models
    )

    result = CombatResult()

    if visible and in_range:
        for unit_model in attacker.unit_models:
            for weapon in unit_model.weapons:
                if weapon.id not in selected_weapon_ids:
                    continue
                if (weapon.weapon_type == "melee") != in_engagement_range:
                    continue

                for _ in range(weapon.attacks):
                    if not targets:
                        break
                    result.total_attacks += 1
                    if random.randint(1, 6) < weapon.skill:
                        continue
                    result.total_hits += 1

                    target = targets[0]
                    threshold = wound_threshold(weapon.strength, target.toughness)
                    if random.randint(1, 6) < threshold:
                        continue
                    result.total_wounds += 1

                    save_needed = target.save - weapon.ap
                    if target.invulnerable is not None:
                        save_needed = min(save_needed, target.invulnerable)
                    if random.randint(1, 6) >= save_needed:
                        continue
                    result.failed_saves += 1

                    damage = roll_damage(weapon.damage)
                    fnp = target.feel_no_pain
                    applied = 0
                    for _ in range(damage):
                        if fnp is not None and random.randint(1, 6) >= fnp:
                            continue
                        applied += 1
                    result.total_damage += applied

                    while applied > 0 and targets:
                        target = targets[0]
                        absorbed = min(applied, target.remaining_wounds)
                        target.remaining_wounds -= absorbed
                        applied -= absorbed
                        if target.remaining_wounds <= 0:
                            targets.popleft()
                            result.models_destroyed += 1

    result.defending_models_remaining = len(targets)
    return result
