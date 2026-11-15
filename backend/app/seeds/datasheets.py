from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from app.models.model import TransportCapacity
from app.schemas import DICE_PATTERN
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
    # A TRANSPORT's capacity (see app/models/model.py TransportCapacity).
    transport: TransportCapacity | None = None


@dataclass(frozen=True)
class CompositionSpec:
    # How many of one of the datasheet's models a unit has ("UNIT
    # COMPOSITION"), and what each starts with ("Every model is equipped
    # with: ..."): weapon/wargear names (a weapon's profiles are one weapon:
    # "Plasma caliver" is both "Plasma caliver – standard" and "–
    # supercharge"; repeat a name for several). None: its default weapons.
    model: str
    min: int = 1
    max: int = 1
    equipped: tuple[str, ...] | None = None


@dataclass(frozen=True)
class OptionSpec:
    # A "WARGEAR OPTIONS" line: a `model` can have its `replace` items (none:
    # it's an addition) replaced with one of the `with` choices (each one
    # item or several). At most `max` models in the unit can take it - for
    # every `per` models in the unit, if given ("for every 5 models...");
    # None: any model can. A model taking it must still have the `requires`
    # items once it's equipped (e.g. "* That model's galvanic rifle cannot
    # be replaced"). Each option is taken at most once per model.
    model: str
    with_: tuple[tuple[str, ...], ...]
    replace: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    max: int | None = None
    per: int | None = None


@dataclass(frozen=True)
class Datasheet:
    name: str  # the faction unit's name, e.g. "Skitarii Rangers"
    models: tuple[ModelSpec, ...]
    composition: tuple[CompositionSpec, ...] = ()
    wargear_options: tuple[OptionSpec, ...] = ()
    # The datasheets a leader or support datasheet can be attached to ("This
    # model can be attached to the following units: ..."), by name.
    leads: tuple[str, ...] = ()


def _weapon(data: dict) -> WeaponSpec:
    # (Its attacks and damage must be a number or dice notation - D3, 2D6,
    # D6+1... - as the API insists too; and only a [TORRENT] weapon, which
    # never rolls to hit, has no skill: 0.)
    for field_name in ("attacks", "damage"):
        if not re.match(DICE_PATTERN, str(data.get(field_name, ""))):
            raise ValueError(
                f"{data.get('name')}: {field_name} {data.get(field_name)!r} isn't a number or "
                "dice notation (e.g. 3, D6, 2D3, D6+1)"
            )
    torrent = "Torrent" in data.get("abilities", ())
    if torrent != (not data.get("skill")):
        raise ValueError(
            f"{data.get('name')}: a [TORRENT] weapon has skill 0, and only a [TORRENT] weapon does"
        )
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
            "transport": _transport(data["transport"]) if data.get("transport") else None,
        }
    )


def _transport(data: dict) -> TransportCapacity:
    return TransportCapacity(
        capacity=data["capacity"],
        keywords=tuple(data.get("keywords", ())),
        excluded_keywords=tuple(data.get("excluded_keywords", ())),
        space=dict(data.get("space", {})),
    )


def _names(value) -> tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value)


def _composition(data: dict) -> CompositionSpec:
    equipped = data.get("equipped")
    return CompositionSpec(
        model=data["model"], min=data.get("min", 1), max=data.get("max", data.get("min", 1)),
        equipped=None if equipped is None else _names(equipped),
    )


def _option(data: dict) -> OptionSpec:
    return OptionSpec(
        model=data["model"],
        with_=tuple(_names(choice) for choice in data["with"]),
        replace=_names(data.get("replace", ())),
        requires=_names(data.get("requires", ())),
        max=data.get("max"),
        per=data.get("per"),
    )


def _datasheet(sheet: dict) -> Datasheet:
    found = Datasheet(
        name=sheet["name"],
        models=tuple(_model(m) for m in sheet["models"]),
        composition=tuple(_composition(c) for c in sheet.get("composition", ())),
        wargear_options=tuple(_option(o) for o in sheet.get("wargear_options", ())),
        leads=tuple(sheet.get("leads", ())),
    )
    names = {m.name for m in found.models}
    for part in (*found.composition, *found.wargear_options):
        if part.model not in names:
            raise ValueError(f"{found.name}: {part.model!r} isn't one of its models")
    for part in found.composition:
        if not 0 <= part.min <= part.max:
            raise ValueError(f"{found.name}: {part.model} min/max {part.min}/{part.max}")
    # Every item named must be one of that model's weapons or wargear.
    from app.services.list_building.loadouts import key

    items = {
        m.name: {key(w.name) for w in m.weapons} | {key(g.name) for g in m.wargear}
        for m in found.models
    }
    named = [(c.model, c.equipped or ()) for c in found.composition] + [
        (o.model, (*o.replace, *o.requires, *(n for c in o.with_ for n in c)))
        for o in found.wargear_options
    ]
    for model, names in named:
        for name in names:
            if key(name) not in items[model]:
                raise ValueError(f"{found.name}: {model} has no weapon or wargear {name!r}")
    return found


def load(faction_slug: str) -> list[Datasheet]:
    # A faction's datasheets, from app/data/factions/<faction_slug>/datasheets.json
    # (the faction's folder name, e.g. "adeptus_mechanicus"); none if there's
    # no file.
    path = data_files.faction_data_dir(faction_slug) / "datasheets.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [_datasheet(sheet) for sheet in data["datasheets"]]
