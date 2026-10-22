from __future__ import annotations

import random
import re
from collections import deque
from dataclasses import dataclass, field
from types import SimpleNamespace

from app.combat_rules import CONDITIONS, EFFECTS, Rule
from app.combat_rules.effects import OWN_UNIT_EFFECTS
from app.models import DetachmentRule, Model, Stratagem, Unit, WargearAbility, WeaponAbility
from app.services import detachment_rules as detachment_rule_service
from app.services import enhancements as enhancement_rules

_DICE_PATTERN = re.compile(
    r"^(?:(?P<flat>[0-9]+)|(?P<count>[0-9]*)D(?P<die>[36])(?:\+(?P<plus>[0-9]+))?)$"
)


def roll_dice(notation: str) -> int:
    # notation is either a flat number or dice notation (D3/D6/2D6/D6+1/...); roll
    # it to a value. Used for both a weapon's damage and its number of attacks.
    return roll_dice_faces(notation)[0]


def roll_dice_faces(notation: str) -> tuple[int, list[int]]:
    # As roll_dice, also returning each die rolled (none for a flat number) -
    # e.g. "D6+2" -> (6, [4]).
    match = _DICE_PATTERN.match(notation)
    if match["flat"] is not None:
        return int(match["flat"]), []
    count = int(match["count"]) if match["count"] else 1
    die = int(match["die"])
    plus = int(match["plus"]) if match["plus"] else 0
    faces = [random.randint(1, die) for _ in range(count)]
    return sum(faces) + plus, faces


def wound_threshold(strength: int, toughness: int) -> int:
    # The wound roll needed scales with how attacker strength compares to defender
    # toughness: double (or more) strength wounds easiest, double toughness hardest.
    if strength >= 2 * toughness:
        return 2
    if strength > toughness:
        return 3
    if strength == toughness:
        return 4
    if toughness >= 2 * strength:
        return 6
    return 5


def _effective_save(model: Model) -> int:
    # A model's invulnerable save isn't worsened by AP, so it protects the model
    # whenever it's better than (lower than) the modified armor save would be.
    if model.invulnerable is not None:
        return min(model.save, model.invulnerable)
    return model.save


def _target_priority(model: Model) -> tuple[int, int]:
    # Supports and leaders are targeted last, regardless of their save. Within that
    # grouping, the worst-saving models (highest save value) are targeted first.
    is_priority_target = not (model.is_support or model.is_leader)
    return (0 if is_priority_target else 1, -_effective_save(model))


def _keyword(item) -> str:
    # Ability/stratagem rows hold Condition/Effect rows; code-defined Rules
    # hold the bare keyword strings.
    return item if isinstance(item, str) else item.keyword


def _apply_triggered_effects(
    abilities: list[WeaponAbility] | list[WargearAbility] | list[Stratagem] | list[Rule],
    context: dict,
    state: dict,
    pending: deque[dict],
) -> None:
    # Checked at every step (pre-hit/hit/wound/save): for each ability in play
    # - whether from the weapon itself or from wargear equipped on the same
    # model - if *any* of its conditions match the current step, apply *all*
    # of its effects. Unknown keywords (a condition/effect row with no matching
    # hardcoded implementation) are simply ignored.
    for ability in abilities:
        matched = any(
            CONDITIONS[_keyword(condition)](context)
            for condition in ability.conditions
            if _keyword(condition) in CONDITIONS
        )
        if not matched:
            continue
        for effect in ability.effects:
            handler = EFFECTS.get(_keyword(effect))
            if handler is not None:
                handler(state, pending)


# eq=False: targets are removed from the queue by identity, and two models
# with identical stats must not be mistaken for one another.
@dataclass(eq=False)
class _Target:
    toughness        : int
    save             : int
    invulnerable     : int | None
    feel_no_pain     : int | None
    remaining_wounds : int
    # Feel No Pain against mortal wounds only (see feel_no_pain_mortal).
    feel_no_pain_mortal: int | None = None
    # Its invulnerable save is against ranged attacks only.
    invulnerable_ranged_only: bool = False
    is_leader        : bool = False
    is_support       : bool = False
    # Rolls to explode when destroyed (a datasheet ability with the
    # deadly_demise effect, e.g. "Deadly Demise D3").
    deadly_demise    : bool = False
    # Defender rules only this model has (from a per-model detachment rule,
    # e.g. War-Form Mantles: TECH-PRIEST models have a 4+ invulnerable save),
    # applied to an attack once it's allocated to this model.
    rules            : tuple = ()


def _precision_target(targets: deque[_Target]) -> _Target:
    # Precision picks leaders first, then supports, then everything else -
    # within each group, the queue's existing order (worst save first) holds.
    return min(
        targets,
        key=lambda target: 0 if target.is_leader else 1 if target.is_support else 2,
    )


