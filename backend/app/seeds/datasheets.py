from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from app.seeds import data_files

# The shape of a datasheet, loaded from app/data/factions/<faction>/datasheets.json
# (see app/data/README.md) and seeded by app.seeds.factions.seed_datasheets.
# Abilities and keywords are referenced by name and must already be seeded
# (weapon/wargear/datasheet abilities, keywords, and this faction's faction
# abilities).


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
    # Equipped by default ("This model is equipped with: ...").
    default: bool = False


@dataclass(frozen=True)
class WargearSpec:
    name: str
    description: str | None = None
    abilities: tuple[str, ...] = ()  # WargearAbility names
    scope: str = "bearer"  # "bearer" or "bearers_unit" (see WARGEAR_SCOPES)


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
    feel_no_pain_mortal: int | None = None  # Feel No Pain vs mortal wounds only
    invulnerable_ranged_only: bool = False  # the invulnerable save is vs ranged only
    base_size: str | None = None  # a BaseSize name, e.g. "32mm" or "105 x 70mm"
    keywords: tuple[str, ...] = ()  # Keyword names
    faction_abilities: tuple[str, ...] = ()  # FactionAbility names in this faction
    abilities: tuple[str, ...] = ()  # DatasheetAbility names
    weapons: tuple[WeaponSpec, ...] = field(default=())
    wargear: tuple[WargearSpec, ...] = field(default=())


@dataclass(frozen=True)
class Datasheet:
    name: str  # the faction unit's name, e.g. "Skitarii Rangers"
    models: tuple[ModelSpec, ...]


def _weapon(data: dict) -> WeaponSpec:
    return WeaponSpec(**{**data, "abilities": tuple(data.get("abilities", ()))})


def _wargear(data: dict) -> WargearSpec:
    return WargearSpec(**{**data, "abilities": tuple(data.get("abilities", ()))})


def _model(data: dict) -> ModelSpec:
    return ModelSpec(
        **{
            **data,
            "keywords": tuple(data.get("keywords", ())),
            "faction_abilities": tuple(data.get("faction_abilities", ())),
            "abilities": tuple(data.get("abilities", ())),
            "weapons": tuple(_weapon(w) for w in data.get("weapons", ())),
            "wargear": tuple(_wargear(g) for g in data.get("wargear", ())),
        }
    )


def load(faction_slug: str) -> list[Datasheet]:
    # A faction's datasheets, from app/data/factions/<faction_slug>/datasheets.json
    # (the faction's folder name, e.g. "adeptus_mechanicus"); none if there's
    # no file.
    path = data_files.faction_data_dir(faction_slug) / "datasheets.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Datasheet(name=sheet["name"], models=tuple(_model(m) for m in sheet["models"]))
        for sheet in data["datasheets"]
    ]
