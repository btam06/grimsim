from __future__ import annotations

import re

# Weapons with several profiles (e.g. "Plasma caliver – standard" and
# "Plasma caliver – supercharge", or a melee weapon's "– strike" and
# "– sweep"): each profile is its own weapon, named "<weapon> – <profile>"
# (an en dash, em dash or hyphen between spaces). A model attacking with the
# weapon uses only one of its profiles each time.

_SEPARATOR = re.compile(r"\s+[-–—]\s+")


def profile_group(name: str) -> str | None:
    # The weapon a profile belongs to (the name before its profile's), or None
    # if it isn't one of several profiles.
    parts = _SEPARATOR.split(name, maxsplit=1)
    return parts[0] if len(parts) == 2 else None


def conflicting_profiles(weapons) -> str | None:
    # The weapon two or more different profiles of are among these (one
    # model's selected weapons), if any. (A model can carry the same profile
    # twice - e.g. two plasma weapons.)
    seen: dict[str, set[str]] = {}
    for weapon in weapons:
        group = profile_group(weapon.name)
        if group is None:
            continue
        seen.setdefault(group, set()).add(weapon.name)
        if len(seen[group]) > 1:
            return group
    return None


def unit_conflict(unit, weapon_ids) -> str | None:
    # Why the unit can't attack with these weapons (ids, as selected): two
    # profiles of one weapon on the same model. None if it can.
    for unit_model in unit.unit_models:
        group = conflicting_profiles(w for w in unit_model.weapons if w.id in weapon_ids)
        if group is not None:
            return f"choose only one profile of {group} to attack with"
    return None
