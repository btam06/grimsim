from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DICE_PATTERN = r"^([0-9]+|[0-9]*D[36](\+[0-9]+)?)$"


class FactionIn(BaseModel):
    name: str


class FactionOut(FactionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # What its lists select, if anything (e.g. the Space Marines' "Chapter"),
    # and the options.
    subfaction_label: str | None = None
    subfactions: list[str] = []


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
    # Required: one of its options is always chosen (there's no "none").
    required: bool = False


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
    # Equipped by default: pre-selected when the model is added to a unit.
    is_default: bool = False

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
    is_default: bool = False


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
    # Whether it's its list's WARLORD (it needs a CHARACTER model): True makes
    # it the Warlord in place of any other unit, False makes it not be - and
    # None (left out) leaves that as it is.
    warlord: bool | None = None


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
    # It's its list's WARLORD.
    warlord: bool = False


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
    # Snap shooting (e.g. Fire Overwatch): hits only on an unmodified 6, with
    # no re-rolls and no Hit roll abilities (Sustained Hits, Lethal Hits).
    snap_shots: bool = False


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
    # (hits: how many were scored - rolled, automatic and extra.)
    hits: int = 0
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
    # Each defending model's wounds left afterwards (0: destroyed), and the
    # hazardous wounds each attacking model took - by unit model id.
    defender_wounds_remaining: dict[int, int] = {}
    attacker_damage: dict[int, int] = {}


class ArmyListIn(BaseModel):
    name: str
    points_limit: Literal[1000, 2000]
    faction_id: int
    detachment_ids: list[int] = []
    # The user who owns the list, if any.
    user_id: int | None = None
    # The unit containing its WARLORD (one of its CHARACTER units), if any.
    warlord_unit_id: int | None = None
    # Its selection for its faction's list selection, if any (e.g. a Space
    # Marines list's Chapter - see FactionOut).
    subfaction: str | None = None


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
    warlord_unit_id: int | None = None
    subfaction: str | None = None



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
    # Who goes first, if already decided; otherwise (left out) the players
    # roll off once everything is set up.
    first_seat: Literal[1, 2] | None = None


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
    # Scored automatically (see app/services/in_game/scoring.py) - a tactical
    # one by claiming it when it's completed; `manual`: what's scored by hand
    # instead, if anything.
    automatic: bool = False
    manual: str | None = None


class ScoreReasonOut(BaseModel):
    text: str
    points: int


class GameScoreOut(BaseModel):
    id: int
    battle_round: int
    turn_seat: int
    kind: str
    points: int
    game_secondary_id: int | None
    # For VP scored automatically: the mission lines met.
    reasons: list[ScoreReasonOut] = []


class GameStratagemUseOut(BaseModel):
    id: int
    stratagem_id: int
    name: str
    battle_round: int
    turn_seat: int
    phase: str
    cp: int
    # The unit it was used on, for one whose game action targets one.
    target_unit_id: int | None = None


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
    # Whether the primary mission is scored automatically, and what of it is
    # scored by hand (if anything).
    primary_automatic: bool = False
    primary_manual: str | None = None
    cp: int
    vp: int
    secondaries: list[GameSecondaryOut]
    scores: list[GameScoreOut]
    stratagem_uses: list[GameStratagemUseOut]


class FirstTurnRollOut(BaseModel):
    # One player's D6 in the roll-off for who goes first (`attempt` 2 and on:
    # after a tie).
    attempt: int
    seat: int
    roll: int


class GameOut(BaseModel):
    id: int
    status: str
    attacker_seat: int
    # Who goes first: None until the roll-off (see first_turn_rolls).
    first_seat: int | None
    battle_round: int
    turn_seat: int | None
    phase: str | None
    players: list[GamePlayerOut]
    # Its terrain (see GET /terrain-layouts/{id}), if one fits the players'
    # dispositions.
    terrain_layout_id: int | None = None
    terrain_layout_name: str | None = None
    # Where deployment is ("formations": declaring battle formations, then
    # "deploying", then "first_turn": the roll-off for who goes first), whose
    # turn it is to deploy a unit, and - at the start of the first battle
    # round - whose to make Scouts moves.
    deployment_step: str | None = None
    deploying_seat: int | None = None
    scouting_seat: int | None = None
    first_turn_rolls: list[FirstTurnRollOut] = []
    # Whose turn it is to pile in, at the start of the fight phase.
    piling_in_seat: int | None = None


class GameStratagemIn(BaseModel):
    seat: Literal[1, 2]
    stratagem_id: int
    # For a stratagem whose game action needs one, e.g. New Orders: the
    # player's Secondary Mission card (game secondary id) it targets - or,
    # e.g. Gunship Extraction, one of their units.
    target_secondary_id: int | None = None
    target_unit_id: int | None = None


class StratagemTargetOut(BaseModel):
    # A unit a stratagem whose game action targets one could be used on.
    unit_id: int
    name: str


class GameAchieveIn(BaseModel):
    # VP to score; defaults to the card's VP for the player's mode.
    points: int | None = Field(default=None, ge=0)


class GameScoreIn(BaseModel):
    seat: Literal[1, 2]
    points: int = Field(ge=0)


class TerrainPointOut(BaseModel):
    x: float
    y: float


class TerrainAreaOut(BaseModel):
    # A terrain area: a kit baseplate (shape) placed at (x, y) and turned
    # `rotation` degrees clockwise about it - a width x height rectangle
    # centred there, or the convex polygon its points make, relative to (x, y)
    # (already flipped if it's mirrored; see app/models/terrain.py).
    id: int
    shape_id: int
    shape_name: str
    x: float
    y: float
    width: float
    height: float
    rotation: float
    mirrored: bool
    points: list[TerrainPointOut] = []


class TerrainFeaturePartOut(BaseModel):
    # One rectangle of a terrain feature: its top-left corner relative to the
    # feature's position (before the feature's rotation), and its size.
    x: float
    y: float
    width: float
    height: float


class TerrainFeatureOut(BaseModel):
    # A terrain feature: a kit ruin wall or obstacle (shape) placed at (x, y)
    # and turned about it; its parts are relative to (x, y) (already flipped if
    # it's mirrored).
    id: int
    shape_id: int
    shape_name: str
    kind: Literal["ruin_wall", "obstacle"]
    x: float
    y: float
    rotation: float
    mirrored: bool
    parts: list[TerrainFeaturePartOut]


class TerrainDeploymentOut(BaseModel):
    # A deployment's zones, each a polygon on the board (corners in order).
    name: str
    attacker_zone: list[TerrainPointOut]
    defender_zone: list[TerrainPointOut]


class TerrainObjectiveOut(BaseModel):
    # An objective: its kind ("attacker_home", "defender_home", "expansion"
    # or "centre"), where its marker goes, and the terrain areas it is.
    id: int
    kind: str
    x: float
    y: float
    area_ids: list[int]


class TerrainLayoutOut(BaseModel):
    id: int
    name: str
    attacker_disposition_id: int
    defender_disposition_id: int
    deployment: TerrainDeploymentOut | None = None
    areas: list[TerrainAreaOut]
    features: list[TerrainFeatureOut]
    objectives: list[TerrainObjectiveOut] = []


class BasePositionIn(BaseModel):
    # A model's base on the board: centred on (x, y) inches, turned `rotation`
    # degrees clockwise. Its size is a base size (by id, e.g. "32mm" or
    # "105 x 70mm"), or given in mm (height_mm defaults to width_mm: round).
    x: float
    y: float
    rotation: float = 0
    base_size_id: int | None = None
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_size(self):
        if (self.base_size_id is None) == (self.width_mm is None):
            raise ValueError("give either base_size_id or width_mm")
        if self.height_mm is not None and self.width_mm is None:
            raise ValueError("height_mm needs width_mm")
        return self


class TerrainPositionOut(BaseModel):
    # Whether any of the base (within) or all of it (wholly within) is over a
    # terrain area or feature.
    id: int
    within: bool
    wholly_within: bool


class BasePositionOut(BaseModel):
    areas: list[TerrainPositionOut]
    features: list[TerrainPositionOut]


class ModelPositionIn(BaseModel):
    # A model's base on the board (see GameModelPosition).
    unit_model_id: int
    x: float
    y: float
    rotation: float = 0


class ModelPositionOut(ModelPositionIn):
    pass


class DeploymentFormationIn(BaseModel):
    # Where to set a unit down: its formation is centred on (x, y) inches.
    unit_id: int
    x: float
    y: float


class DeployUnitIn(BaseModel):
    # A unit's models, each placed on the board - arriving by Rapid Ingress
    # at its Teleport Homer token, if `teleport_homer`.
    unit_id: int
    positions: list[ModelPositionIn]
    teleport_homer: bool = False


class DeploymentModelOut(BaseModel):
    unit_model_id: int
    name: str
    # Its base: the base size's name (None if not entered), and its width and
    # height in inches - a placeholder size if it has no measurements
    # (measured False, e.g. "Use model").
    base_size: str | None
    width: float
    height: float
    measured: bool
    # Where it is, once deployed (None again once it's destroyed).
    position: ModelPositionOut | None = None
    # Its Wounds characteristic, how many it has left in this game, and
    # whether it's been destroyed.
    wounds: int = 0
    wounds_remaining: int = 0
    destroyed: bool = False


class AuraOut(BaseModel):
    # An aura (or similar reach) from one of a unit's models: the option or
    # ability's name, and its range in inches (base to base).
    unit_model_id: int
    name: str
    range: float


class DeploymentUnitOut(BaseModel):
    unit_id: int
    seat: int
    name: str
    # Every model has Infiltrators: it can be set up outside its deployment
    # zone, more than 9" from the enemy's and from enemy models.
    infiltrators: bool
    deployed: bool
    # Where it starts if not on the battlefield ("reserves" or "embarked"),
    # and the transport it's embarked in.
    formation: str | None = None
    transport_unit_id: int | None = None
    # Every model in it has been destroyed in this game.
    destroyed: bool = False
    models: list[DeploymentModelOut]
    # It's Battle-shocked (its models have 0 OC).
    battle_shocked: bool = False
    # In a battle: what reaches out from its models - auras, and how far a
    # Command phase ability can pick a unit (see app/services/in_game/auras.py).
    auras: list[AuraOut] = []


class ObjectiveControlOut(BaseModel):
    # An objective (see the layout's objectives) now: each player's total OC
    # on it (by seat), and who controls it (None: no one - a tie, or nobody's
    # there).
    objective_id: int
    kind: str
    area_ids: list[int]
    oc: dict[int, int]
    controller: int | None = None
    # The player who's secured it (it stays theirs until their opponent has
    # OC on it), if anyone has.
    secured_by: int | None = None


class TerritoryOut(BaseModel):
    # Which line halves the battlefield into the players' territories
    # ("vertical", "horizontal", "diagonal" or "slanted"), its ends, and each player's
    # half (by seat).
    split: str
    line: list[TerrainPointOut]
    territories: dict[int, list[TerrainPointOut]]


class DeploymentOut(BaseModel):
    deploying_seat: int | None
    units: list[DeploymentUnitOut]
    # Who controls each objective now (see app/services/in_game/objectives.py),
    # and the players' territories.
    objectives: list[ObjectiveControlOut] = []
    territory: TerritoryOut | None = None


class ModelProblemsOut(BaseModel):
    unit_model_id: int
    problems: list[str]


class ModelPathOut(BaseModel):
    # The way a model goes from where it started to where it is, where it
    # bends round a wall: the points it goes through.
    unit_model_id: int
    points: list[TerrainPointOut]


class DeploymentCheckOut(BaseModel):
    # Whether a unit could be deployed (or moved) as placed, and if not why:
    # for the unit as a whole, and for each model with a problem - and, for a
    # move, the way each model goes where it bends round a wall.
    valid: bool
    problems: list[str]
    models: list[ModelProblemsOut]
    paths: list[ModelPathOut] = []


class UnitMoveIn(BaseModel):
    # A unit's move: what kind, and where each of its models ends up (every
    # model, moved or not).
    unit_id: int
    kind: Literal["normal", "advance", "fall_back"]
    positions: list[ModelPositionIn]


class UnitIdIn(BaseModel):
    unit_id: int


class MovementModelOut(BaseModel):
    unit_model_id: int
    # Its Movement characteristic, in inches.
    movement: int
    # Where it was at the start of the phase (its moves are measured from
    # there, and resetting puts it back) - None if it's off the battlefield.
    start: ModelPositionOut | None = None


class MovementUnitOut(BaseModel):
    unit_id: int
    name: str
    # The moves it can make this phase: Fall Back if it started within
    # Engagement Range, otherwise a Normal move or Advance. (It can be moved
    # again until the phase ends.)
    allowed_kinds: list[str]
    in_engagement_range: bool
    # The move it made this phase, once it has; and its Advance roll, if it's
    # rolled one (kept for the phase, whether or not it Advances).
    kind: str | None = None
    advance_roll: int | None = None
    moved: bool = False
    # It arrived from Reserves this phase (it can't move again).
    arrived: bool = False
    models: list[MovementModelOut]


class MovementOut(BaseModel):
    # The units the player whose turn it is can move, in their movement phase
    # (empty otherwise).
    units: list[MovementUnitOut]


class ShotOut(BaseModel):
    target_unit_id: int
    target_name: str
    total_damage: int
    models_destroyed: int


class ShootingUnitOut(BaseModel):
    # A unit of the player whose turn it is, in their shooting phase: whether
    # it can shoot (and if not, why), how it moved this turn, and what it
    # shot, once it has.
    unit_id: int
    name: str
    can_shoot: bool
    reason: str | None = None
    advanced: bool
    remained_stationary: bool
    moved_less_than_3: bool
    # How far its furthest-moved model went this turn, if known.
    distance: float | None = None
    shot: ShotOut | None = None
    # The ability it can move after shooting with now (e.g. Ride the
    # Thermals), if any, and how far at most.
    shoot_scoot: str | None = None
    shoot_scoot_reach: float | None = None


class ShootingOut(BaseModel):
    units: list[ShootingUnitOut]


class OverwatchOut(BaseModel):
    # At the end of the movement phase (see GET /games/{id}/overwatch): who
    # can Fire Overwatch (`seat`, None if no one can now), whether they can
    # use the stratagem (and if not, why), its CP, and their units on the
    # battlefield.
    seat: int | None
    available: bool
    reason: str | None = None
    cp: int
    units: list[ShootingUnitOut]


class ShootingWeaponOut(BaseModel):
    # A ranged weapon the unit has (an enhancement's if `enhancement`): how
    # many of its models carry it, how many could fire it at the target (a
    # visible target model within range), and whether any at half range.
    id: int
    enhancement: bool
    name: str
    range: int
    carried_by: int
    # One of the transport's embarked models' weapons, fired with its Firing
    # Deck (`carried_by`: how many embarked models have it).
    firing_deck: bool = False
    in_range: int
    half_range: bool
    # Whether it has Assault; and whether it can't be fired at all this phase
    # (the unit Advanced and it isn't Assault).
    assault: bool = False
    unusable: bool = False
    # Chosen to start with (for melee: each model's first weapon).
    default: bool = False


class ShootingTargetOut(BaseModel):
    unit_id: int
    name: str
    # Whether any of the unit's models can see it (dense terrain blocks
    # sight), and whether it's in cover.
    visible: bool
    in_cover: bool
    weapons: list[ShootingWeaponOut]


class ShootIn(BaseModel):
    unit_id: int
    target_unit_id: int
    weapon_ids: list[int] = []
    enhancement_weapon_ids: list[int] = []
    # A transport's Firing Deck weapons (embarked models' weapons, by weapon
    # id): each fired by the embarked models carrying it, up to its limit.
    firing_deck_weapon_ids: list[int] = []


class ShootOut(BaseModel):
    # What the battlefield gave the calculator, and its result - and the
    # models it destroyed (the target's, or the shooters' own, e.g. to
    # Hazardous), by unit model id: taken off the battlefield.
    in_cover: bool
    advanced: bool
    remained_stationary: bool
    moved_less_than_3: bool
    combat: CombatOut
    destroyed_unit_model_ids: list[int] = []


class SightBubbleOut(BaseModel):
    # Where a unit's guns reach (see GET /games/{id}/shooting/bubble): its
    # longest range it can fire this phase, and the regions it can see within
    # it - drawn together, one shape.
    range: int | None
    regions: list[list[TerrainPointOut]]


class ChargeUnitOut(BaseModel):
    # A unit of the player whose turn it is, in their charge phase: its charge
    # roll (once rolled - the two dice, what its rules add, and their total),
    # whether the charge failed (nothing in reach), and its target once it's
    # charged.
    unit_id: int
    name: str
    dice: list[int] = []
    bonus: int = 0
    roll: int | None = None
    # An ability lets it re-roll its charge roll now (once).
    can_reroll: bool = False
    failed: bool = False
    charged: bool = False
    target_unit_id: int | None = None
    target_name: str | None = None
    # Why it can't charge this turn (it Advanced or Fell Back), if it can't.
    reason: str | None = None


class ChargeOut(BaseModel):
    units: list[ChargeUnitOut]


class ChargeTargetOut(BaseModel):
    # An enemy unit: how close the charging unit is to it (base to base), and
    # whether its roll reaches.
    unit_id: int
    name: str
    distance: float
    in_reach: bool


class ChargeIn(BaseModel):
    # A charge: the target, and where each of the unit's models ends up
    # (every one it has left, moved or not).
    unit_id: int
    target_unit_id: int
    positions: list[ModelPositionIn]


class PileInUnitOut(BaseModel):
    # A unit of the player piling in: whether it can (and if not, why),
    # whether it has, and its models in base contact with an enemy model
    # (they can't move).
    unit_id: int
    name: str
    engaged: bool
    can_pile_in: bool
    reason: str | None = None
    piled_in: bool
    locked_unit_model_ids: list[int] = []


class PileInOut(BaseModel):
    # At the start of the fight phase: whose turn it is to pile in (None once
    # both players are done), and their units.
    seat: int | None
    units: list[PileInUnitOut]


class UnitPlacementIn(BaseModel):
    # Where each of a unit's models ends up (every one it has left).
    unit_id: int
    positions: list[ModelPositionIn]


class SeatIn(BaseModel):
    seat: Literal[1, 2]


class RoundStartRuleOut(BaseModel):
    # A rule that happens at the start of the battle round: its kind
    # ("ability", "army rule", "enhancement" or "detachment rule"), name and
    # text, and the units it's from. An army rule with options (e.g. Doctrina
    # Imperatives) also has which one it is, its options (with what each does
    # in combat), and the one chosen this round (None: none).
    kind: str
    name: str
    description: str
    units: list[str]
    faction_ability_id: int | None = None
    options: list[str] = []
    option_descriptions: dict[str, str] = {}
    # Required: one of its options must be chosen (there's no "none").
    required: bool = False
    chosen: str | None = None
    # It needs the player to decide something (it has options, or its text
    # gives them a choice).
    decision: bool = False


class RuleChoiceIn(BaseModel):
    # A player's option for one of their army rules this battle round (None:
    # none).
    seat: Literal[1, 2]
    faction_ability_id: int
    option: str | None = None


class RoundStartPlayerOut(BaseModel):
    seat: int
    user_name: str
    rules: list[RoundStartRuleOut]


class RoundStartOut(BaseModel):
    # The rules each player has at the start of this battle round.
    battle_round: int
    players: list[RoundStartPlayerOut]


class FightUnitOut(BaseModel):
    # A unit on the battlefield, in the fight phase: whether it has Fights
    # First (and whether that's from charging), whether it's fought, and
    # whether it can fight now (and if not, why).
    unit_id: int
    seat: int
    name: str
    fights_first: bool
    charged: bool
    fought: bool
    can_fight: bool
    reason: str | None = None


class FightLogOut(BaseModel):
    # A unit that's fought this phase, in order.
    unit_id: int
    unit_name: str
    seat: int
    target_name: str
    fights_first: bool
    total_damage: int
    models_destroyed: int


class ConsolidatingOut(BaseModel):
    # The unit that's just fought, which can consolidate now: the unit it
    # fought, and whether that's been destroyed.
    unit_id: int
    unit_name: str
    target_name: str
    target_destroyed: bool


class FightOut(BaseModel):
    # The fight phase's step ("pile_in", "consolidate", "fights_first",
    # "remaining" or "done"), who's to act (pick the next unit to fight, or
    # consolidate), both players' units, and what's fought so far.
    step: str | None
    seat: int | None
    units: list[FightUnitOut]
    fights: list[FightLogOut]
    consolidating: ConsolidatingOut | None = None


class FightTargetOut(BaseModel):
    # An enemy unit within Engagement Range, and the unit's melee weapons
    # against it (in_range: how many of its models can fight with each).
    unit_id: int
    name: str
    weapons: list[ShootingWeaponOut]


class FightResultOut(BaseModel):
    # The calculator's result, and the models it destroyed (taken off the
    # battlefield).
    charged: bool
    fights_first: bool
    combat: CombatOut
    destroyed_unit_model_ids: list[int] = []


class ReachModelIn(BaseModel):
    # A model setting off from (x, y), able to move `distance`.
    unit_model_id: int
    x: float
    y: float
    distance: float


class ReachIn(BaseModel):
    unit_id: int
    models: list[ReachModelIn]


class ReachModelOut(BaseModel):
    # Where the model's base centre can get within its distance, going round
    # what it has to: polygons, together the area. `clearance` is how far its
    # base reaches beyond its centre (to show where the base can get).
    unit_model_id: int
    clearance: float
    regions: list[list[TerrainPointOut]]


class ReachOut(BaseModel):
    models: list[ReachModelOut]


class FormationUnitOut(BaseModel):
    # One of a player's units, as declared: on the battlefield (place None),
    # in Strategic Reserves, or embarked in `transport_unit_id`.
    unit_id: int
    name: str
    points: int
    transport: bool
    place: str | None = None
    transport_unit_id: int | None = None


class FormationPlayerOut(BaseModel):
    seat: int
    user_name: str
    done: bool
    army_points: int
    reserves_points: int
    reserves_limit: int
    units: list[FormationUnitOut]


class FormationsOut(BaseModel):
    # Declaring battle formations (at the start of deployment): each player's
    # units and where they start.
    step: str | None
    players: list[FormationPlayerOut]


class FormationIn(BaseModel):
    seat: Literal[1, 2]
    unit_id: int
    # "reserves", "embarked" (in transport_unit_id), or None: the battlefield.
    place: str | None = None
    transport_unit_id: int | None = None


class ReserveUnitOut(BaseModel):
    unit_id: int
    name: str
    # Every model has Deep Strike: it can arrive anywhere (8" from enemies).
    deep_strike: bool
    # Its Teleport Homer token on the battlefield, if it has one (usable with
    # Rapid Ingress, for 1CP less).
    teleport_homer: dict | None = None


class TeleportHomerUnitOut(BaseModel):
    # A unit with a Teleport Homer, and its token (None: not set up).
    unit_id: int
    name: str
    seat: int
    token: dict | None = None


class TeleportHomersOut(BaseModel):
    # At the start of the battle, the players still setting up their tokens;
    # their units with Teleport Homers; and every token on the battlefield.
    waiting_seats: list[int]
    units: list[TeleportHomerUnitOut]
    tokens: list[dict]


class StartOfShootingOut(BaseModel):
    # An ability the player whose turn it is can use at the start of their
    # Shooting phase (e.g. Secutor of Olympus), and its possible targets.
    unit_id: int
    unit_name: str
    ability: str
    description: str | None = None
    targets: list[UnitIdNameOut]


class StartOfShootingIn(BaseModel):
    unit_id: int
    ability: str
    target_unit_id: int


class StartOfShootingResultOut(BaseModel):
    # The D6 rolled, the mortal wounds it inflicted (0 if it failed), and the
    # models they destroyed.
    roll: int
    wounds: int
    destroyed_unit_model_ids: list[int]


class ScoutsUnitOut(BaseModel):
    # A unit that can make a Scouts move, and how far.
    unit_id: int
    name: str
    distance: int
    moved: bool


class ScoutsOut(BaseModel):
    # Whose turn it is to make Scouts moves (None: no one's), and their units
    # that can.
    seat: int | None
    units: list[ScoutsUnitOut]


class TeleportHomerIn(BaseModel):
    seat: Literal[1, 2]
    unit_id: int | None = None
    x: float | None = None
    y: float | None = None


class PsychicAbilityOut(BaseModel):
    # One of a PSYKER unit's psychic abilities: its level, whether it can be
    # used now (and if not, why), and - for Soul Sight - the units it could
    # pick.
    name: str
    level: int
    usable: bool
    reason: str | None = None
    targets: list[UnitIdNameOut] = []


class PsychicUnitOut(BaseModel):
    unit_id: int
    name: str
    seat: int
    psyker_level: int
    used_this_round: int
    abilities: list[PsychicAbilityOut]


class PsychicUseOut(BaseModel):
    unit_name: str
    ability: str
    roll: int
    target_name: str | None = None


class PsychicOut(BaseModel):
    # Every PSYKER unit on the battlefield and its psychic abilities, and the
    # uses this battle round.
    units: list[PsychicUnitOut]
    uses: list[PsychicUseOut]


class PsychicIn(BaseModel):
    unit_id: int
    ability: str
    target_unit_id: int | None = None


class ReservesOut(BaseModel):
    # Bringing units in from Strategic Reserves, in the movement phase: whose
    # turn it is to (`seat`) - the player whose turn it is, or at the end of
    # the phase ("rapid_ingress") their opponent, with the stratagem - and
    # their units in Reserves. `seat` is None when none can arrive (the first
    # battle round, or outside the movement phase).
    step: str | None
    seat: int | None
    battle_round: int
    units: list[ReserveUnitOut]


class ReanimationUnitOut(BaseModel):
    # A unit's Reanimation Protocols this turn: its D3 roll, the wounds that
    # restored to wounded models and the destroyed models it returned - and
    # where to start those still to be set up (none once they are).
    unit_id: int
    name: str
    roll: int
    healed: int
    returned: int
    to_place: list[ModelPositionOut] = []


class ReanimationOut(BaseModel):
    # At the end of the command phase (see GET /games/{id}/reanimation): the
    # player whose turn it is's Reanimation Protocols, and whether the game
    # is waiting for them to set up returned models.
    placing: bool
    seat: int | None
    units: list[ReanimationUnitOut]


class UnitIdNameOut(BaseModel):
    unit_id: int
    name: str


class CommandAbilityOut(BaseModel):
    # One of the player whose turn it is's units' abilities whose option is
    # selected in their Command phase (see GET /games/{id}/command): its
    # options (with what each does), whether one must be selected, whether it
    # stays until another is (`persistent`), the option active now and
    # whether it was selected this phase - and, for one that applies to
    # another unit, the units it could (`targets`) and the one it does. An
    # army rule (e.g. Combat Doctrines) has its faction ability's id instead
    # of a unit's, the units with it, and the options already used up this
    # battle (`used_options`).
    unit_id: int | None = None
    unit_name: str
    faction_ability_id: int | None = None
    used_options: list[str] = []
    ability: str
    description: str
    options: list[str]
    option_descriptions: dict[str, str] = {}
    required: bool
    persistent: bool
    active: str | None = None
    chosen: bool = False
    targets: list[UnitIdNameOut] = []
    target_unit_id: int | None = None
    needs_target: bool = False
    # Options that target an enemy unit (e.g. Invocation of Machine
    # Vengeance), and the enemy units each could.
    option_targets: dict[str, list[UnitIdNameOut]] = {}


class CommandHealOut(BaseModel):
    # A model that healed at the start of the Command phase: its roll and the
    # wounds it regained.
    unit_name: str
    model_name: str
    ability: str
    roll: int
    healed: int


class CommandOut(BaseModel):
    # The player whose turn it is's Command phase abilities (None: it isn't a
    # Command phase).
    seat: int | None
    abilities: list[CommandAbilityOut]
    heals: list[CommandHealOut]


class CommandChoiceIn(BaseModel):
    # A unit's ability's option - or, with `faction_ability_id` (and no
    # unit), an army rule's.
    seat: Literal[1, 2]
    unit_id: int | None = None
    faction_ability_id: int | None = None
    ability: str = ""
    # None: none (only for one that needn't have one).
    option: str | None = None
    target_unit_id: int | None = None


class BattleShockTestOut(BaseModel):
    # A Battle-shock test a unit takes (or must): why, any modifier, the
    # Leadership it needs, its strength - and once taken, its dice (none for
    # Insane Bravery) and whether it passed.
    id: int
    unit_id: int
    unit_name: str
    seat: int
    reason: str
    modifier: int
    leadership: int
    starting_strength: int
    current_strength: int
    dice: list[int] = []
    insane_bravery: bool = False
    passed: bool | None = None
    # Mortal wounds it suffered for failing (e.g. "Delirium: D3 rolled 2").
    mortal_wounds: str | None = None


class BattleShockUnitOut(BaseModel):
    unit_id: int
    name: str
    seat: int


class BattleShockOut(BaseModel):
    # Battle-shock now (see GET /games/{id}/battle-shock): the tests waiting
    # to be taken, those taken this phase, the Battle-shocked units, and
    # whether each player (by seat) can use Insane Bravery (None) or why not.
    pending: list[BattleShockTestOut]
    taken: list[BattleShockTestOut]
    battle_shocked: list[BattleShockUnitOut]
    insane_bravery_cp: int | None = None
    insane_bravery: dict[int, str | None] = {}


class BattleShockTakeIn(BaseModel):
    # Take the test with Insane Bravery (passed automatically, for its CP)?
    insane_bravery: bool = False


class BattleShockRequireIn(BaseModel):
    # A rule or stratagem makes the unit take a Battle-shock test.
    unit_id: int
    reason: str
    modifier: int = 0


class DestroyedModelOut(BaseModel):
    # A model destroyed in a turn: when (phase), whose, its unit, the unit
    # whose attacks destroyed it (None: none), and whether its unit was
    # destroyed with it.
    phase: str | None = None
    seat: int
    unit_id: int
    unit_name: str
    model_name: str
    destroyed_by_unit_id: int | None = None
    destroyed_by: str | None = None
    unit_destroyed: bool


class TurnStartObjectiveOut(BaseModel):
    # An objective at the start of the turn: who controlled it (None: no
    # one), and the units within range of it.
    objective_id: int
    kind: str
    controller: int | None = None
    unit_ids: list[int] = []


class TurnRecordOut(BaseModel):
    # What happened in a turn (see GET /games/{id}/turn-record): the models
    # destroyed, and how the objectives stood at its start (none recorded:
    # an empty list).
    battle_round: int
    turn_seat: int
    destroyed: list[DestroyedModelOut]
    start: list[TurnStartObjectiveOut]


class ClaimOfferOut(BaseModel):
    # A tactical secondary completed at a scoring moment, waiting for its
    # holder to claim or hold it: its VP and why.
    id: int
    seat: int
    game_secondary_id: int
    name: str
    timing: str
    points: int
    reasons: list[ScoreReasonOut]


class ScoringOut(BaseModel):
    # Automatic scoring now (see GET /games/{id}/scoring): the tactical
    # secondaries to claim or hold, and what was scored this turn (by seat).
    offers: list[ClaimOfferOut]
    scored: dict[int, list[GameScoreOut]]


class ActionTargetOut(BaseModel):
    kind: str  # "objective" or "area"
    id: int
    label: str


class ActionOptionOut(BaseModel):
    # An action the unit's player has (from a mission card): what the unit
    # could do it on now, or why it can't.
    action: str
    card: str
    completes: str
    targets: list[ActionTargetOut]
    reason: str | None = None


class UnitActionOut(BaseModel):
    # An action a unit started this turn, and how it's gone ("started",
    # "completed" or "failed").
    unit_id: int
    unit_name: str
    action: str
    target: str
    status: str


class ActionsOut(BaseModel):
    # In the Shooting phase (see GET /games/{id}/actions): each of the
    # player whose turn it is's units' actions (by unit id), and the actions
    # started this turn.
    options: dict[int, list[ActionOptionOut]]
    started: list[UnitActionOut]


class ActionIn(BaseModel):
    unit_id: int
    action: str
    target_id: int


class OperationMarkerOut(BaseModel):
    # An operation marker on the battlefield: whose, what placed it, and
    # where - an objective's marker point or a terrain area's middle (x, y).
    id: int
    seat: int
    source: str
    objective_id: int | None = None
    area_id: int | None = None
    x: float
    y: float
    label: str


class MarkedUnitOut(BaseModel):
    unit_id: int
    unit_name: str
    seat: int
    kind: str


class PromptOptionOut(BaseModel):
    # Something a prompt's player can pick: a terrain area, an objective, an
    # enemy unit or an operation marker (for consecration: which of their
    # units it's for).
    id: int
    label: str
    unit_id: int | None = None


class MissionPromptOut(BaseModel):
    # A choice a mission needs from a player (see GET /games/{id}/mission):
    # what kind, why, its options, and how many to pick (at least, at most).
    id: int
    seat: int
    kind: str
    mission: str
    text: str
    options: list[PromptOptionOut]
    pick_min: int
    pick_max: int
    # For guarding objectives (Burden of Trust): the units that can guard
    # them (`options` are the objectives).
    units: list[PromptOptionOut] = []


class MissionStateOut(BaseModel):
    prompts: list[MissionPromptOut]
    markers: list[OperationMarkerOut]
    marked: list[MarkedUnitOut]


class MissionAnswerIn(BaseModel):
    # The answer to a prompt: the ids picked (terrain areas, enemy units or
    # an operation marker) - or, for consecration, {unit id: objective id}.
    ids: list[int] = []
    consecrations: dict[int, int] = {}
    # Guarding objectives: {objective id: unit id}.
    guards: dict[int, int] = {}


class EmbarkedUnitOut(BaseModel):
    # A unit embarked in a transport that's on the battlefield.
    unit_id: int
    name: str
    transport_unit_id: int
    transport_name: str


class EmbarkableUnitOut(BaseModel):
    # A unit that's moved and can embark now, and the transports it can
    # embark in.
    unit_id: int
    name: str
    transports: list[UnitIdNameOut]


class EmbarkedOut(BaseModel):
    # In the movement phase (see GET /games/{id}/embarked): the units the
    # player whose turn it is can disembark, and those it can embark (None:
    # no one can now).
    seat: int | None
    units: list[EmbarkedUnitOut]
    embarkable: list[EmbarkableUnitOut] = []


class EmergencyRollOut(BaseModel):
    # A roll after an emergency disembark (see GameEmergencyRoll): its kind
    # ("hazard", "deadly_demise" or "deadly_demise_wounds"), the model or unit
    # it's for, the roll and the wounds it caused.
    kind: str
    name: str | None = None
    roll: int
    wounds: int


class EmergencyUnitOut(BaseModel):
    # A unit that must emergency disembark from a destroyed transport: where
    # to start its models (only those that fit within 3"), and the
    # transport's wreck (each of its models' bases, as positions with their
    # base sizes in inches).
    unit_id: int
    name: str
    seat: int
    transport_unit_id: int
    transport_name: str
    suggested: list[ModelPositionOut]
    wreck: list[dict]
    # Its models that aren't destroyed ({unit_model_id, name}).
    models: list[dict] = []


class EmergencyOut(BaseModel):
    # Units still to emergency disembark, and the rolls made after those
    # that have (this game, latest last).
    units: list[EmergencyUnitOut]
    rolls: list[EmergencyRollOut] = []


class EmbarkIn(BaseModel):
    unit_id: int
    transport_unit_id: int
