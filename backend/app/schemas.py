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
    # Names of the selectable rule options this ability grants in combat
    # (e.g. Canticles of the Omnissiah), defined in
    # app/seeds/datasheet_abilities.py. Read-only.
    rule_options: list[str] = []


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


PhaseName = Literal["command", "movement", "shooting", "charge", "fight"]


class StratagemTimingSchema(BaseModel):
    # A phase a stratagem can be used in, and whose turn (from the using
    # player's point of view).
    phase: PhaseName
    turn: Literal["your_turn", "opponent_turn", "either"]


class StratagemIn(BaseModel):
    name: str
    description: str | None = None
    cp: int = Field(ge=0)
    is_core: bool = False
    detachment_ids: list[int] = []
    condition_ids: list[int] = []
    effect_ids: list[int] = []
    # Keywords a model must have (all of them) for the stratagem to apply to
    # it; empty means any model.
    keyword_ids: list[int] = []
    # When it can be used in a game; empty means any time.
    timings: list[StratagemTimingSchema] = []

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
    keyword_ids: list[int]
    timings: list[StratagemTimingSchema]


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
    # The user who owns the list, if any.
    user_id: int | None = None


class ArmyListOut(BaseModel):
    id: int
    name: str
    points_limit: int
    faction_id: int
    detachment_ids: list[int]
    user_id: int | None



class UserIn(BaseModel):
    name: str


class UserOut(UserIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class SecondaryMissionIn(BaseModel):
    name: str
    description: str | None = None
    completes_on: Literal["your_turn", "opponent_turn"]
    # VP for completing it in each mode; None means it can't be used in that mode.
    fixed_points: int | None = Field(default=None, ge=0)
    tactical_points: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_usable_in_a_mode(self):
        if self.fixed_points is None and self.tactical_points is None:
            raise ValueError("a secondary mission needs points for at least one mode")
        return self


class SecondaryMissionOut(SecondaryMissionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PrimaryMissionIn(BaseModel):
    name: str
    description: str | None = None
    player_disposition_id: int
    opponent_disposition_id: int


class PrimaryMissionOut(PrimaryMissionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class GamePlayerIn(BaseModel):
    user_id: int
    list_id: int
    secondary_mode: Literal["fixed", "tactical"]
    # Needed only if the list's detachments have more than one disposition.
    disposition_id: int | None = None
    # Fixed mode: the 2 secondary missions kept all game.
    fixed_secondary_ids: list[int] = []


class GameIn(BaseModel):
    players: list[GamePlayerIn] = Field(min_length=2, max_length=2)
    # Seats are 1 and 2, in the order of `players`.
    attacker_seat: Literal[1, 2]
    first_seat: Literal[1, 2]


class GameSecondaryOut(BaseModel):
    id: int
    secondary_mission_id: int
    name: str
    description: str | None
    completes_on: str
    points: int  # for the player's mode
    status: str
    fixed: bool
    drawn_round: int


class GameScoreOut(BaseModel):
    id: int
    battle_round: int
    turn_seat: int
    kind: str
    points: int
    game_secondary_id: int | None


class GameStratagemUseOut(BaseModel):
    id: int
    stratagem_id: int
    name: str
    battle_round: int
    turn_seat: int
    phase: str
    cp: int


class GamePlayerOut(BaseModel):
    id: int
    seat: int
    user_id: int
    user_name: str
    list_id: int
    list_name: str
    secondary_mode: str
    disposition_id: int | None
    disposition_name: str | None
    primary_mission_id: int | None
    primary_mission_name: str | None
    primary_mission_description: str | None
    cp: int
    vp: int
    secondaries: list[GameSecondaryOut]
    scores: list[GameScoreOut]
    stratagem_uses: list[GameStratagemUseOut]


class GameOut(BaseModel):
    id: int
    status: str
    attacker_seat: int
    first_seat: int
    battle_round: int
    turn_seat: int | None
    phase: str | None
    players: list[GamePlayerOut]


class GameStratagemIn(BaseModel):
    seat: Literal[1, 2]
    stratagem_id: int


class GameScoreIn(BaseModel):
    seat: Literal[1, 2]
    points: int = Field(ge=0)
