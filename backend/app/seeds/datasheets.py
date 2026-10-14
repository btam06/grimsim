from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# The shape of a hardcoded datasheet, as declared in
# app/seeds/factions/<faction>/units/<unit>.py and seeded by
# app.seeds.factions.seed_datasheets. Abilities and keywords are referenced by
# name and must already be seeded (weapon/wargear/datasheet abilities,
# keywords, and this faction's faction abilities).


@dataclass(frozen=True)
class WeaponSpec:
    name: str
    weapon_type: Literal["ranged", "melee"]
    attacks: str  # flat or dice notation, e.g. "2", "D3"
    skill: int  # BS/WS, e.g. 4 for 4+
    strength: int
    ap: int  # 0 or negative
    damage: str  # flat or dice notation
    range: int | None = None  # inches; None for melee
    abilities: tuple[str, ...] = ()  # WeaponAbility names


@dataclass(frozen=True)
class WargearSpec:
    name: str
    description: str | None = None
    abilities: tuple[str, ...] = ()  # WargearAbility names


@dataclass(frozen=True)
class ModelSpec:
    name: str
    movement: int
    toughness: int
    save: int
    wounds: int
    leadership: int
    oc: int
    invulnerable: int | None = None
    feel_no_pain: int | None = None
    is_support: bool = False
    is_leader: bool = False
    keywords: tuple[str, ...] = ()  # Keyword names
    faction_abilities: tuple[str, ...] = ()  # FactionAbility names in this faction
    abilities: tuple[str, ...] = ()  # DatasheetAbility names
    weapons: tuple[WeaponSpec, ...] = field(default=())
    wargear: tuple[WargearSpec, ...] = field(default=())
