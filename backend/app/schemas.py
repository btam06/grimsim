from pydantic import BaseModel, ConfigDict


class FactionIn(BaseModel):
    name: str


class FactionOut(FactionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ModelIn(BaseModel):
    name: str
    faction_id: int
    points: int
    save: int
    toughness: int
    oc: int
    movement: int
    wounds: int
    invulnerable: int | None = None
    feel_no_pain: int | None = None
    ability_ids: list[int] = []
    weapon_ids: list[int] = []


class ModelOut(BaseModel):
    id: int
    name: str
    faction_id: int
    points: int
    save: int
    toughness: int
    oc: int
    movement: int
    wounds: int
    invulnerable: int | None
    feel_no_pain: int | None
    ability_ids: list[int]
    weapon_ids: list[int]


class WeaponIn(BaseModel):
    name: str
    model_id: int
    damage: int
    range: int
    strength: int
    attacks: int
    ability_ids: list[int] = []


class WeaponOut(BaseModel):
    id: int
    name: str
    model_id: int
    damage: int
    range: int
    strength: int
    attacks: int
    ability_ids: list[int]


class UnitIn(BaseModel):
    name: str
    model_ids: list[int] = []


class UnitOut(BaseModel):
    id: int
    name: str
    model_ids: list[int]


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
