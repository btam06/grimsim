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
    # What each option does in the calculator: {option name: description}.
    rule_option_descriptions: dict[str, str] = {}
    # How the calculator handles the ability, where that needs saying.
    calculator_notes: list[str] = []


class KeywordIn(BaseModel):
    name: str


class KeywordOut(KeywordIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class BaseSizeIn(BaseModel):
    # As written on datasheets, e.g. "32mm", "105 x 70mm" or "Use model".
    name: str = Field(min_length=1, max_length=64)


class BaseSizeOut(BaseSizeIn):
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
    # Feel No Pain against mortal wounds only (e.g. 5+), on top of any
    # feel_no_pain.
    feel_no_pain_mortal: int | None = None
    # The invulnerable save only applies against ranged attacks.
    invulnerable_ranged_only: bool = False
    # One of the base sizes (GET /base-sizes); None if not entered.
    base_size_id: int | None = None
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
    feel_no_pain_mortal: int | None
    invulnerable_ranged_only: bool
    base_size_id: int | None
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
    # Who its abilities reach: the bearer's weapons, or every model's in the
    # bearer's unit.
    scope: Literal["bearer", "bearers_unit"] = "bearer"


class WargearOut(BaseModel):
    id: int
    name: str
    model_id: int
    description: str | None
    ability_ids: list[int]
    scope: str


class UnitModelIn(BaseModel):
    model_id: int
    weapon_ids: list[int] = []
    wargear_ids: list[int] = []
    # An enhancement this model carries (a CHARACTER from a list that has
    # taken the enhancement's detachment).
    enhancement_id: int | None = None


class UnitModelOut(BaseModel):
    id: int
    model_id: int
    weapon_ids: list[int]
    wargear_ids: list[int]
    enhancement_id: int | None


class UnitIn(BaseModel):
    faction_unit_id: int
    points: int
    list_id: int | None = None
    unit_models: list[UnitModelIn] = []
    # An upgrade the whole unit takes (from a detachment its list has taken).
    upgrade_id: int | None = None
    # Detachment rules with a selection limit this unit is selected for.
    selected_rule_ids: list[int] = []


class SelectableRuleOut(BaseModel):
    # A detachment rule a unit can be selected for in list building (e.g.
    # Houndpack Alphas), and how many other units in the list already are.
    id: int
    name: str
    description: str | None
    selection_limit: int
    selected_elsewhere: int


class UnitOut(BaseModel):
    id: int
    faction_unit_id: int
    points: int
    list_id: int | None
    unit_models: list[UnitModelOut]
    upgrade_id: int | None
    selected_rule_ids: list[int] = []


EnhancementScope = Literal["bearer", "led_unit", "bearers_unit", "unit"]


class EnhancementWeaponAbilitySchema(BaseModel):
    # A weapon ability an enhancement/upgrade grants - to every weapon, or only
    # "ranged" or "melee" ones - and who it reaches (see ENHANCEMENT_SCOPES).
    weapon_ability_id: int
    weapon_type: Literal["ranged", "melee"] | None = None
    scope: EnhancementScope


class EnhancementDatasheetAbilitySchema(BaseModel):
    datasheet_ability_id: int
    scope: EnhancementScope


class DetachmentRuleWeaponAbilitySchema(BaseModel):
    weapon_ability_id: int
    weapon_type: Literal["ranged", "melee"] | None = None


class DetachmentRuleIn(BaseModel):
    detachment_id: int
    name: str
    description: str | None = None
    # Alternative keyword sets; a unit is reached if every model in it has all
    # of one of them. Empty means every unit.
    keyword_option_ids: list[list[int]] = []
    weapon_abilities: list[DetachmentRuleWeaponAbilitySchema] = []
    datasheet_ability_ids: list[int] = []
    # Keywords it gives the models it reaches (e.g. BATTLELINE).
    granted_keyword_ids: list[int] = []
    # False: reaches units whose every model matches an option. True: reaches
    # each matching model on its own, in any unit.
    per_model: bool = False
    # Only reaches units selected for it in list building, up to this many per
    # list (e.g. 3 WAR DOG units have CHARACTER). None: every matching unit.
    selection_limit: int | None = Field(default=None, ge=1)


class DetachmentRuleOut(BaseModel):
    id: int
    detachment_id: int
    name: str
    description: str | None
    keyword_option_ids: list[list[int]]
    weapon_abilities: list[DetachmentRuleWeaponAbilitySchema]
    datasheet_ability_ids: list[int]
    granted_keyword_ids: list[int] = []
    selection_limit: int | None = None
    per_model: bool


class EnhancementKeywordSchema(BaseModel):
    # A keyword an enhancement/upgrade gives models, and who it reaches.
    keyword_id: int
    scope: EnhancementScope


class EnhancementWeaponSchema(BaseModel):
    # A weapon an enhancement gives its bearer: a full profile, and weapon
    # abilities by id.
    name: str
    weapon_type: Literal["melee", "ranged"]
    range: int | None = None
    attacks: str = Field(pattern=DICE_PATTERN)
    skill: int
    strength: int
    ap: int = Field(le=0)
    damage: str = Field(pattern=DICE_PATTERN)
    ability_ids: list[int] = []


class EnhancementWeaponOut(EnhancementWeaponSchema):
    id: int


class EnhancementIn(BaseModel):
    name: str
    description: str | None = None
    points: int = Field(ge=0)
    kind: Literal["enhancement", "upgrade"]
    detachment_id: int
    # Keywords needed (all of them) on the model carrying an enhancement, or
    # on every model in a unit taking an upgrade; empty means none.
    keyword_ids: list[int] = []
    # Keywords that rule it out (any one of them); empty means none.
    excluded_keyword_ids: list[int] = []
    # Abilities it grants in combat. An enhancement's reach the bearer or the
    # unit it leads; an upgrade's, the unit.
    weapon_abilities: list[EnhancementWeaponAbilitySchema] = []
    datasheet_abilities: list[EnhancementDatasheetAbilitySchema] = []
    # Keywords it gives models (e.g. SKITARII for the bearer's unit).
    granted_keywords: list[EnhancementKeywordSchema] = []
    # Weapons the bearer has (enhancements only).
    weapons: list[EnhancementWeaponSchema] = []

    @model_validator(mode="after")
    def check_scopes(self):
        allowed = {
            "enhancement": ("bearer", "led_unit", "bearers_unit"),
            "upgrade": ("unit",),
        }[self.kind]
        if self.weapons and self.kind != "enhancement":
            raise ValueError("only an enhancement (carried by a model) can give a weapon")
        for grant in [*self.weapon_abilities, *self.datasheet_abilities, *self.granted_keywords]:
            if grant.scope not in allowed:
                raise ValueError(
                    f"an {self.kind}'s abilities must have scope {' or '.join(allowed)}"
                )
        return self


class EnhancementOut(BaseModel):
    id: int
    name: str
    description: str | None
    points: int
    kind: str
    detachment_id: int
    keyword_ids: list[int]
    excluded_keyword_ids: list[int]
    weapon_abilities: list[EnhancementWeaponAbilitySchema]
    datasheet_abilities: list[EnhancementDatasheetAbilitySchema]
    granted_keywords: list[EnhancementKeywordSchema]
    weapons: list[EnhancementWeaponOut]


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
    # What each option does in the calculator: {option name: description}.
    rule_option_descriptions: dict[str, str] = {}
    # How the calculator handles the ability, where that needs saying.
    calculator_notes: list[str] = []


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
    # e.g. "DYNASTY" - a list can't take two detachments with the same tag.
    unique_tag: str | None = Field(default=None, max_length=50)


class DetachmentOut(BaseModel):
    id: int
    name: str
    faction_id: int
    dp: int
    disposition_ids: list[int]
    unique_tag: str | None = None


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
    # Keywords that stop it applying to a model (any one of them); empty
    # means nothing is excluded.
    excluded_keyword_ids: list[int] = []
    # Alternative keyword sets, one of which a model must have all of (e.g.
    # [[SICARIAN], [SKITARII, MOUNTED]]); empty means no alternatives.
    keyword_option_ids: list[list[int]] = []
    # When it can be used in a game; empty means any time.
    timings: list[StratagemTimingSchema] = []
    # What the game tracker does when it's used, besides spending CP.
    game_action: Literal["replace_secondary"] | None = None
    # Which unit in a combat it's used on; None means either.
    combat_side: Literal["attacker", "defender"] | None = None
    # How long its effect lasts beyond the phase it's used in; None: just that
    # phase.
    duration: Literal["until_end_of_turn", "until_next_command_phase"] | None = None

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
    excluded_keyword_ids: list[int]
    keyword_option_ids: list[list[int]]
    timings: list[StratagemTimingSchema]
    game_action: str | None
    combat_side: str | None
    duration: str | None


class PositionOut(BaseModel):
    id: str
    label: str


class CombatIn(BaseModel):
    game_id: int | None = None
    attacking_unit_id: int
    defending_unit_id: int
    selected_weapon_ids: list[int] = []
    # Weapons the attacking unit's enhancements give it (EnhancementWeapon
    # ids, e.g. TL-4Ø9) to attack with as well.
    selected_enhancement_weapon_ids: list[int] = []
    # Stratagems used on the attacking unit, and on the defending unit, for this
    # attack - each must be usable on that unit, by that side, in this phase
    # (see GET /combat/stratagems).
    stratagem_ids: list[int] = []
    defender_stratagem_ids: list[int] = []
    # Where each unit is, for rules the calculator can't measure (see GET
    # /combat/positions), e.g. ["near_admech_battleline"].
    attacker_positions: list[str] = []
    defender_positions: list[str] = []
    # The attacking unit made a Charge move this turn (e.g. for [LANCE]).
    charged: bool = False
    # The defending unit is Battle-shocked (e.g. for the Chaos Knights' Doom).
    defender_battle_shocked: bool = False
    # The attacking model is on its Damaged profile (e.g. a War Dog with 1-5
    # wounds remaining: -1 to hit).
    attacker_damaged: bool = False
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
    damage: str
    attack_rolls: list[int]
    attack_rerolls: list[int]
    wound_rolls: list[int]
    wound_rerolls: list[int]
    save_rolls: list[int]
    fnp_rolls: list[int]
    damage_rolls: list[int]
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


class ListEligibleOut(BaseModel):
    # What a unit in this list can be made of: faction units and models from
    # the list's faction, plus any its ally rules let in.
    faction_unit_ids: list[int]
    model_ids: list[int]


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
    completes_on: Literal["your_turn", "opponent_turn", "either"]
    # (Base) VP for completing it in each mode; None means it can't be used in
    # that mode. Many cards score more or less depending on the outcome, so
    # the VP can be adjusted when it's achieved in a game.
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
    # For a stratagem whose game action needs one, e.g. New Orders: the
    # player's Secondary Mission card (game secondary id) it targets.
    target_secondary_id: int | None = None


class GameAchieveIn(BaseModel):
    # VP to score; defaults to the card's VP for the player's mode.
    points: int | None = Field(default=None, ge=0)


class GameScoreIn(BaseModel):
    seat: Literal[1, 2]
    points: int = Field(ge=0)
