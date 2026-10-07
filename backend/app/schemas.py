from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    leadership: int
    invulnerable: int | None = None
    feel_no_pain: int | None = None
    is_support: bool = False
    is_leader: bool = False
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
    leadership: int
    invulnerable: int | None
    feel_no_pain: int | None
    is_support: bool
    is_leader: bool
    ability_ids: list[int]
    wargear_ids: list[int]


class WeaponIn(BaseModel):
    name: str
    model_id: int
    damage: str = Field(pattern=DAMAGE_PATTERN)
    range: int | None = None
    strength: int
    ap: int
    attacks: int
    skill: int
    weapon_type: Literal["melee", "ranged"] | None = None
    ability_ids: list[int] = []

    @model_validator(mode="after")
    def check_range_required_unless_melee(self):
        if self.weapon_type != "melee" and self.range is None:
            raise ValueError("range is required unless the weapon is melee")
        return self


class WeaponOut(BaseModel):
    id: int
    name: str
    model_id: int
    damage: str
    range: int | None
    strength: int
    ap: int
    attacks: int
    skill: int
    weapon_type: Literal["melee", "ranged"] | None
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