@dataclass
class WeaponCombatResult:
    # The same breakdown as CombatResult below, scoped to a single weapon
    # profile (every weapon instance sharing one name, across every model in
    # the attacking unit that fired it) rather than the whole combat.
    name             : str
    # The weapon's Damage characteristic, e.g. "D6+2".
    damage           : str       = field(default="")
    attack_rolls     : list[int] = field(default_factory=list)
    attack_rerolls   : list[int] = field(default_factory=list)
    wound_rolls      : list[int] = field(default_factory=list)
    wound_rerolls    : list[int] = field(default_factory=list)
    save_rolls       : list[int] = field(default_factory=list)
    fnp_rolls        : list[int] = field(default_factory=list)
    # The dice rolled for a random Damage characteristic (e.g. the D6 of
    # "D6+2"), for each attack that got through its save - none if it's flat.
    damage_rolls     : list[int] = field(default_factory=list)
    total_damage     : int       = field(default=0)
    models_destroyed : int       = field(default=0)
    hazardous_rolls  : list[int] = field(default_factory=list)
    hazardous_wounds : int       = field(default=0)


@dataclass
class CombatResult:
    # Raw die values (1-6) rolled at each step, in the order they were rolled,
    # rather than pass/fail counts - callers can see exactly what was rolled.
    attack_rolls               : list[int] = field(default_factory=list)
    attack_rerolls             : list[int] = field(default_factory=list)
    wound_rolls                : list[int] = field(default_factory=list)
    wound_rerolls              : list[int] = field(default_factory=list)
    save_rolls                 : list[int] = field(default_factory=list)
    # The defending models' feel no pain rolls, one per point of damage
    # against a model that has feel no pain (not the attacker's own, from
    # hazardous - those aren't recorded).
    fnp_rolls                  : list[int] = field(default_factory=list)
    total_damage               : int       = field(default=0)
    models_destroyed           : int       = field(default=0)
    defending_models_remaining : int       = field(default=0)
    # Self-inflicted hazard checks made by the attacking unit (one per
    # hazardous weapon fired), and the total wounds they dealt after FNP.
    hazardous_rolls: list[int] = field(default_factory=list)
    hazardous_wounds: int = field(default=0)
    # How many attacking models were destroyed outright by their own
    # hazardous wounds (checked once a model is done firing all its weapons).
    hazardous_models_destroyed: int = field(default=0)
    # Deadly Demise: one D6 per destroyed defending model that has it; a 6
    # means it explodes. (The explosion's mortal wounds aren't resolved.)
    deadly_demise_rolls: list[int] = field(default_factory=list)
    deadly_demise_explosions: int = field(default=0)
    # The same totals above, broken down per weapon profile (grouped by
    # weapon name) instead of pooled across the whole attacking unit.
    weapon_results: list[WeaponCombatResult] = field(default_factory=list)


