from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DICE_PATTERN = r"^([0-9]+|[0-9]*D[36](\+[0-9]+)?)$"


class FactionIn(BaseModel):
    name: str


class FactionOut(FactionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FactionUnitIn(BaseModel):
    name: str
    faction_id: int


class FactionUnitOut(FactionUnitIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FactionAbilityIn(BaseModel):
    name: str
    description: str | None = None
    faction_id: int


class FactionAbilityOut(FactionAbilityIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Names of the selectable rule options this ability grants in combat
    # (e.g. Doctrina Imperatives' Protector/Conqueror Imperatives), defined in
    # the faction's app/seeds/factions/<faction>/abilities.py. Read-only.
    rule_options: list[str] = []


class KeywordIn(BaseModel):
    name: str


class KeywordOut(KeywordIn):
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
    keyword_ids: list[int] = []
    faction_ability_ids: list[int] = []


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
    keyword_ids: list[int]
    faction_ability_ids: list[int]


class WeaponIn(BaseModel):
    name: str
    model_id: int
    damage: str = Field(pattern=DICE_PATTERN)
    range: int | None = None
    strength: int
    ap: int = Field(le=0)
    attacks: str = Field(pattern=DICE_PATTERN)
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
    attacks: str
    skill: int
    weapon_type: Literal["melee", "ranged"] | None
    ability_ids: list[int]


class WargearIn(BaseModel):
    name: str
    model_id: int
    description: str | None = None
    ability_ids: list[int] = []


class WargearOut(BaseModel):
    id: int
    name: str
    model_id: int
    description: str | None
    ability_ids: list[int]


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
    faction_unit_id: int
    points: int
    list_id: int | None = None
    unit_models: list[UnitModelIn] = []


class UnitOut(BaseModel):
    id: int
    faction_unit_id: int
    points: int
    list_id: int | None
    unit_models: list[UnitModelOut]


class ConditionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    name: str
    description: str | None


class EffectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    name: str
    description: str | None


class WeaponAbilityIn(BaseModel):
    name: str
    description: str | None = None
    condition_ids: list[int] = []
    effect_ids: list[int] = []


class WeaponAbilityOut(BaseModel):
    id: int
    name: str
    description: str | None
    condition_ids: list[int]
    effect_ids: list[int]


class WargearAbilityIn(BaseModel):
    name: str
    description: str | None = None
    condition_ids: list[int] = []
    effect_ids: list[int] = []


class WargearAbilityOut(BaseModel):
    id: int
    name: str
    description: str | None
    condition_ids: list[int]
    effect_ids: list[int]


class DatasheetAbilityIn(BaseModel):
    name: str
    description: str | None = None
    condition_ids: list[int] = []
    effect_ids: list[int] = []


class DatasheetAbilityOut(BaseModel):
    id: int
    name: str
    description: str | None
    condition_ids: list[int]
    effect_ids: list[int]


class DispositionIn(BaseModel):
    name: str
    description: str | None = None


class DispositionOut(DispositionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class DetachmentIn(BaseModel):
    name: str
    faction_id: int
    dp: int
    disposition_ids: list[int] = []


class DetachmentOut(BaseModel):
    id: int
    name: str
    faction_id: int
    dp: int
    disposition_ids: list[int]


class StratagemIn(BaseModel):
    name: str
    description: str | None = None
    cp: int = Field(ge=0)
    is_core: bool = False
    detachment_ids: list[int] = []
    condition_ids: list[int] = []
    effect_ids: list[int] = []

    @model_validator(mode="after")
    def check_core_xor_detachments(self):
        # Core stratagems are usable by any detachment, so they're attached to
        # none; every other stratagem must belong to at least one detachment.
        if self.is_core and self.detachment_ids:
            raise ValueError("core stratagems cannot be attached to detachments")
        if not self.is_core and not self.detachment_ids:
            raise ValueError("non-core stratagems must be attached to at least one detachment")
        return self


class StratagemOut(BaseModel):
    id: int
    name: str
    description: str | None
    cp: int
    is_core: bool
    detachment_ids: list[int]
    condition_ids: list[int]
    effect_ids: list[int]


class CombatIn(BaseModel):
    game_id: int | None = None
    attacking_unit_id: int
    defending_unit_id: int
    selected_weapon_ids: list[int] = []
    # Stratagems used on the attacking unit for this attack - each must be core
    # or belong to one of the detachments in the attacking unit's army list.
    stratagem_ids: list[int] = []
    # Whether attacks from weapons with the Precision effect pick off leaders
    # (then supports) first, rather than following normal targeting.
    apply_precision: bool = False
    # Active rule options from faction abilities (e.g. "Protector Imperative"
    # for Doctrina Imperatives), per side. A unit only gains an option if one
    # of its models has the faction ability that grants it.
    attacker_rule_options: list[str] = []
    defender_rule_options: list[str] = []
    in_engagement_range: bool = False
    in_cover: bool = False
    half_range: bool = False
    moved_less_than_3: bool = False
    advanced: bool = False
    defender_visible: bool = True
    defender_in_range: bool = True


class WeaponCombatResultOut(BaseModel):
    name: str
    attack_rolls: list[int]
    attack_rerolls: list[int]
    wound_rolls: list[int]
    wound_rerolls: list[int]
    save_rolls: list[int]
    fnp_rolls: list[int]
    total_damage: int
    models_destroyed: int
    hazardous_rolls: list[int]
    hazardous_wounds: int


class CombatOut(BaseModel):
    visible: bool
    in_range: bool
    in_engagement_range: bool
    in_cover: bool
    half_range: bool
    moved_less_than_3: bool
    advanced: bool
    attack_rolls: list[int]
    attack_rerolls: list[int]
    wound_rolls: list[int]
    wound_rerolls: list[int]
    save_rolls: list[int]
    fnp_rolls: list[int]
    total_damage: int
    models_destroyed: int
    defending_models_remaining: int
    hazardous_rolls: list[int]
    hazardous_wounds: int
    hazardous_models_destroyed: int
    deadly_demise_rolls: list[int]
    deadly_demise_explosions: int
    weapon_results: list[WeaponCombatResultOut]


class ArmyListIn(BaseModel):
    name: str
    points_limit: Literal[1000, 2000]
    faction_id: int
    detachment_ids: list[int] = []


class ArmyListOut(BaseModel):
    id: int
    name: str
    points_limit: int
    faction_id: int
    detachment_ids: list[int]
