from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DAMAGE_PATTERN = r"^([0-9]+|[0-9]*D[36])$"


class FactionIn(BaseModel):
    name: str


class FactionOut(FactionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ModelIn(BaseModel):
    name: str
    faction_id: int
    save: int
    toughness: int
    oc: int
    movement: int
    wounds: int
    invulnerable: int | None = None
    feel_no_pain: int | None = None
    ability_ids: list[int] = []
    wargear_ids: list[int] = []


class ModelOut(BaseModel):
    id: int
    name: str
    faction_id: int
    save: int
    toughness: int
    oc: int
    movement: int
    wounds: int
    invulnerable: int | None
    feel_no_pain: int | None
    ability_ids: list[int]
    wargear_ids: list[int]


class WeaponIn(BaseModel):
    name: str
    model_id: int
    damage: str = Field(pattern=DAMAGE_PATTERN)
    range: int
    strength: int
    ap: int
    attacks: int
    ability_ids: list[int] = []


class WeaponOut(BaseModel):
    id: int
    name: str
    model_id: int
    damage: str
    range: int
    strength: int
    ap: int
    attacks: int
    ability_ids: list[int]


class WargearIn(BaseModel):
    name: str
    model_id: int
    description: str | None = None


class WargearOut(BaseModel):
    id: int
    name: str
    model_id: int
    description: str | None


class UnitModelIn(BaseModel):
    model_id: int
    weapon_ids: list[int] = []
    wargear_ids: list[int] = []


class UnitModelOut(BaseModel):
    id: int
    model_id: int
    weapon_ids: list[int]
    wargear_ids: list[int]


class UnitIn(BaseModel):
    name: str
    points: int
    list_id: int | None = None
    unit_models: list[UnitModelIn] = []


class UnitOut(BaseModel):
    id: int
    name: str
    points: int
    list_id: int | None
    unit_models: list[UnitModelOut]


class WeaponAbilityIn(BaseModel):
    name: str
    description: str | None = None


class WeaponAbilityOut(WeaponAbilityIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class DatasheetAbilityIn(BaseModel):
    name: str
    description: str | None = None


class DatasheetAbilityOut(DatasheetAbilityIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class DispositionIn(BaseModel):
    name: str
    description: str | None = None


class DispositionOut(DispositionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class DetachmentIn(BaseModel):
    name: str
    faction_id: int
    disposition_ids: list[int] = []


class DetachmentOut(BaseModel):
    id: int
    name: str
    faction_id: int
    disposition_ids: list[int]


class ArmyListIn(BaseModel):
    name: str
    points_limit: Literal[1000, 2000]
    faction_id: int
    detachment_id: int


class ArmyListOut(BaseModel):
    id: int
    name: str
    points_limit: int
    faction_id: int
    detachment_id: int