def resolve_combat(
    attacker: Unit,
    defender: Unit,
    selected_weapon_ids: set[int],
    in_engagement_range: bool,
    visible: bool,
    in_range: bool,
    in_cover: bool,
    half_range: bool,
    moved_less_than_3: bool,
    advanced: bool,
    stratagems: list[Stratagem] | None = None,
    defender_stratagems: list[Stratagem] | None = None,
    apply_precision: bool = False,
    attacker_rules: list[Rule] | None = None,
    defender_rules: list[Rule] | None = None,
    attacker_options: set[str] | None = None,
    attacker_extra_keywords: set[str] | None = None,
    defender_extra_keywords: set[str] | None = None,
    attacker_detachment_rules: list[DetachmentRule] | None = None,
    defender_detachment_rules: list[DetachmentRule] | None = None,
    ability_rules: dict[str, list[Rule]] | None = None,
    attacker_positions: set[str] | None = None,
    defender_positions: set[str] | None = None,
    charged: bool = False,
    defender_battle_shocked: bool = False,
    attacker_damaged: bool = False,
) -> CombatResult:
    # The defending unit is a queue of individual models, each with its own wound pool.
    # Each attack targets whichever model is at the front of the queue; once that
    # model is destroyed it's popped, and the *next* attack targets the model now
    # at the front - a single attack's damage never spills onto a second model.
    # The queue is pre-sorted so supports/leaders die last, and otherwise worst
    # saves (including invulnerable) die before better ones.
    ordered_unit_models = sorted(
        defender.unit_models, key=lambda unit_model: _target_priority(unit_model.model)
    )
    # The full set of keywords across every model in the defending unit's
    # original composition - used by conditions like "target has INFANTRY"
    # (e.g. for Anti-Infantry/Anti-Vehicle), independent of casualties so far.
    # (Each model's keywords include any its unit's enhancements give it.)
    defender_keywords = {
        keyword
        for unit_model in defender.unit_models
        for keyword in enhancement_rules.model_keywords(defender, unit_model)
    } | set(defender_extra_keywords or ())
    # The same keywords, but kept per defending model - e.g. to tell a
    # CHARACTER leading a unit apart from a CHARACTER on its own.
    defender_model_keywords = [
        frozenset(enhancement_rules.model_keywords(defender, unit_model))
        for unit_model in defender.unit_models
    ]
    # Likewise for the attacking unit - e.g. for "if this unit has BATTLELINE".
    # Either side can also have keywords granted by a rule option (e.g. Mantra
    # of Discipline's BATTLELINE).
    attacker_keywords = {
        keyword
        for unit_model in attacker.unit_models
        for keyword in enhancement_rules.model_keywords(attacker, unit_model)
    } | set(attacker_extra_keywords or ())
    # ...and per attacking model, e.g. for "while a CHARACTER model is leading
    # this unit".
    attacker_unit_model_keywords = [
        frozenset(enhancement_rules.model_keywords(attacker, unit_model))
        for unit_model in attacker.unit_models
    ]

    # Code-defined rules (e.g. an active Doctrina Imperative) from faction
    # abilities: the attacking unit's own "attacker" rules are in play like
    # stratagems; the defending unit's "defender" rules are in play for every
    # weapon too, modifying the attacks made against it.
    attacker_rules = [r for r in attacker_rules or [] if r.side == "attacker"]
    defender_rules = [r for r in defender_rules or [] if r.side == "defender"]

    # Stratagems used on the attacking unit. One with keyword requirements
    # (e.g. Epic Challenge's CHARACTER) or exclusions only applies to the
    # attacks of models that have all the required keywords and none of the
    # excluded ones; one without either applies to every model, and also to
    # the unit-wide check below.
    stratagems = list(stratagems or [])
    # Stratagems the defender used on its unit: like the defender's rules,
    # they're in play for every weapon, modifying the attacks against it.
    defender_stratagems = list(defender_stratagems or [])
    # A stratagem used on the attacking unit that protects it (e.g. Feel No
    # Pain) protects that unit, not the targets of its attacks - so attacks
    # only get its other effects, and its protective ones are kept for the
    # unit itself (see OWN_UNIT_EFFECTS).
    def attack_effects(stratagem: Stratagem) -> SimpleNamespace:
        return SimpleNamespace(
            conditions=stratagem.conditions,
            effects=[e for e in stratagem.effects if _keyword(e) not in OWN_UNIT_EFFECTS],
        )

    def own_unit_effects(stratagem: Stratagem) -> SimpleNamespace:
        return SimpleNamespace(
            conditions=stratagem.conditions,
            effects=[e for e in stratagem.effects if _keyword(e) in OWN_UNIT_EFFECTS],
        )

    unrestricted_stratagems = [attack_effects(s) for s in stratagems if s.is_unrestricted]

    def stratagems_for(unit_model) -> list[Stratagem]:
        keywords = enhancement_rules.model_keywords(attacker, unit_model)
        return [s for s in stratagems if s.applies_to(keywords)]

    # Some wargear/datasheet abilities apply to the whole attacking unit rather
    # than just the model carrying them (e.g. a datasheet ability granting the
    # unit a reroll) - checked once, across
    # every model's wargear and datasheet abilities, regardless of which
    # weapon is firing.
    unit_wide_state: dict = {}
    # Datasheet abilities belong to the unit, so (unlike wargear) they're also
    # in play for every weapon any of its models fires - e.g. "this unit's
    # ranged attacks have [SUSTAINED HITS 1]".
    # Enhancements, upgrades and the rules of the attacking list's detachments
    # can grant the unit more. (Abilities with
    # code-defined rules, like Stealth giving the benefit of cover when the
    # unit is the target, come in through attacker_rules/defender_rules.)
    datasheet_abilities = [
        ability
        for unit_model in attacker.unit_models
        for ability in unit_model.model.abilities
    ] + enhancement_rules.granted_datasheet_abilities(attacker)
    attacker_detachment_rules = list(attacker_detachment_rules or [])
    datasheet_abilities += detachment_rule_service.granted_datasheet_abilities(
        attacker_detachment_rules, attacker
    )
    # Code-defined rules by datasheet ability name (e.g. War-Form Mantle's),
    # for abilities a per-model detachment rule gives single models.
    ability_rules = ability_rules or {}

    def model_abilities(rules: list[DetachmentRule], keywords: set[str], side: str) -> list:
        # The datasheet abilities a per-model detachment rule gives a model with
        # these keywords, and their code-defined rules for `side`.
        abilities = detachment_rule_service.model_datasheet_abilities(rules, keywords)
        return abilities + [
            rule
            for ability in abilities
            for rule in ability_rules.get(ability.name, [])
            if rule.side == side
        ]
    # Names of the faction-ability rule options active for the attacking unit
    # (e.g. "Riled Up"), for conditions like "if this unit is riled up".
    attacker_options = set(attacker_options or ())
    # Where each unit is that the calculator can't work out itself (see
    # app/combat_rules/positions.py), e.g. within 6" of a BATTLELINE unit.
    attacker_positions = set(attacker_positions or ())
    defender_positions = set(defender_positions or ())
    # A unit that Remained Stationary moved less than 3" (e.g. for [HEAVY]).
    moved_less_than_3 = moved_less_than_3 or "remained_stationary" in attacker_positions
    all_unit_wide_abilities = [
        ability
        for unit_model in attacker.unit_models
        for gear in unit_model.wargear
        for ability in gear.abilities
    ] + datasheet_abilities + unrestricted_stratagems + attacker_rules
    _apply_triggered_effects(
        all_unit_wide_abilities,
        {
            "step": "unit_wide",
            "defender_keywords": defender_keywords,
            "attacker_keywords": attacker_keywords,
            "attacker_unit_model_keywords": attacker_unit_model_keywords,
            "attacker_options": attacker_options,
            "defender_model_keywords": defender_model_keywords,
            "attacker_positions": attacker_positions,
            "defender_positions": defender_positions,
            "charged": charged,
            "defender_battle_shocked": defender_battle_shocked,
            "attacker_damaged": attacker_damaged,
        },
        unit_wide_state,
        deque(),
    )
    unit_rerolls_failed_hits = unit_wide_state.get("reroll_failed_hits", False)

    def model_state(unit_model) -> dict:
        # What the defender's rules do for one of its models in particular -
        # e.g. the Aegis Protocol's +1 Toughness for KASTELAN ROBOT models, or
        # Robotic Bodyguard's Feel No Pain 4+ for the Datasmith leading them.
        state: dict = {}
        _apply_triggered_effects(
            defender_rules,
            {
                "step": "target_model",
                "target_model_keywords": enhancement_rules.model_keywords(defender, unit_model),
                "defender_keywords": defender_keywords,
                "defender_model_keywords": defender_model_keywords,
            },
            state,
            deque(),
        )
        return state

    model_states = {id(unit_model): model_state(unit_model) for unit_model in ordered_unit_models}
    targets: deque[_Target] = deque(
        _Target(
            toughness=unit_model.model.toughness
            + (1 if model_states[id(unit_model)].get("plus_one_toughness") else 0),
            save=unit_model.model.save,
            invulnerable=unit_model.model.invulnerable,
            feel_no_pain=min(
                (
                    fnp
                    for fnp in (
                        unit_model.model.feel_no_pain,
                        model_states[id(unit_model)].get("feel_no_pain"),
                    )
                    if fnp is not None
                ),
                default=None,
            ),
            feel_no_pain_mortal=unit_model.model.feel_no_pain_mortal,
            invulnerable_ranged_only=unit_model.model.invulnerable_ranged_only,
            remaining_wounds=unit_model.model.wounds,
            is_leader=bool(unit_model.model.is_leader),
            is_support=bool(unit_model.model.is_support),
            deadly_demise=any(
                effect.keyword == "deadly_demise"
                for ability in unit_model.model.abilities
                for effect in ability.effects
            ),
            rules=tuple(
                ability
                for ability in model_abilities(
                    list(defender_detachment_rules or []),
                    enhancement_rules.model_keywords(defender, unit_model),
                    "defender",
                )
                if isinstance(ability, Rule)
            ),
        )
        for unit_model in ordered_unit_models
    )

    result = CombatResult()
    # Accumulates the same breakdown as `result`, but bucketed per weapon name
    # - every weapon instance sharing a name (e.g. five models each carrying
    # their own "Boltgun") feeds into the same bucket. Built up alongside the
    # pooled totals below, then flattened onto result.weapon_results at the end.
    weapon_results_by_name: dict[str, WeaponCombatResult] = {}

    # Every attack the unit makes, queued per weapon profile (every weapon
    # sharing a name, across every model firing one - e.g. all ten Galvanic
    # rifles) as (attack state, the weapon instance it came from) pairs.
    # Profiles are then resolved one at a time, in phases, like at the table:
    # all hit rolls, then all wound rolls, then saves and damage.
    profiles: dict[str, list[tuple[dict, dict]]] = {}

    # A unit that can't see its target makes no attacks at all - this is checked
    # once for the whole attacking unit, since visibility is a property of the
    # engagement as a whole, not of any one model within it.
    if visible:
        for unit_model in attacker.unit_models:
            # Range, by contrast, is checked per attacking model: models within the
            # same unit can be spread out, so one model being out of range doesn't
            # stop the rest of the unit from attacking.
            if not in_range:
                continue

            # Abilities on wargear equipped by this model are in play for every
            # weapon it fires, same as the weapon's own abilities - and so are
            # those on wargear another model in the unit has, if it reaches the
            # bearer's unit (e.g. an Omnispex).
            wargear_abilities = [
                ability
                for other in attacker.unit_models
                for gear in other.wargear
                if other is unit_model or gear.scope == "bearers_unit"
                for ability in gear.abilities
            ]
            own_stratagems = stratagems_for(unit_model)
            model_stratagems = [attack_effects(s) for s in own_stratagems]
            # This model's own Feel No Pain against mortal wounds (e.g. from a
            # Hazardous weapon): the best of its Feel No Pain, its Feel No Pain
            # against mortal wounds, and any its stratagems give it.
            own_state: dict = {}
            _apply_triggered_effects(
                [own_unit_effects(s) for s in own_stratagems],
                {"step": "own_unit"},
                own_state,
                deque(),
            )
            shooter_fnp = min(
                (
                    fnp
                    for fnp in (
                        unit_model.model.feel_no_pain,
                        unit_model.model.feel_no_pain_mortal,
                        own_state.get("feel_no_pain"),
                        own_state.get("feel_no_pain_mortal"),
                    )
                    if fnp is not None
                ),
                default=None,
            )
            # Weapon abilities this model's weapons gain from enhancements,
            # upgrades and detachment rules (e.g. [SUSTAINED HITS 1] on ranged
            # weapons), each limited to a weapon type or not.
            granted_weapon_abilities = enhancement_rules.granted_weapon_abilities(
                attacker, unit_model
            ) + detachment_rule_service.granted_weapon_abilities(
                attacker_detachment_rules, attacker, unit_model
            )
            # What a per-model detachment rule gives this model alone.
            model_rule_abilities = model_abilities(
                attacker_detachment_rules,
                enhancement_rules.model_keywords(attacker, unit_model),
                "attacker",
            )

            # Hazardous wounds taken by this model accumulate across every one
            # of its weapons, in case more than one is hazardous - checked
            # against its own wounds once it's done firing (see below).
            model_hazardous_damage = 0

            # Its own weapons, and any its enhancement gives it (e.g. TL-4Ø9).
            for weapon in list(unit_model.weapons) + enhancement_rules.granted_weapons(unit_model):
                # Only weapons the caller chose to fire/swing with this attack count.
                if weapon.id not in selected_weapon_ids:
                    continue

                is_ranged = weapon.weapon_type != "melee"
                weapon_type = "ranged" if is_ranged else "melee"
                # Each distinct ability once - e.g. a datasheet ability every model
                # in the unit has is still one rule - so effects that count their
                # sources (like +1 to hit) aren't multiplied by model count.
                abilities = list(
                    {
                        id(ability): ability
                        for ability in (
                            list(weapon.abilities)
                            + [
                                ability
                                for ability, only in granted_weapon_abilities
                                if only in (None, weapon_type)
                            ]
                            + wargear_abilities
                            + datasheet_abilities
                            + model_rule_abilities
                            + model_stratagems
                            + attacker_rules
                            + defender_rules
                            + defender_stratagems
                        )
                    }.values()
                )
                # Shared by every step's context for this weapon.
                weapon_context = {
                    "is_ranged": is_ranged,
                    # e.g. for "your unit's Tesla Sphere weapons".
                    "weapon_name": weapon.name,
                    "defender_keywords": defender_keywords,
                    "attacker_keywords": attacker_keywords,
                    "attacker_unit_model_keywords": attacker_unit_model_keywords,
                    "attacker_options": attacker_options,
                    "defender_model_keywords": defender_model_keywords,
                    "attacker_positions": attacker_positions,
                    "defender_positions": defender_positions,
                    "charged": charged,
                    "defender_battle_shocked": defender_battle_shocked,
                    "attacker_damaged": attacker_damaged,
                    # The firing model's own keywords - e.g. for "weapons
                    # equipped by KASTELAN ROBOT models".
                    "attacker_model_keywords": enhancement_rules.model_keywords(
                        attacker, unit_model
                    ),
                }

                # Weapon eligibility: a static, no-dice-rolled check of this
                # weapon's own abilities (Assault/Pistol) run before deciding
                # whether it can fire at all this call, since both can
                # override the engagement-range/advance restrictions below.
                eligibility_state: dict = {}
                _apply_triggered_effects(
                    abilities,
                    {"step": "weapon_eligibility", **weapon_context},
                    eligibility_state,
                    deque(),
                )

                # A weapon restricted to certain targets (e.g. a HUNTER
                # profile) that can't attack this one doesn't attack at all.
                if eligibility_state.get("cannot_attack"):
                    continue

                # Being in engagement range normally swaps which weapons are
                # usable: melee weapons fight instead of ranged weapons
                # shooting - Pistol is the one exception, letting a ranged
                # weapon fire while its bearer is in engagement range without
                # becoming a melee weapon.
                if is_ranged == in_engagement_range:
                    if not (
                        is_ranged and in_engagement_range and eligibility_state.get("pistol")
                    ):
                        continue

                # A unit that advanced can't shoot with ranged weapons this
                # turn, unless the weapon has Assault.
                if (
                    advanced
                    and is_ranged
                    and not in_engagement_range
                    and not eligibility_state.get("assault")
                ):
                    continue

                weapon_result = weapon_results_by_name.setdefault(
                    weapon.name, WeaponCombatResult(name=weapon.name, damage=weapon.damage)
                )
                fired = {
                    "weapon": weapon,
                    "abilities": abilities,
                    "context": weapon_context,
                    "is_ranged": is_ranged,
                    # Precision only changes targeting when the attacker opts in.
                    "uses_precision": apply_precision and eligibility_state.get("precision", False),
                    "result": weapon_result,
                }

                # Attacks characteristic: how many attacks this weapon makes,
                # rolled once per weapon (flat or dice notation, e.g. "2", "D3", "2D6").
                pending_attacks: deque[dict] = deque(
                    {"auto_hit": False} for _ in range(roll_dice(weapon.attacks))
                )

                # Pre-weapon: checked once per weapon (not per individual attack),
                # for traits that apply to the whole shooting sequence rather than
                # any one attack - e.g. Rapid Fire adding attacks to the queue when
                # within half range, or Hazardous risking a self-inflicted wound.
                pre_weapon_state: dict = {}
                _apply_triggered_effects(
                    abilities,
                    {"step": "pre_weapon", "half_range": half_range, **weapon_context},
                    pre_weapon_state,
                    pending_attacks,
                )
                # Melta: extra damage on every attack this weapon makes.
                fired["damage_bonus"] = pre_weapon_state.get("melta", 0)
                if pre_weapon_state.get("blast"):
                    # Blast: +1 attack for every five models in the target unit
                    # (counted when targets are declared, before any attacks
                    # resolve), rounding down.
                    for _ in range(len(targets) // 5):
                        pending_attacks.append({"auto_hit": False})
                if pre_weapon_state.get("torrent"):
                    # Torrent: every attack hits automatically.
                    for pending_attack in pending_attacks:
                        pending_attack["auto_hit"] = True
                if pre_weapon_state.get("hazardous"):
                    # Hazard roll: a 1-2 means the firing model takes mortal
                    # wounds based on its own keywords, reduced by its own feel
                    # no pain (against mortal wounds - see shooter_fnp).
                    hazard_roll = random.randint(1, 6)
                    result.hazardous_rolls.append(hazard_roll)
                    weapon_result.hazardous_rolls.append(hazard_roll)
                    if hazard_roll <= 2:
                        shooter_keywords = enhancement_rules.model_keywords(attacker, unit_model)
                        if "VEHICLE" in shooter_keywords:
                            self_wounds = 3
                        elif "INFANTRY" in shooter_keywords:
                            self_wounds = 1
                        else:
                            self_wounds = 0
                        for _ in range(self_wounds):
                            if shooter_fnp is not None and random.randint(1, 6) >= shooter_fnp:
                                continue  # feel no pain negated this point of damage
                            result.hazardous_wounds += 1
                            weapon_result.hazardous_wounds += 1
                            model_hazardous_damage += 1

                profiles.setdefault(weapon.name, []).extend(
                    (attack, fired) for attack in pending_attacks
                )

            # End of combat for this attacking model: if the hazardous wounds it
            # took while firing added up to (or past) its own wounds, it died.
            if model_hazardous_damage >= unit_model.model.wounds:
                result.hazardous_models_destroyed += 1

    def target_for(fired: dict) -> _Target:
        # The model an attack is allocated to: whoever is at the front of the
        # queue, or a Precision weapon's pick.
        return _precision_target(targets) if fired["uses_precision"] else targets[0]

    for profile_attacks in profiles.values():
        # Hit phase: every attack of this profile rolls to hit. Extra attacks
        # and hits an effect adds (e.g. Sustained Hits) join the same phase -
        # an extra hit is already a hit, so it skips the roll.
        successful_hits: list[tuple[dict, dict]] = []
        queue = deque(profile_attacks)
        while queue:
            attack, fired = queue.popleft()
            if attack["auto_hit"]:
                successful_hits.append((attack, fired))
                continue
            weapon = fired["weapon"]
            abilities = fired["abilities"]
            weapon_context = fired["context"]
            is_ranged = fired["is_ranged"]
            weapon_result = fired["result"]
            spawned: deque[dict] = deque()

            # Pre-hit: lets a static trait (e.g. "always ignore cover", or Heavy
            # when the unit moved less than 3") mark this attack before the hit
            # roll's threshold is set.
            _apply_triggered_effects(
                abilities,
                {
                    "step": "pre_hit",
                    "moved_less_than_3": moved_less_than_3,
                    "half_range": half_range,
                    **weapon_context,
                },
                attack,
                spawned,
            )
            # Hit roll modifiers: every +1 and -1 to hit adds up, then the total
            # is capped at +1/-1 - so +2 and -1 is still +1. A ranged attack
            # against a target in cover counts as a -1, unless this attack (or
            # the whole unit) ignores cover.
            # An attack that ignores penalties to its Hit roll (e.g. Molecular
            # Targeting) keeps only the bonuses.
            ignore_penalties = attack.get("ignore_hit_penalties", False)
            hit_modifier = attack.get("plus_one_to_hit", 0) - (
                0 if ignore_penalties else attack.get("minus_one_to_hit", 0)
            )
            # [HEAVY] is one +1, however many sources grant it.
            if attack.get("heavy"):
                hit_modifier += 1
            if (
                (in_cover or attack.get("benefit_of_cover"))
                and is_ranged
                and not attack.get("ignore_cover")
                and not ignore_penalties
            ):
                hit_modifier -= 1
            hit_modifier = max(-1, min(1, hit_modifier))
            # Setting the characteristic (e.g. "a Ballistic Skill of 3+") comes
            # before any modifiers or improvements.
            skill = 3 if is_ranged and attack.get("ranged_skill_3") else weapon.skill
            effective_skill = skill - hit_modifier
            # Improving the BS/WS characteristic itself (e.g. a Doctrina
            # Imperative) isn't a hit roll modifier, so it's outside the cap.
            if is_ranged and attack.get("plus_one_skill_ranged"):
                effective_skill -= 1
            if not is_ranged and attack.get("plus_one_skill_melee"):
                effective_skill -= 1

            # The unmodified roll that scores a Critical Hit: a 6, or lower for
            # some attacks (e.g. Enslaved Artifice's 5+).
            critical_hit_on = attack.get("critical_hit_on", 6)
            hit_context = {"critical_hit_on": critical_hit_on, **weapon_context}

            def hits(roll: int) -> bool:
                # A Critical Hit always hits and a 1 always fails, whatever the
                # modifiers.
                return roll != 1 and (roll >= critical_hit_on or roll >= effective_skill)

            # Hit roll: succeeds (hits) on a roll equal to or greater than skill.
            hit_roll = random.randint(1, 6)
            result.attack_rolls.append(hit_roll)
            weapon_result.attack_rolls.append(hit_roll)
            _apply_triggered_effects(
                abilities, {"step": "hit", "roll": hit_roll, **hit_context}, attack, spawned
            )
            if not hits(hit_roll) and (
                attack.get("reroll_failed_hits")
                or unit_rerolls_failed_hits
                or (hit_roll == 1 and attack.get("reroll_hit_ones"))
            ):
                # Re-roll a failed hit (or just a 1) once, replacing the
                # original result - hit-step triggers (e.g. Sustained Hits)
                # are re-checked against the new roll too.
                hit_roll = random.randint(1, 6)
                result.attack_rerolls.append(hit_roll)
                weapon_result.attack_rerolls.append(hit_roll)
                _apply_triggered_effects(
                    abilities, {"step": "hit", "roll": hit_roll, **hit_context}, attack, spawned
                )
            queue.extend((extra, fired) for extra in spawned)
            if hits(hit_roll):
                successful_hits.append((attack, fired))

        # Wound phase: every hit rolls to wound. Nothing has been destroyed yet
        # this phase, so each wound roll is against the Toughness of the model
        # its attack will be allocated to first.
        if not targets:
            continue  # the defending unit was wiped out by an earlier profile
        wounds: list[tuple[dict, dict]] = []
        for attack, fired in successful_hits:
            weapon = fired["weapon"]
            abilities = fired["abilities"]
            weapon_context = fired["context"]
            weapon_result = fired["result"]
            strength = (
                weapon.strength
                + (1 if attack.get("plus_one_strength") else 0)
                + (2 if attack.get("plus_two_strength") else 0)
            )
            toughness = target_for(fired).toughness
            threshold = wound_threshold(strength, toughness)
            # The wound step's checks can compare the two (e.g. "if the
            # Strength of that attack is greater than the Toughness").
            wound_context = {"strength": strength, "toughness": toughness, **weapon_context}

            if attack.get("auto_pass_wound"):
                wound_passed = True
            else:
                wound_passed = False
                # A failed wound roll may be re-rolled once (e.g. Twin-linked,
                # or just a 1), with the wound-step triggers re-checked against
                # the new roll.
                wound_roll = None
                for is_reroll in (False, True):
                    if is_reroll and not (
                        attack.get("reroll_failed_wounds")
                        or (wound_roll == 1 and attack.get("reroll_wound_ones"))
                    ):
                        break
                    wound_roll = random.randint(1, 6)
                    if is_reroll:
                        result.wound_rerolls.append(wound_roll)
                        weapon_result.wound_rerolls.append(wound_roll)
                    else:
                        result.wound_rolls.append(wound_roll)
                        weapon_result.wound_rolls.append(wound_roll)
                    _apply_triggered_effects(
                        abilities,
                        {"step": "wound", "roll": wound_roll, **wound_context},
                        attack,
                        deque(),
                    )
                    if attack.get("critical_wound"):
                        # An Anti-X-style ability (e.g. Anti-Infantry 4+) matched
                        # this roll against the defending unit's keywords - it
                        # counts as a critical wound regardless of the actual
                        # roll, so re-run the wound-step trigger check with a
                        # synthetic natural-6 context to also fire any other
                        # critical-wound-dependent effects (e.g. Devastating
                        # Wounds), same as an actual natural 6 would.
                        _apply_triggered_effects(
                            abilities,
                            {"step": "wound", "roll": 6, **wound_context},
                            attack,
                            deque(),
                        )
                        wound_passed = True
                    else:
                        # An unmodified 6 always wounds and a 1 always fails,
                        # whatever the modifiers. A +1 and a -1 to wound
                        # cancel out.
                        # (An attack that ignores penalties to its Wound roll,
                        # e.g. Molecular Targeting, ignores a -1.)
                        needed = (
                            threshold
                            + (
                                1
                                if attack.get("minus_one_to_wound")
                                and not attack.get("ignore_wound_penalties")
                                else 0
                            )
                            - (1 if attack.get("plus_one_to_wound") else 0)
                        )
                        wound_passed = wound_roll != 1 and (
                            wound_roll == 6 or wound_roll >= needed
                        )
                    if wound_passed:
                        break
            if wound_passed:
                wounds.append((attack, fired))

        # Saves and damage: each wound is allocated to a model and resolved in
        # turn - its save is rolled against the model it's allocated to, which
        # can change as earlier wounds destroy models.
        for attack, fired in wounds:
            if not targets:
                break  # defending unit has no models left
            weapon = fired["weapon"]
            abilities = fired["abilities"]
            weapon_context = fired["context"]
            weapon_result = fired["result"]
            target = target_for(fired)
            if target.rules:
                # Rules only the model it's allocated to has (e.g. a
                # TECH-PRIEST's 4+ invulnerable save) apply to this attack from
                # here on - its save and damage.
                attack = dict(attack)
                _apply_triggered_effects(
                    target.rules, {"step": "allocated", **weapon_context}, attack, deque()
                )

            # Save roll: armor save is worsened by the weapon's AP, but the
            # defender may use their invulnerable save instead if it's better.
            # An effect (e.g. devastating wounds) can mark this attack to skip
            # the roll entirely - no save of any kind, armor or invulnerable.
            if attack.get("no_save"):
                save_passed = False
            else:
                ap = weapon.ap - 1 if attack.get("improve_ap") else weapon.ap
                if attack.get("worsen_ap"):
                    ap = min(0, ap + 1)
                save_needed = target.save - ap
                # (A ranged-only invulnerable save, e.g. an ion shield, doesn't
                # help against melee attacks.)
                if target.invulnerable is not None and (
                    fired["is_ranged"] or not target.invulnerable_ranged_only
                ):
                    save_needed = min(save_needed, target.invulnerable)
                # An invulnerable save granted by a rule (e.g. Waaagh!'s 5+ while
                # riled up) - also unaffected by AP.
                if attack.get("invulnerable_save") is not None:
                    save_needed = min(save_needed, attack["invulnerable_save"])
                save_roll = random.randint(1, 6)
                result.save_rolls.append(save_roll)
                weapon_result.save_rolls.append(save_roll)
                _apply_triggered_effects(
                    abilities,
                    {"step": "save", "roll": save_roll, **weapon_context},
                    attack,
                    deque(),
                )
                save_passed = save_roll >= save_needed
            if save_passed:
                continue  # save succeeded - no damage from this attack

            # Damage roll: how many wounds this one failed save inflicts, plus any
            # bonus for the weapon (e.g. Melta within half range).
            rolled_damage, damage_faces = roll_dice_faces(weapon.damage)
            weapon_result.damage_rolls.extend(damage_faces)
            damage = (
                rolled_damage
                + fired["damage_bonus"]
                + (1 if attack.get("plus_one_damage") else 0)
            )
            # e.g. Nanoassembly Protocols: -1 Damage, to a minimum of 1.
            if attack.get("minus_one_damage"):
                damage = max(1, damage - 1)

            # Apply damage a single point at a time, each rolling feel no pain
            # separately, against the one model this attack is allocated to. If
            # that model dies partway through, this attack's remaining damage is
            # wasted rather than carrying onto the next model.
            # The model's own feel no pain, or a better one granted by a rule
            # (e.g. a leader's Lord of the Machine Cult). An attack that allows
            # no save (e.g. Devastating Wounds) inflicts mortal wounds, so a
            # Feel No Pain against mortal wounds counts too, if it's better.
            fnps = [target.feel_no_pain, attack.get("feel_no_pain")]
            if attack.get("no_save"):
                fnps += [target.feel_no_pain_mortal, attack.get("feel_no_pain_mortal")]
            feel_no_pain = min((fnp for fnp in fnps if fnp is not None), default=None)
            for _ in range(damage):
                if feel_no_pain is not None:
                    fnp_roll = random.randint(1, 6)
                    result.fnp_rolls.append(fnp_roll)
                    weapon_result.fnp_rolls.append(fnp_roll)
                    if fnp_roll >= feel_no_pain:
                        continue  # feel no pain negated this point of damage

                result.total_damage += 1
                weapon_result.total_damage += 1
                target.remaining_wounds -= 1
                if target.remaining_wounds <= 0:
                    targets.remove(target)
                    if target.deadly_demise:
                        demise_roll = random.randint(1, 6)
                        result.deadly_demise_rolls.append(demise_roll)
                        if demise_roll == 6:
                            result.deadly_demise_explosions += 1
                    result.models_destroyed += 1
                    weapon_result.models_destroyed += 1
                    break  # this model is destroyed - no spillover to the next

    result.defending_models_remaining = len(targets)
    result.weapon_results = list(weapon_results_by_name.values())
    return result
