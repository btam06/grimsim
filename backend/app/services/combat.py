from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from types import SimpleNamespace

from app.combat_rules import CONDITIONS, EFFECTS, Rule
from app.combat_rules.conditions import TARGET_ENGAGED, WITHIN_12_OF_TARGET
from app.combat_rules.effects import OWN_UNIT_EFFECTS
from app.models import DetachmentRule, Model, Stratagem, Unit, WargearAbility, WeaponAbility
from app.services import dice
from app.services.list_building import detachment_rules as detachment_rule_service
from app.services.list_building import enhancements as enhancement_rules

_DICE_PATTERN = re.compile(
    r"^(?:(?P<flat>[0-9]+)|(?P<count>[0-9]*)D(?P<die>[36])(?:\+(?P<plus>[0-9]+))?)$"
)


def _replace(rolls: list[int], old: int, new: int) -> None:
    # The last roll of `old` in the list is now `new` (a changed roll).
    for i in range(len(rolls) - 1, -1, -1):
        if rolls[i] == old:
            rolls[i] = new
            return


def roll_dice(notation: str) -> int:
    # notation is either a flat number or dice notation (D3/D6/2D6/D6+1/...); roll
    # it to a value. Used for both a weapon's damage and its number of attacks.
    return roll_dice_faces(notation)[0]


def roll_dice_faces(notation: str, first: int | None = None) -> tuple[int, list[int]]:
    # As roll_dice, also returning each die rolled (none for a flat number) -
    # e.g. "D6+2" -> (6, [4]). `first`: the first die's value, instead of
    # rolling it (e.g. a Miracle dice).
    match = _DICE_PATTERN.match(notation)
    if match["flat"] is not None:
        return int(match["flat"]), []
    count = int(match["count"]) if match["count"] else 1
    die = int(match["die"])
    plus = int(match["plus"]) if match["plus"] else 0
    faces = [dice.randint(1, die) for _ in range(count - (first is not None))]
    if first is not None:
        faces.insert(0, first)
    return sum(faces) + plus, faces


def _sides(notation: str) -> int:
    # The dice rolled for it: 3 (D3s) or 6.
    match = _DICE_PATTERN.match(notation)
    return int(match["die"]) if match["die"] else 6


def random_notation(notation: str) -> bool:
    # Whether dice are rolled for it (D3, 2D6+1...), rather than a flat number.
    return _DICE_PATTERN.match(notation)["flat"] is None


def average_damage(notation: str) -> float:
    # The average of a damage roll - e.g. "D3+2" -> 4.
    match = _DICE_PATTERN.match(notation)
    if match["flat"] is not None:
        return float(match["flat"])
    count = int(match["count"]) if match["count"] else 1
    plus = int(match["plus"]) if match["plus"] else 0
    return count * (int(match["die"]) + 1) / 2 + plus


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


# The weapon ability that lets a weapon shoot targets it can't see (24.19).
INDIRECT_FIRE = "Indirect Fire"
# A Psychic Attack is one made with a [PSYCHIC] weapon.
PSYCHIC = "Psychic"
# Devastating Refrain (Exorcist): its [INDIRECT FIRE] attacks set off a
# destroyed model's Deadly Demise on this (instead of a 6).
DEVASTATING_REFRAIN = "Devastating Refrain"
DEVASTATING_REFRAIN_DEMISE = 5


def _blast(weapon) -> bool:
    # A [BLAST] weapon (Blast, Blast 2...).
    return any(a.name.startswith("Blast") for a in getattr(weapon, "abilities", []))


@dataclass(frozen=True)
class WeaponBonus:
    # Something a rule adds to one attacking model's weapons (see
    # resolve_combat weapon_bonuses): to its melee weapons (`melee_only`), or
    # its weapons named `names` (or starting with one - a profile, e.g.
    # "Lance of Illumination – strike"), or all of them. Their Attacks,
    # Strength and Damage; [DEVASTATING WOUNDS]; and a mortal wound on the
    # target each time an attack wounds, in addition to its damage
    # (`mortal_on_wound` - e.g. Rapturous Blows).
    attacks: int = 0
    strength: int = 0
    damage: int = 0
    melee_only: bool = True
    names: tuple[str, ...] = ()
    devastating: bool = False
    mortal_on_wound: bool = False

    def applies(self, weapon, is_ranged: bool) -> bool:
        if self.melee_only and is_ranged:
            return False
        return not self.names or any(weapon.name.startswith(n) for n in self.names)


# What each kind of roll's called (see resolve_combat's offer).
ROLL_NAMES = {
    "hit": "Hit roll", "wound": "Wound roll", "save": "saving throw", "damage": "Damage roll",
    "hazard": "hazard roll", "attacks": "Attacks roll",
}


def _hit_check(indirect_needs: int, critical_hit_on: int, effective_skill: int):
    # Whether a Hit roll hits: a Critical Hit always does and a 1 always
    # fails, whatever the modifiers (an indirect fire one needs at least
    # `indirect_needs`).
    def hits(roll: int) -> bool:
        if roll < indirect_needs:
            return False
        return roll != 1 and (roll >= critical_hit_on or roll >= effective_skill)

    return hits


def _wounds(attack: dict, roll: int, abilities, wound_context: dict, threshold: int) -> bool:
    # Whether a Wound roll wounds - the attack marked by the wound-step
    # triggers it sets off.
    _apply_triggered_effects(
        abilities, {"step": "wound", "roll": roll, **wound_context}, attack, deque()
    )
    if attack.get("critical_wound"):
        # An Anti-X-style ability (e.g. Anti-Infantry 4+) matched this roll
        # against the defending unit's keywords - it counts as a critical
        # wound regardless of the actual roll, so re-run the wound-step
        # trigger check with a synthetic natural-6 context to also fire any
        # other critical-wound-dependent effects (e.g. Devastating Wounds),
        # same as an actual natural 6 would.
        _apply_triggered_effects(
            abilities, {"step": "wound", "roll": 6, **wound_context}, attack, deque()
        )
        return True
    # An unmodified 6 always wounds and a 1 always fails, whatever the
    # modifiers. A +1 and a -1 to wound cancel out.
    # (An attack that ignores penalties to its Wound roll, e.g. Molecular
    # Targeting, ignores a -1.)
    needed = (
        threshold
        + (
            1
            if attack.get("minus_one_to_wound") and not attack.get("ignore_wound_penalties")
            else 0
        )
        - (1 if attack.get("plus_one_to_wound") else 0)
    )
    return roll != 1 and (roll == 6 or roll >= needed)


def _wound_die(
    attack: dict, before: dict, fired: dict, roll: int, passed: bool, wound_context: dict,
    threshold: int, rerolled: bool, rerollable: bool, result,
) -> RolledDie:
    # The attack's Wound roll, which its player can re-roll or change (see
    # resolve_combat's offer): the attack's as it was `before` it, its
    # wound-step triggers checked against the new roll.
    abilities = fired["abilities"]

    def check(value: int) -> bool:
        return _wounds(dict(before), value, abilities, wound_context, threshold)

    def give(value: int, rerolled: bool) -> None:
        attack.clear()
        attack.update(before)
        die.passed = _wounds(attack, value, abilities, wound_context, threshold)
        if rerolled:
            result.wound_rerolls.append(value)
            fired["result"].wound_rerolls.append(value)
        else:
            _replace(result.wound_rolls, die.value, value)
            _replace(fired["result"].wound_rolls, die.value, value)
        die.value, die.rerolled = value, die.rerolled or rerolled

    die = RolledDie(
        "wound", roll, fired["weapon"].name, passed, rerollable=rerollable, rerolled=rerolled,
        check=check, give=give,
    )
    return die


def hazard_failed(roll: int) -> bool:
    # A hazard roll (one D6) fails on a 1-2.
    return roll <= 2


def hazard_wounds(model_keywords: list[set[str]]) -> int:
    # The mortal wounds a unit suffers for a failed hazard roll (06.03): 3 if
    # every model in it is a MONSTER/VEHICLE, otherwise 1.
    if model_keywords and all(k & {"MONSTER", "VEHICLE"} for k in model_keywords):
        return 3
    return 1


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
    # model - if *all* of its conditions match the current step (and it has
    # at least one), apply *all* of its effects. Unknown keywords (a
    # condition/effect row with no matching hardcoded implementation) are
    # simply ignored.
    for ability in abilities:
        known = [
            CONDITIONS[_keyword(condition)]
            for condition in ability.conditions
            if _keyword(condition) in CONDITIONS
        ]
        if not known or not all(check(context) for check in known):
            continue
        for effect in ability.effects:
            handler = EFFECTS.get(_keyword(effect))
            if handler is not None:
                handler(state, pending)


def _protective(ability) -> bool:
    # Whether an ability only protects the model that has it (every effect is
    # one of OWN_UNIT_EFFECTS - e.g. an invulnerable save).
    return bool(ability.effects) and all(
        _keyword(e) in OWN_UNIT_EFFECTS for e in ability.effects
    )


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
    # Feel No Pain against Psychic Attacks only (attacks made with [PSYCHIC]
    # weapons) - e.g. a Null Rod.
    feel_no_pain_psychic: int | None = None
    # Its invulnerable save is against ranged attacks only.
    invulnerable_ranged_only: bool = False
    # An invulnerable save it has against ranged attacks only, from a rule
    # (e.g. Emanatus Force Field) - on top of its own.
    ranged_invulnerable: int | None = None
    is_leader        : bool = False
    is_support       : bool = False
    # Its W characteristic, and whether it's a CHARACTER model (for its
    # allocation group - see _Allocation).
    wounds_characteristic: int = 0
    is_character     : bool = False
    # Rolls to explode when destroyed (a datasheet ability with the
    # deadly_demise effect, e.g. "Deadly Demise D3").
    deadly_demise    : bool = False
    # -1 Damage for each attack allocated to it (e.g. Implacable Resilience).
    minus_one_damage : bool = False
    # Defender rules only this model has (from a per-model detachment rule,
    # e.g. War-Form Mantles: TECH-PRIEST models have a 4+ invulnerable save),
    # applied to an attack once it's allocated to this model.
    rules            : tuple = ()
    # Which of the defending unit's models it is.
    unit_model_id    : int | None = None


def _group_id(group: list[_Target]) -> int:
    # An allocation group is known by its first model's unit model id.
    return min(t.unit_model_id if t.unit_model_id is not None else id(t) for t in group)


def _wounded(target: _Target) -> bool:
    return target.remaining_wounds < target.wounds_characteristic


class _Allocation:
    # The defending unit's allocation groups (05.03), in allocation order:
    # one group for each CHARACTER model, and one for all other models with the
    # same W, Sv and InSv (against these attacks - `ranged` or not: e.g. a
    # model with Emanatus Force Field's 4+ against ranged attacks is in a
    # group of its own). A non-CHARACTER group with a wounded model is first,
    # CHARACTER groups last (wounded ones before the rest); otherwise in the
    # defender's `order` (group ids - see _group_id), or with the best
    # protected first. Attacks are allocated to the current group - the first
    # with models left - each to a wounded model in it if there is one.

    def __init__(self, targets: deque[_Target], order: list[int] | None, ranged: bool = True):
        groups: dict[tuple, list[_Target]] = {}
        for t in targets:
            key = (
                ("character", id(t))
                if t.is_character
                else ("group", t.wounds_characteristic, t.save, _invulnerable_of(t, ranged))
            )
            groups.setdefault(key, []).append(t)
        preference = {group_id: i for i, group_id in enumerate(order or [])}

        def rank(group: list[_Target]) -> tuple:
            return (
                not any(_wounded(t) for t in group),
                preference.get(_group_id(group), len(preference)),
                # The best save first - and of equal ones, the better
                # invulnerable save (it beats AP).
                min(_effective_save_of(t, ranged) for t in group),
                min(_invulnerable_of(t, ranged) or 7 for t in group),
            )

        regular = sorted((g for g in groups.values() if not g[0].is_character), key=rank)
        characters = sorted((g for g in groups.values() if g[0].is_character), key=rank)
        self.groups = regular + characters
        self.targets = targets

    def _alive(self, group: list[_Target]) -> list[_Target]:
        return [t for t in group if t in self.targets]

    def current(self, precision: bool = False) -> _Target:
        # The model the next attack is allocated to. With Precision, the
        # first CHARACTER group with models left is the current one instead.
        groups = [g for g in (self._alive(g) for g in self.groups) if g]
        if precision:
            groups = [g for g in groups if g[0].is_character] or groups
        group = groups[0]
        return next((t for t in group if _wounded(t)), group[0])


@dataclass
class AllocationGroup:
    # One of a unit's allocation groups (05.03), for its player to order: its
    # id, models, and whether it's a CHARACTER's or has a wounded model (the
    # rules fix where those go).
    id: int
    unit_model_ids: list[int]
    character: bool
    wounded: bool


def allocation_groups(unit: Unit, wounds: dict[int, int] | None = None) -> list[AllocationGroup]:
    # The unit's allocation groups in their default order (the best protected
    # first) - only its models with wounds left, if `wounds` ({unit model id:
    # wounds left}) is given.
    targets = deque(
        _Target(
            toughness=m.model.toughness, save=m.save, invulnerable=m.model.invulnerable,
            feel_no_pain=None,
            remaining_wounds=m.wounds if wounds is None else wounds[m.id],
            unit_model_id=m.id, wounds_characteristic=m.wounds,
            is_character=bool(m.model.is_leader)
            or "CHARACTER" in enhancement_rules.model_keywords(unit, m),
        )
        for m in unit.unit_models
        if wounds is None or m.id in wounds
    )
    return [
        AllocationGroup(
            id=_group_id(group),
            unit_model_ids=[t.unit_model_id for t in group],
            character=group[0].is_character,
            wounded=any(_wounded(t) for t in group),
        )
        for group in _Allocation(targets, None).groups
    ]


def _invulnerable_of(target: _Target, ranged: bool = True) -> int | None:
    # Its best invulnerable save against ranged attacks, or melee ones.
    found = [
        save
        for save, applies in (
            (target.invulnerable, ranged or not target.invulnerable_ranged_only),
            (target.ranged_invulnerable, ranged),
        )
        if save is not None and applies
    ]
    return min(found, default=None)


def _effective_save_of(target: _Target, ranged: bool = True) -> int:
    invulnerable = _invulnerable_of(target, ranged)
    return min(target.save, invulnerable) if invulnerable is not None else target.save


def _mortal_wound_target(targets: deque[_Target]) -> _Target:
    # Who suffers the next mortal wound (06.02): a wounded non-CHARACTER
    # model, then any non-CHARACTER model, then a wounded CHARACTER, then any.
    def rank(t: _Target) -> tuple:
        return (t.is_character, not _wounded(t))

    return min(targets, key=rank)


@dataclass
class RolledDie:
    # A dice rolled as an attack's made - one of a weapon's Hit, Wound or
    # saving throws, rolled together - that a player could re-roll or change
    # once they're all rolled (in a game - see
    # app/services/in_game/attack_decisions.py Decisions.dice). A dice is
    # never re-rolled twice: one re-rolled already (by any rule - e.g.
    # Twin-linked, re-rolling 1s) isn't offered again.
    kind: str
    value: int
    weapon_name: str
    # Whether it succeeds with its value now.
    passed: bool
    # (False: a Miracle dice, or a roll nothing can re-roll - e.g. an
    # indirect fire Hit roll.)
    rerollable: bool = True
    rerolled: bool = False
    # Whether it'd succeed with a value (e.g. Artisan's 6), and gives it one
    # (re-rolled, or changed) - the rules its roll triggers checked again.
    check: object = None
    give: object = None
    # (A D3's re-rolled as a D3.)
    sides: int = 6

    def offerable(self) -> bool:
        # A failed roll that can still be re-rolled.
        return self.rerollable and not self.rerolled and not self.passed


@dataclass
class WeaponCombatResult:
    # The same breakdown as CombatResult below, scoped to a single weapon
    # profile (every weapon instance sharing one name, across every model in
    # the attacking unit that fired it) rather than the whole combat.
    name             : str
    # The weapon's Damage characteristic, e.g. "D6+2".
    damage           : str       = field(default="")
    # How many hits it scored (as CombatResult.hits).
    hits             : int       = field(default=0)
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
    # How many hits were scored (rolled or automatic, and any extra ones -
    # e.g. Sustained Hits) - and how many of those with [INDIRECT FIRE]
    # weapons.
    hits                       : int       = field(default=0)
    indirect_hits              : int       = field(default=0)
    # How many of those wounded (rolled, or automatically - e.g. Lethal
    # Hits).
    wounds                     : int       = field(default=0)
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
    # The Miracle dice used in place of rolled dice (Acts of Faith), described
    # - e.g. "Hit roll (Bolt rifle): Miracle dice 6".
    acts_of_faith: list[str] = field(default_factory=list)
    # What players chose or re-rolled as it was made (e.g. Artisan,
    # Necromechanic, a re-rolled Attacks roll), described.
    choices: list[str] = field(default_factory=list)
    # The same totals above, broken down per weapon profile (grouped by
    # weapon name) instead of pooled across the whole attacking unit.
    weapon_results: list[WeaponCombatResult] = field(default_factory=list)
    # Each defending model's wounds left afterwards (0: destroyed), and the
    # hazardous wounds each attacking model took - by unit model id.
    defender_wounds_remaining: dict[int, int] = field(default_factory=dict)
    attacker_damage: dict[int, int] = field(default_factory=dict)




def _damaged_bracket(unit_model, attacker_wounds, attacker_damaged: bool) -> int | None:
    # The top of the model's Damaged profile's wounds range if it's on it now:
    # in a game, by its wounds left; in the calculator (no wounds known), when
    # "Attacking model is Damaged" is ticked. None: it has no such profile, or
    # isn't on it.
    from app.seeds.datasheet_abilities import DAMAGED_PROFILES

    top = next(
        (DAMAGED_PROFILES[a.name][0] for a in unit_model.model.abilities if a.name in DAMAGED_PROFILES),
        None,
    )
    if top is None:
        return None
    if not attacker_wounds or unit_model.id not in attacker_wounds:
        return top if attacker_damaged else None
    return top if 0 < attacker_wounds[unit_model.id] <= top else None


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
    firing: dict[int, dict] | None = None,
    defender_wounds: dict[int, int] | None = None,
    attacker_wounds: dict[int, int] | None = None,
    snap_shots: bool = False,
    extra_weapons: dict[int, list] | None = None,
    defender_model_rules: dict[int, list[Rule]] | None = None,
    allocation_order: list[int] | None = None,
    indirect: bool = False,
    indirect_spotted: bool = False,
    attack_limits: dict | None = None,
    hazards_rolled: set | None = None,
    precision_models: set | None = None,
    attacker_miracle=None,
    defender_miracle=None,
    weapon_bonuses: dict[int, list[WeaponBonus]] | None = None,
    decisions=None,
) -> CombatResult:
    # `decisions`: the players' choices as the attack's made, in a game (see
    # app/services/in_game/attack_decisions.py's Decisions) - asked once a
    # weapon's Hit, Wound or saving throws are rolled, to re-roll or change
    # one (e.g. Command Re-roll, Seething Hatred, Artisan); before its saving
    # throws are rolled (an Act of Faith); and as one fails (Necromechanic).
    # `weapon_bonuses`: what rules add to particular attacking models'
    # weapons, by unit model id (see WeaponBonus - e.g. Righteous Rage's
    # Miracle dice discarded).
    # `attacker_miracle`, `defender_miracle`: an Act of Faith each side's
    # unit performs in the attack (see
    # app/seeds/factions/adepta_sororitas/acts_of_faith.py's AttackMiracle):
    # the first roll of its kind (Hit, Wound or Damage for the attacker, a
    # Saving throw for the defender) is its Miracle dice - an unmodified roll
    # of that value, which can't be re-rolled. Marked used once it is.
    # `precision_models`: attacking models (by unit model id) whose melee
    # weapons have [PRECISION] (e.g. after Epic Challenge).
    # `attack_limits`: how many attacks each weapon (by id) makes at most
    # against this target, across the models with it - when a unit splits
    # its melee attacks between targets (04.02); it's counted down.
    # `hazards_rolled`: the weapons (by id) whose hazard roll was already made
    # in this unit's attacks (against another target); added to.
    # `allocation_order`: the defender's order for its allocation groups (by
    # group id - see _Allocation), where the rules leave it to them.
    # `indirect` (10.07): the target isn't visible, so only [INDIRECT FIRE]
    # weapons shoot it - the target has the benefit of cover, Hit rolls can't
    # be re-rolled, and only an unmodified 6 hits (4+ if `indirect_spotted`:
    # the unit remained stationary and a friendly unit can see the target).
    # `defender_model_rules`: more rules for attacks allocated to particular
    # defending models, by unit model id (e.g. a repaired VEHICLE's Feel No
    # Pain).
    # `extra_weapons`: more weapons attacking models fire, by unit model id
    # (e.g. a transport's Firing Deck: its embarked models' weapons).
    # `firing`, if given, is which weapons each attacking model can fire on
    # the battlefield and whether each is within half range: {unit model id:
    # {weapon id: half range}} (see app/services/in_game/shooting.py). A model only
    # fires the selected weapons it lists, and `half_range` is then per weapon.
    # `defender_wounds` and `attacker_wounds`, if given, are the wounds each
    # model has left in a game ({unit model id: wounds}): a defending model
    # not in it is already destroyed, and isn't attacked.
    # `snap_shots` (e.g. Fire Overwatch): every Hit roll needs an unmodified 6,
    # can't be re-rolled, and triggers nothing (no Sustained or Lethal Hits) -
    # attacks that hit automatically (Torrent) still do, and extra attacks
    # (Rapid Fire) are still made.
    # The defending unit is its models, each with its own wound pool, in
    # allocation groups (see _Allocation): each attack is allocated to a model
    # in the current group, and a single attack's damage never spills onto a
    # second model. In a game, models that have lost wounds are already
    # wounded.
    def wounded(unit_model) -> bool:
        return (
            defender_wounds is not None
            and defender_wounds[unit_model.id] < unit_model.wounds
        )

    ordered_unit_models = sorted(
        (
            unit_model
            for unit_model in defender.unit_models
            if defender_wounds is None or unit_model.id in defender_wounds
        ),
        key=lambda unit_model: not wounded(unit_model),
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
    # The models' names, either side - e.g. "while this unit contains a
    # Repentia Superior model".
    attacker_unit_model_names = [unit_model.model.name for unit_model in attacker.unit_models]
    # Snap shots hit on an unmodified 6 - or less, with an ability that says
    # so (datasheet_abilities SNAP_SHOTS_ON - e.g. Sentinel Directives: 5+).
    snap_shots_on = 6
    if snap_shots:
        from app.seeds import datasheet_abilities

        snap_shots_on = min(
            (
                datasheet_abilities.SNAP_SHOTS_ON[a.name]
                for unit_model in attacker.unit_models
                for a in unit_model.model.abilities
                if a.name in datasheet_abilities.SNAP_SHOTS_ON
            ),
            default=6,
        )
    defender_unit_model_names = [unit_model.model.name for unit_model in defender.unit_models]

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
    refrain = any(a.name == DEVASTATING_REFRAIN for a in datasheet_abilities)
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
    # The defending unit is engaged (17.03).
    target_engaged = TARGET_ENGAGED in defender_positions
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
            "attacker_unit_model_names": attacker_unit_model_names,
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
    # One failed Hit roll it can re-roll, this time it attacks - or one failed
    # Hit or Wound roll (e.g. Seething Hatred). In a game, its player's
    # offered it once a weapon's Hit or Wound rolls are rolled (see offer);
    # otherwise the first to fail is re-rolled.
    one_reroll = {
        "left": 1,
        "kinds": (
            {"hit", "wound"}
            if unit_wide_state.get("reroll_one_hit_or_wound")
            else {"hit"} if unit_wide_state.get("reroll_one_failed_hit") else set()
        ),
    }

    def spend_one_reroll(kind: str, weapon, roll: int) -> bool:
        if decisions is not None or one_reroll["left"] <= 0 or kind not in one_reroll["kinds"]:
            return False
        one_reroll["left"] -= 1
        return True

    def offer(kind: str, rolled_dice: list[RolledDie], unit: Unit) -> None:
        # In a game: once rolls are made - a weapon's Hit, Wound or saving
        # throws together, or its Attacks, a Damage or a hazard roll - their
        # player's offered what can re-roll or change one of them (e.g.
        # Command Re-roll, Seething Hatred, Artisan) - one at a time, until
        # they carry on.
        if decisions is None:
            return
        while any(d.rerollable and not d.rerolled for d in rolled_dice):
            one = one_reroll["left"] > 0 and kind in one_reroll["kinds"]
            chosen = decisions.dice(kind, unit, rolled_dice, one)
            if chosen is None:
                return
            source, die, note = chosen
            if source == "one":
                one_reroll["left"] -= 1
            before = die.value
            name = ROLL_NAMES[kind]
            if source == "six":
                die.give(6, rerolled=False)
                result.choices.append(f"{note}: a {name} of {before} ({die.weapon_name}) became a 6")
            else:
                die.give(dice.randint(1, die.sides), rerolled=True)
                result.choices.append(
                    f"{note}: a {name} of {before} ({die.weapon_name}) re-rolled: {die.value}"
                )

    def plain_dice(kind: str, faces: list[int], weapon, sides: int, check=None) -> list[RolledDie]:
        # Dice whose values are all that matters (an Attacks or Damage roll's,
        # a hazard roll) - `faces` kept up to date with them.
        found = []
        for index, value in enumerate(faces):
            def give(value: int, rerolled: bool, index=index) -> None:
                die = found[index]
                faces[index] = value
                die.value, die.rerolled = value, die.rerolled or rerolled
                die.passed = die.check(value)

            found.append(
                RolledDie(
                    kind, value, weapon.name, (check or (lambda v: True))(value),
                    check=check or (lambda v: True), give=give, sides=sides,
                )
            )
        return found

    def own_rules(unit_model) -> tuple:
        # Rules only this model has: per-model detachment rules (e.g.
        # War-Form Mantles), those a game gives it (e.g. a repair's Feel No
        # Pain, or an aura it's wholly within), and its wargear's protective
        # abilities (e.g. a Shield Dome's 5+ invulnerable save) - and those of
        # wargear another model in the unit has that reaches the bearer's unit.
        return (
            tuple(
                ability
                for ability in model_abilities(
                    list(defender_detachment_rules or []),
                    enhancement_rules.model_keywords(defender, unit_model),
                    "defender",
                )
                if isinstance(ability, Rule)
            )
            + tuple((defender_model_rules or {}).get(unit_model.id, ()))
            + tuple(
                ability
                for other in defender.unit_models
                for gear in other.wargear
                if other is unit_model or gear.scope == "bearers_unit"
                for ability in gear.abilities
                if _protective(ability)
            )
        )

    def model_state(unit_model) -> dict:
        # What the defender's rules - and its own - do for one of its models in
        # particular: e.g. the Aegis Protocol's +1 Toughness for KASTELAN ROBOT
        # models, Robotic Bodyguard's Feel No Pain 4+ for the Datasmith leading
        # them, or Emanatus Force Field's 4+ against ranged attacks.
        state: dict = {}
        context = {
            "step": "target_model",
            "target_model_keywords": enhancement_rules.model_keywords(defender, unit_model),
            # (Its datasheet abilities' names - e.g. for "other CHARACTER
            # models", the one with the ability aside: Veteran Bodyguard.)
            "target_model_abilities": {a.name for a in unit_model.model.abilities},
            "target_model_name": unit_model.model.name,
            "defender_unit_model_names": defender_unit_model_names,
            "defender_keywords": defender_keywords,
            "defender_model_keywords": defender_model_keywords,
        }
        _apply_triggered_effects(defender_rules, context, state, deque())
        _apply_triggered_effects(list(own_rules(unit_model)), context, state, deque())
        return state

    model_states = {id(unit_model): model_state(unit_model) for unit_model in ordered_unit_models}
    targets: deque[_Target] = deque(
        _Target(
            toughness=unit_model.model.toughness
            + (1 if model_states[id(unit_model)].get("plus_one_toughness") else 0),
            # (Or a better Save characteristic a rule gives it - e.g. Stanchion
            # of Holy Martyrs' 2+.)
            save=min(unit_model.save, model_states[id(unit_model)].get("save_characteristic", 7)),
            # (With any its rules give it - e.g. Defend the Divine Work's 4+ -
            # so its allocation group knows it.)
            invulnerable=min(
                (
                    save
                    for save in (
                        unit_model.model.invulnerable,
                        model_states[id(unit_model)].get("invulnerable_save"),
                    )
                    if save is not None
                ),
                default=None,
            ),
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
            # (Its own, or one a rule gives it - e.g. a Null Rod.)
            feel_no_pain_mortal=min(
                (
                    fnp
                    for fnp in (
                        unit_model.model.feel_no_pain_mortal,
                        model_states[id(unit_model)].get("feel_no_pain_mortal"),
                    )
                    if fnp is not None
                ),
                default=None,
            ),
            feel_no_pain_psychic=model_states[id(unit_model)].get("feel_no_pain_psychic"),
            invulnerable_ranged_only=unit_model.model.invulnerable_ranged_only,
            ranged_invulnerable=model_states[id(unit_model)].get("ranged_invulnerable"),
            minus_one_damage=bool(model_states[id(unit_model)].get("minus_one_damage")),
            remaining_wounds=(
                unit_model.wounds
                if defender_wounds is None
                else defender_wounds[unit_model.id]
            ),
            unit_model_id=unit_model.id,
            is_leader=bool(unit_model.model.is_leader),
            is_support=bool(unit_model.model.is_support),
            wounds_characteristic=unit_model.wounds,
            # (A leader model is a CHARACTER, even if its keywords weren't
            # entered.)
            is_character=bool(unit_model.model.is_leader)
            or "CHARACTER" in enhancement_rules.model_keywords(defender, unit_model),
            deadly_demise=any(
                effect.keyword == "deadly_demise"
                for ability in unit_model.model.abilities
                for effect in ability.effects
            ),
            rules=own_rules(unit_model),
        )
        for unit_model in ordered_unit_models
    )
    # Every model attacked, destroyed or not (the queue loses them as they die).
    all_targets = list(targets)
    # (Ranged attacks, unless every weapon chosen is a melee one.)
    chosen = [
        w for m in attacker.unit_models for w in m.weapons if w.id in selected_weapon_ids
    ]
    ranged_attacks = not chosen or any(w.weapon_type != "melee" for w in chosen)
    allocation = _Allocation(targets, allocation_order, ranged=ranged_attacks)

    def unit_toughness() -> int:
        # The T an attack against the unit uses (19.02): the highest of its
        # bodyguard models' left (not its leaders' or supports'), or if only
        # those are left, the highest of theirs.
        bodyguard = [t for t in targets if not (t.is_leader or t.is_support)]
        return max(t.toughness for t in (bodyguard or targets))

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

    # Failed hazard rolls (the weapon each was for), and each attacking model's
    # Feel No Pain against mortal wounds.
    failed_hazards: list[WeaponCombatResult] = []
    attacker_fnps: dict[int, int | None] = {}

    # A unit that can't see its target makes no attacks at all - this is checked
    # once for the whole attacking unit, since visibility is a property of the
    # engagement as a whole, not of any one model within it.
    if visible or indirect:
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
            # (Not protective ones, e.g. a Shield Dome's invulnerable save:
            # those protect the bearer when it's attacked - see below.)
            wargear_abilities = [
                ability
                for other in attacker.unit_models
                for gear in other.wargear
                if other is unit_model or gear.scope == "bearers_unit"
                for ability in gear.abilities
                if not _protective(ability)
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

            attacker_fnps[unit_model.id] = shooter_fnp

            # Its own weapons, any its enhancement gives it (e.g. TL-4Ø9), and any
            # more it fires (e.g. a Firing Deck's).
            for weapon in (
                list(unit_model.weapons)
                + enhancement_rules.granted_weapons(unit_model)
                + (extra_weapons or {}).get(unit_model.id, [])
            ):
                # Only weapons the caller chose to fire/swing with this attack count.
                if weapon.id not in selected_weapon_ids:
                    continue
                # Shooting a target it can't see: only [INDIRECT FIRE] weapons.
                is_indirect = indirect and any(
                    a.name == INDIRECT_FIRE for a in weapon.abilities
                )
                if indirect and not is_indirect:
                    continue
                # Only those it can fire where it is (in range of a target it
                # can see), if that's known.
                weapon_half_range = half_range
                if firing is not None:
                    can_fire = firing.get(unit_model.id, {})
                    if weapon.id not in can_fire:
                        continue
                    weapon_half_range = can_fire[weapon.id]

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
                    # Its own abilities, by name - e.g. for "(excluding
                    # [DEVASTATING WOUNDS] attacks)".
                    "weapon_ability_names": {a.name for a in weapon.abilities},
                    "defender_keywords": defender_keywords,
                    "attacker_keywords": attacker_keywords,
                    "attacker_unit_model_keywords": attacker_unit_model_keywords,
                    "attacker_unit_model_names": attacker_unit_model_names,
                    "attacker_options": attacker_options,
                    "defender_model_keywords": defender_model_keywords,
                    "attacker_positions": attacker_positions,
                    "defender_positions": defender_positions,
                    "charged": charged,
                    "defender_battle_shocked": defender_battle_shocked,
                    "attacker_damaged": attacker_damaged,
                    # The firing model's Damaged profile, if it's on it: the
                    # most wounds remaining it applies at (e.g. 6, for
                    # "Damaged: 1-6 Wounds Remaining") - for DAMAGED_6.
                    "attacker_damaged_bracket": _damaged_bracket(
                        unit_model, attacker_wounds, attacker_damaged
                    ),
                    # The firing model's own keywords - e.g. for "weapons
                    # equipped by KASTELAN ROBOT models".
                    "attacker_model_keywords": enhancement_rules.model_keywords(
                        attacker, unit_model
                    ),
                    # ...and its datasheet abilities' names - e.g. for "this
                    # model's attacks" (Calgar's Champion).
                    "attacker_model_abilities": {a.name for a in unit_model.model.abilities},
                    "attacker_model_name": unit_model.model.name,
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

                # Fighting: melee weapons. Shooting while engaged (close-quarters
                # shooting, 10.06): a non-MONSTER/VEHICLE model only fires its
                # [CLOSE-QUARTERS] (Pistol) weapons; a MONSTER/VEHICLE model
                # fires any - at -1 to hit unless it's one of those - but no
                # [BLAST] weapon at a unit it's engaged with.
                big = bool(
                    enhancement_rules.model_keywords(attacker, unit_model) & {"MONSTER", "VEHICLE"}
                )
                close_quarters = eligibility_state.get("pistol", False)
                if not is_ranged and not in_engagement_range:
                    continue
                if is_ranged and in_engagement_range and not (close_quarters or big):
                    continue
                if is_ranged and (in_engagement_range or target_engaged) and _blast(weapon):
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
                    "uses_precision": (
                        apply_precision and eligibility_state.get("precision", False)
                    )
                    or (not is_ranged and unit_model.id in (precision_models or ())),
                    "result": weapon_result,
                    "half_range": weapon_half_range,
                    "indirect": is_indirect,
                    # Made with an [INDIRECT FIRE] weapon (seen or not) - e.g.
                    # for Devastating Refrain.
                    "indirect_weapon": any(a.name == INDIRECT_FIRE for a in weapon.abilities),
                    # -1 to hit: a MONSTER/VEHICLE model shooting while
                    # engaged (other than a close-quarters weapon at the unit
                    # it's engaged with), or any shot at an engaged
                    # MONSTER/VEHICLE (17.03 - other than a close-quarters
                    # weapon fired by a unit engaged with it).
                    "engaged_penalty": is_ranged
                    and (in_engagement_range or target_engaged)
                    and not close_quarters,
                }

                # Attacks characteristic: how many attacks this weapon makes,
                # rolled once per weapon (flat or dice notation, e.g. "2", "D3", "2D6").
                rolled_attacks, attack_faces = roll_dice_faces(weapon.attacks)
                if attack_faces and decisions is not None and not (
                    attack_limits is not None and weapon.id in attack_limits
                ):
                    # (Its player's offered re-rolling one of its dice - e.g.
                    # Command Re-roll.)
                    plus = rolled_attacks - sum(attack_faces)
                    offer(
                        "attacks",
                        plain_dice("attacks", attack_faces, weapon, _sides(weapon.attacks)),
                        attacker,
                    )
                    rolled_attacks = sum(attack_faces) + plus
                attack_count = rolled_attacks
                bonuses = [
                    b
                    for b in (weapon_bonuses or {}).get(unit_model.id, ())
                    if b.applies(weapon, is_ranged)
                ]
                bonus_d = sum(b.damage for b in bonuses)
                attack_count += sum(b.attacks for b in bonuses)
                fired["strength_bonus"] = sum(b.strength for b in bonuses)
                fired["devastating"] = any(b.devastating for b in bonuses)
                fired["mortal_on_wound"] = any(b.mortal_on_wound for b in bonuses)
                if attack_limits is not None and weapon.id in attack_limits:
                    attack_count = min(attack_count, attack_limits[weapon.id])
                    attack_limits[weapon.id] -= attack_count
                    if not attack_count:
                        continue
                pending_attacks: deque[dict] = deque(
                    {"auto_hit": False} for _ in range(attack_count)
                )

                # Pre-weapon: checked once per weapon (not per individual attack),
                # for traits that apply to the whole shooting sequence rather than
                # any one attack - e.g. Rapid Fire adding attacks to the queue when
                # within half range, or Hazardous risking a self-inflicted wound.
                pre_weapon_state: dict = {}
                _apply_triggered_effects(
                    abilities,
                    {"step": "pre_weapon", "half_range": weapon_half_range, **weapon_context},
                    pre_weapon_state,
                    pending_attacks,
                )
                # A below-average roll for its Attacks re-rolled, if it can
                # be (e.g. Symphonic Payload) - not when its attacks are
                # split between targets.
                if (
                    pre_weapon_state.get("reroll_attacks")
                    and random_notation(weapon.attacks)
                    and rolled_attacks < average_damage(weapon.attacks)
                    and not (attack_limits is not None and weapon.id in attack_limits)
                ):
                    again = roll_dice(weapon.attacks)
                    result.choices.append(
                        f"{weapon.name}: Attacks roll of {rolled_attacks} re-rolled: {again}"
                    )
                    for _ in range(again - rolled_attacks):
                        pending_attacks.append({"auto_hit": False})
                    for _ in range(rolled_attacks - again):
                        if pending_attacks:
                            pending_attacks.pop()
                if pre_weapon_state.get("halve_attacks"):
                    # Its Attacks halved, rounding up (e.g. a Damaged
                    # profile).
                    for _ in range(len(pending_attacks) // 2):
                        pending_attacks.pop()
                # Melta: extra damage on every attack this weapon makes.
                fired["damage_bonus"] = pre_weapon_state.get("melta", 0) + bonus_d
                if pre_weapon_state.get("blast"):
                    # Blast: +1 attack for every five models in the target unit
                    # (counted when targets are declared, before any attacks
                    # resolve), rounding down - or more, for Blast 2 (e.g.
                    # Cleave 2).
                    per_five = int(pre_weapon_state["blast"])
                    for _ in range(len(targets) // 5 * per_five):
                        pending_attacks.append({"auto_hit": False})
                if pre_weapon_state.get("torrent"):
                    # Torrent: every attack hits automatically.
                    for pending_attack in pending_attacks:
                        pending_attack["auto_hit"] = True
                hazard_key = (unit_model.id, weapon.id)
                if pre_weapon_state.get("hazardous") and (
                    hazards_rolled is None or hazard_key not in hazards_rolled
                ):
                    if hazards_rolled is not None:
                        hazards_rolled.add(hazard_key)
                    # A hazard roll for each [HAZARDOUS] weapon selected; a
                    # 1-2 fails, and the unit suffers mortal wounds once its
                    # attacks are resolved (see below).
                    hazard_roll = dice.randint(1, 6)
                    if decisions is not None:
                        faces = [hazard_roll]
                        offer(
                            "hazard",
                            plain_dice(
                                "hazard", faces, weapon, 6, check=lambda v: not hazard_failed(v)
                            ),
                            attacker,
                        )
                        hazard_roll = faces[0]
                    result.hazardous_rolls.append(hazard_roll)
                    weapon_result.hazardous_rolls.append(hazard_roll)
                    if hazard_failed(hazard_roll):
                        failed_hazards.append(weapon_result)

                profiles.setdefault(weapon.name, []).extend(
                    (attack, fired) for attack in pending_attacks
                )


    def miracle_roll(roll: str, weapon, miracle) -> int | None:
        # The Miracle dice's value, if it substitutes this roll (see
        # attacker_miracle) - None to roll the die.
        if miracle is None or not miracle.applies(roll, weapon):
            return None
        from app.seeds.factions.adepta_sororitas.acts_of_faith import ROLL_NAMES

        value = miracle.take()
        result.acts_of_faith.append(
            f"{ROLL_NAMES[roll]} ({weapon.name}): Miracle dice {value}"
        )
        return value

    def target_for(fired: dict) -> _Target:
        # The model an attack is allocated to: in the current allocation group
        # (a CHARACTER's, for a Precision weapon - see _Allocation).
        return allocation.current(precision=fired["uses_precision"])

    def _inflict(target: _Target, attack: dict, fired: dict, mortal: bool) -> None:
        # The attack inflicts damage on the model it's allocated to: its D
        # (rolled, plus any bonus), a point at a time, each negated on a Feel
        # No Pain - one against mortal wounds too, if they are. The model
        # destroyed, the rest is lost: damage never spills onto another model.
        weapon = fired["weapon"]
        weapon_result = fired["result"]
        if attack.get("fixed_damage") is not None:
            # A set number of mortal wounds (e.g. Rapturous Blows' 1).
            _suffer(target, attack, fired, attack["fixed_damage"], mortal)
            return
        miracle = (
            miracle_roll("damage", weapon, attacker_miracle)
            if random_notation(weapon.damage)
            else None
        )
        rolled_damage, damage_faces = roll_dice_faces(weapon.damage, first=miracle)
        # A damage roll that can be re-rolled is, if it's below average (not
        # one with a Miracle dice in it).
        if (
            damage_faces
            and miracle is None
            and attack.get("reroll_damage")
            and rolled_damage < average_damage(weapon.damage)
        ):
            weapon_result.damage_rolls.extend(damage_faces)
            rolled_damage, damage_faces = roll_dice_faces(weapon.damage)
        elif damage_faces and decisions is not None:
            # (Its player's offered re-rolling one of its dice - e.g. Command
            # Re-roll. Not a Miracle dice.)
            plus = rolled_damage - sum(damage_faces)
            rolled = plain_dice("damage", damage_faces, weapon, _sides(weapon.damage))
            if miracle is not None:
                rolled[0].rerollable = False
            offer("damage", rolled, attacker)
            rolled_damage = sum(damage_faces) + plus
        weapon_result.damage_rolls.extend(damage_faces)
        damage = (
            rolled_damage + fired["damage_bonus"] + (1 if attack.get("plus_one_damage") else 0)
        )
        # e.g. Nanoassembly Protocols: -1 Damage, to a minimum of 1 - or the
        # model's own (e.g. Implacable Resilience).
        if attack.get("minus_one_damage") or target.minus_one_damage:
            damage = max(1, damage - 1)
        _suffer(target, attack, fired, damage, mortal)

    def _suffer(target: _Target, attack: dict, fired: dict, damage: int, mortal: bool) -> None:
        # The model suffers `damage`, a point at a time, each negated on a
        # Feel No Pain - one against mortal wounds too, if they are.
        weapon_result = fired["result"]
        fnps = [target.feel_no_pain, attack.get("feel_no_pain")]
        if mortal:
            fnps += [target.feel_no_pain_mortal, attack.get("feel_no_pain_mortal")]
        weapon = fired.get("weapon")
        if weapon is not None and any(a.name == PSYCHIC for a in weapon.abilities):
            fnps.append(target.feel_no_pain_psychic)
        feel_no_pain = min((fnp for fnp in fnps if fnp is not None), default=None)
        for _ in range(damage):
            if feel_no_pain is not None:
                fnp_roll = dice.randint(1, 6)
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
                    demise_roll = dice.randint(1, 6)
                    result.deadly_demise_rolls.append(demise_roll)
                    # (Devastating Refrain: on a 5+, to an [INDIRECT FIRE]
                    # attack by a unit with it.)
                    demise_on = (
                        DEVASTATING_REFRAIN_DEMISE
                        if fired["indirect_weapon"] and refrain
                        else 6
                    )
                    if demise_roll >= demise_on:
                        result.deadly_demise_explosions += 1
                result.models_destroyed += 1
                weapon_result.models_destroyed += 1
                break

    def hit_die(
        attack: dict, fired: dict, spawned: deque, roll: int, hit_context: dict, hits, rerolled: bool,
        rerollable: bool,
    ) -> RolledDie:
        # Its Hit roll, which the player can re-roll (see offer): the attack's
        # as it was before it, its hit-step triggers checked against the new
        # roll.
        abilities = fired["abilities"]
        base_before_triggers = attack.pop("_before_hit")

        def give(value: int, rerolled: bool) -> None:
            attack.clear()
            attack.update(base_before_triggers)
            spawned.clear()
            _apply_triggered_effects(
                abilities, {"step": "hit", "roll": value, **hit_context}, attack, spawned
            )
            if rerolled:
                result.attack_rerolls.append(value)
                fired["result"].attack_rerolls.append(value)
            else:
                _replace(result.attack_rolls, die.value, value)
                _replace(fired["result"].attack_rolls, die.value, value)
            die.value, die.passed, die.rerolled = value, hits(value), die.rerolled or rerolled

        die = RolledDie(
            "hit", roll, fired["weapon"].name, hits(roll), rerollable=rerollable,
            rerolled=rerolled, check=hits, give=give,
        )
        return die

    for profile_attacks in profiles.values():
        # Hit phase: every attack of this profile rolls to hit. Extra attacks
        # and hits an effect adds (e.g. Sustained Hits) join the same phase -
        # an extra hit is already a hit, so it skips the roll. The Hit rolls
        # made together are offered to the player (see offer) before what
        # they spawn is resolved - then those, in turn.
        successful_hits: list[tuple[dict, dict]] = []
        queue = deque(profile_attacks)
        while queue:
            # (In order: an attack that hits automatically has no dice.)
            rolled_hits: list[tuple[RolledDie | None, dict, dict, deque]] = []
            batch, queue = queue, deque()
            for attack, fired in batch:
                # (A weapon with no skill - [TORRENT]'s "N/A" - never rolls.)
                if attack["auto_hit"] or not fired["weapon"].skill:
                    rolled_hits.append((None, attack, fired, deque()))
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
                        "in_engagement_range": in_engagement_range,
                        "half_range": fired["half_range"],
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
                    0
                    if ignore_penalties
                    else attack.get("minus_one_to_hit", 0) + (1 if fired["engaged_penalty"] else 0)
                )
                # [HEAVY] is one +1, however many sources grant it.
                if attack.get("heavy"):
                    hit_modifier += 1
                hit_modifier = max(-1, min(1, hit_modifier))
                # Setting the characteristic (e.g. "a Ballistic Skill of 3+") comes
                # before any modifiers or improvements.
                skill = 3 if is_ranged and attack.get("ranged_skill_3") else weapon.skill
                effective_skill = skill - hit_modifier
                # Improving the BS/WS characteristic itself (e.g. a Doctrina
                # Imperative) isn't a hit roll modifier, so it's outside the cap.
                if is_ranged and attack.get("plus_one_skill_ranged"):
                    effective_skill -= 1
                # Plunging Fire (22.05): a TOWERING model's ranged attack at a
                # target within 12" has +1 BS (not by or at AIRCRAFT).
                if (
                    is_ranged
                    and "TOWERING" in weapon_context["attacker_model_keywords"]
                    and WITHIN_12_OF_TARGET in attacker_positions
                    and "AIRCRAFT" not in weapon_context["attacker_model_keywords"]
                    and "AIRCRAFT" not in defender_keywords
                ):
                    effective_skill -= 1
                # The benefit of cover worsens a ranged attack's BS by 1 (13.08) -
                # an indirect fire attack's target always has it.
                if (
                    (in_cover or attack.get("benefit_of_cover") or fired["indirect"])
                    and is_ranged
                    and not attack.get("ignore_cover")
                    and not ignore_penalties
                ):
                    effective_skill += 1
                if not is_ranged and attack.get("plus_one_skill_melee"):
                    effective_skill -= 1
                # (Worsened, e.g. by Data-spike: the characteristic, outside the cap.)
                if not is_ranged and attack.get("worse_melee_skill"):
                    effective_skill += 1

                # The unmodified roll that scores a Critical Hit: a 6, or lower for
                # some attacks (e.g. Enslaved Artifice's 5+).
                critical_hit_on = attack.get("critical_hit_on", 6)
                # (Or every successful Hit roll does - e.g. Flesh Hunger.)
                if attack.get("successful_hits_critical"):
                    critical_hit_on = min(critical_hit_on, max(2, effective_skill))
                hit_context = {"critical_hit_on": critical_hit_on, **weapon_context}

                # Indirect fire: an unmodified 1-5 fails (1-3 if spotted).
                indirect_needs = (4 if indirect_spotted else 6) if fired["indirect"] else 0
                hits = _hit_check(indirect_needs, critical_hit_on, effective_skill)

                # Hit roll: succeeds (hits) on a roll equal to or greater than skill.
                hit_roll = miracle_roll("hit", weapon, attacker_miracle)
                miracle_hit = hit_roll is not None
                if hit_roll is None:
                    hit_roll = dice.randint(1, 6)
                result.attack_rolls.append(hit_roll)
                weapon_result.attack_rolls.append(hit_roll)
                if snap_shots:
                    # Only an unmodified 6 (or what an ability says) hits;
                    # nothing else happens.
                    if hit_roll >= snap_shots_on:
                        rolled_hits.append((None, attack, fired, deque()))
                    continue
                attack["_before_hit"] = dict(attack)
                _apply_triggered_effects(
                    abilities, {"step": "hit", "roll": hit_roll, **hit_context}, attack, spawned
                )
                # (A Miracle dice can't be re-rolled.)
                rerolled = False
                if not hits(hit_roll) and not fired["indirect"] and not miracle_hit and (
                    attack.get("reroll_failed_hits")
                    or unit_rerolls_failed_hits
                    or (hit_roll == 1 and attack.get("reroll_hit_ones"))
                    or spend_one_reroll("hit", weapon, hit_roll)
                ):
                    # Re-roll a failed hit (or just a 1) once, replacing the
                    # original result - hit-step triggers (e.g. Sustained Hits)
                    # are re-checked against the new roll too.
                    hit_roll = dice.randint(1, 6)
                    rerolled = True
                    result.attack_rerolls.append(hit_roll)
                    weapon_result.attack_rerolls.append(hit_roll)
                    _apply_triggered_effects(
                        abilities, {"step": "hit", "roll": hit_roll, **hit_context}, attack, spawned
                    )
                die = hit_die(
                    attack, fired, spawned, hit_roll, hit_context, hits, rerolled,
                    rerollable=not fired["indirect"] and not miracle_hit,
                )
                rolled_hits.append((die, attack, fired, spawned))
            offer("hit", [r[0] for r in rolled_hits if r[0] is not None], attacker)
            for die, attack, fired, spawned in rolled_hits:
                queue.extend((extra, fired) for extra in spawned)
                if die is None or die.passed:
                    successful_hits.append((attack, fired))

        # Wound phase: every hit rolls to wound. Nothing has been destroyed yet
        # this phase, so each wound roll is against the Toughness of the model
        # its attack will be allocated to first.
        result.hits += len(successful_hits)
        for _, f in successful_hits:
            f["result"].hits += 1
        result.indirect_hits += sum(1 for _, f in successful_hits if f["indirect_weapon"])
        if not targets:
            continue  # the defending unit was wiped out by an earlier profile
        wounds: list[tuple[dict, dict]] = []
        extra_mortals: list[tuple[dict, dict]] = []
        # (In order: an attack that wounds automatically has no dice.)
        rolled_wounds: list[tuple[RolledDie | None, dict, dict]] = []
        for attack, fired in successful_hits:
            weapon = fired["weapon"]
            abilities = fired["abilities"]
            weapon_context = fired["context"]
            weapon_result = fired["result"]
            strength = (
                weapon.strength
                + fired.get("strength_bonus", 0)
                + (1 if attack.get("plus_one_strength") else 0)
                + (2 if attack.get("plus_two_strength") else 0)
            )
            toughness = unit_toughness()
            threshold = wound_threshold(strength, toughness)
            # The wound step's checks can compare the two (e.g. "if the
            # Strength of that attack is greater than the Toughness").
            wound_context = {"strength": strength, "toughness": toughness, **weapon_context}

            if attack.get("auto_pass_wound"):
                rolled_wounds.append((None, attack, fired))
                continue
            before = dict(attack)
            wound_passed = False
            rerolled = False
            # A failed wound roll may be re-rolled once (e.g. Twin-linked,
            # or just a 1), with the wound-step triggers re-checked against
            # the new roll.
            # (A Miracle dice can't be re-rolled.)
            wound_roll = None
            miracle_wound = False
            for is_reroll in (False, True):
                if is_reroll and (
                    miracle_wound
                    or not (
                        attack.get("reroll_failed_wounds")
                        or (wound_roll == 1 and attack.get("reroll_wound_ones"))
                        or spend_one_reroll("wound", weapon, wound_roll)
                    )
                ):
                    break
                wound_roll = (
                    None if is_reroll else miracle_roll("wound", weapon, attacker_miracle)
                )
                miracle_wound = wound_roll is not None
                if wound_roll is None:
                    wound_roll = dice.randint(1, 6)
                if is_reroll:
                    rerolled = True
                    result.wound_rerolls.append(wound_roll)
                    weapon_result.wound_rerolls.append(wound_roll)
                else:
                    result.wound_rolls.append(wound_roll)
                    weapon_result.wound_rolls.append(wound_roll)
                wound_passed = _wounds(attack, wound_roll, abilities, wound_context, threshold)
                if wound_passed:
                    break
            rolled_wounds.append(
                (
                    _wound_die(
                        attack, before, fired, wound_roll, wound_passed, wound_context,
                        threshold, rerolled, rerollable=not miracle_wound, result=result,
                    ),
                    attack,
                    fired,
                )
            )
        offer("wound", [r[0] for r in rolled_wounds if r[0] is not None], attacker)
        for die, attack, fired in rolled_wounds:
            if die is not None and not die.passed:
                continue
            # [DEVASTATING WOUNDS] a rule gives this model's weapon (e.g.
            # Divine Deliverance): a Critical Wound allows no save.
            if fired.get("devastating") and die is not None and (
                die.value == 6 or attack.get("critical_wound")
            ):
                attack["no_save"] = True
            wounds.append((attack, fired))
            if fired.get("mortal_on_wound"):
                # (e.g. Rapturous Blows: 1 mortal wound as well.)
                extra_mortals.append(({"no_save": True, "fixed_damage": 1}, fired))
        result.wounds += len(wounds)

        # Save rolls (05.03): one for each wound, made together; then resolved
        # from the lowest result to the highest, each allocated to the current
        # allocation group (05.04) - which can change as models are destroyed.
        # Attacks that allow no save (Devastating Wounds) inflict mortal
        # wounds instead, after the normal damage.
        saving = [(a, f) for a, f in wounds if not a.get("no_save")]
        devastating = [(a, f) for a, f in wounds if a.get("no_save")] + extra_mortals
        if decisions is not None and saving and (
            defender_miracle is None or defender_miracle.used
        ):
            # (One weapon's saves at a time: a profile is one weapon's.)
            chosen = decisions.save_miracle(saving[0][1]["weapon"], len(saving))
            if chosen is not None:
                defender_miracle = chosen
        def allocated(attack: dict, target: _Target, fired: dict) -> dict:
            # Rules only the model it's allocated to has (e.g. a TECH-PRIEST's
            # 4+ invulnerable save) apply to this attack from here on.
            if not target.rules:
                return attack
            attack = dict(attack)
            _apply_triggered_effects(
                target.rules, {"step": "allocated", **fired["context"]}, attack, deque()
            )
            return attack

        def saves(attack: dict, target: _Target, fired: dict, save_roll: int) -> bool:
            # Whether the saving throw succeeds for the model it's allocated
            # to (`attack` already allocated).
            weapon = fired["weapon"]
            # The invulnerable save if the roll beats it (unaffected by AP),
            # otherwise the armour save, worsened by the weapon's AP.
            ap = weapon.ap - 1 if attack.get("improve_ap") else weapon.ap
            if attack.get("worsen_ap"):
                ap = min(0, ap + 1)
            save_needed = target.save - ap
            # (A ranged-only invulnerable save, e.g. an ion shield, doesn't
            # help against melee attacks.)
            invulnerable = _invulnerable_of(target, fired["is_ranged"])
            if invulnerable is not None:
                save_needed = min(save_needed, invulnerable)
            # An invulnerable save granted by a rule (e.g. Waaagh!'s 5+ while
            # riled up) - also unaffected by AP.
            if attack.get("invulnerable_save") is not None:
                save_needed = min(save_needed, attack["invulnerable_save"])
            # +1 to the save roll (an unmodified 1 still fails).
            bonus = 1 if attack.get("plus_one_to_save") else 0
            return bool(attack.get("miracle_save")) or (
                save_roll != 1 and save_roll + bonus >= save_needed
            )

        def save_die(attack: dict, before: dict, fired: dict, roll: int, miracle: bool) -> RolledDie:
            # A saving throw, which the defending player can re-roll or change
            # once they're all rolled (see offer) - whether it succeeds judged
            # against the model they'd go to first now.
            def triggered(value: int, state: dict) -> dict:
                _apply_triggered_effects(
                    fired["abilities"],
                    {"step": "save", "roll": value, **fired["context"]},
                    state,
                    deque(),
                )
                return state

            def check(value: int) -> bool:
                if not targets:
                    return True
                target = target_for(fired)
                return saves(allocated(triggered(value, dict(before)), target, fired), target, fired, value)

            def give(value: int, rerolled: bool) -> None:
                attack.clear()
                attack.update(triggered(value, dict(before)))
                _replace(result.save_rolls, die.value, value)
                _replace(fired["result"].save_rolls, die.value, value)
                die.value, die.rerolled = value, die.rerolled or rerolled
                die.passed = check(value)

            die = RolledDie(
                "save", roll, fired["weapon"].name, False, rerollable=not miracle,
                check=check, give=give,
            )
            die.passed = check(roll)
            return die

        rolled_saves: list[tuple[RolledDie | None, dict, dict, int]] = []
        for attack, fired in saving:
            save_roll = miracle_roll("save", fired["weapon"], defender_miracle)
            miracle = save_roll is not None
            if save_roll is None:
                save_roll = dice.randint(1, 6)
            elif defender_miracle.auto_success:
                # (Triptych of the Macharian Crusade: it succeeds, whatever
                # its value.)
                attack = {**attack, "miracle_save": True}
            result.save_rolls.append(save_roll)
            fired["result"].save_rolls.append(save_roll)
            before = dict(attack)
            _apply_triggered_effects(
                fired["abilities"],
                {"step": "save", "roll": save_roll, **fired["context"]},
                attack,
                deque(),
            )
            die = save_die(attack, before, fired, save_roll, miracle) if decisions is not None else None
            rolled_saves.append((die, attack, fired, save_roll))
        if decisions is not None:
            offer("save", [r[0] for r in rolled_saves], defender)
        rolled = sorted(
            ((d.value if d is not None else roll, attack, fired) for d, attack, fired, roll in rolled_saves),
            key=lambda r: r[0],
        )

        for save_roll, attack, fired in rolled:
            if not targets:
                break  # defending unit has no models left
            weapon = fired["weapon"]
            target = target_for(fired)
            attack = allocated(attack, target, fired)
            if saves(attack, target, fired, save_roll):
                continue  # save succeeded - no damage from this attack
            if decisions is not None:
                # The defender's choice as it fails: the attack's Damage to 0
                # (Necromechanic).
                choice = decisions.failed_save(target.unit_model_id, weapon, save_roll)
                if choice is not None:
                    result.choices.append(choice.note)
                    continue
            _inflict(target, attack, fired, mortal=False)

        for attack, fired in devastating:
            if not targets:
                break
            target = _mortal_wound_target(targets)
            _inflict(target, allocated(attack, target, fired), fired, mortal=True)

    # Failed hazard rolls: once its attacks are resolved, the attacking unit
    # suffers mortal wounds for each (06.03, 24.15), allocated as mortal
    # wounds are (06.02) - each negated on the model's Feel No Pain.
    if failed_hazards:
        own = [
            _Target(
                toughness=0, save=7, invulnerable=None, feel_no_pain=None,
                remaining_wounds=(attacker_wounds or {}).get(m.id, m.wounds),
                unit_model_id=m.id, wounds_characteristic=m.wounds,
                is_character="CHARACTER" in enhancement_rules.model_keywords(attacker, m),
            )
            for m in attacker.unit_models
            if attacker_wounds is None or m.id in attacker_wounds
        ]
        alive = deque(t for t in own if t.remaining_wounds > 0)
        per_failure = hazard_wounds(
            [enhancement_rules.model_keywords(attacker, m) for m in attacker.unit_models
             if attacker_wounds is None or m.id in attacker_wounds]
        )
        for weapon_result in failed_hazards:
            for _ in range(per_failure):
                if not alive:
                    break
                victim = _mortal_wound_target(alive)
                fnp = attacker_fnps.get(victim.unit_model_id)
                if fnp is not None and dice.randint(1, 6) >= fnp:
                    continue
                result.hazardous_wounds += 1
                weapon_result.hazardous_wounds += 1
                result.attacker_damage[victim.unit_model_id] = (
                    result.attacker_damage.get(victim.unit_model_id, 0) + 1
                )
                victim.remaining_wounds -= 1
                if victim.remaining_wounds <= 0:
                    alive.remove(victim)
                    result.hazardous_models_destroyed += 1

    result.defending_models_remaining = len(targets)
    result.weapon_results = list(weapon_results_by_name.values())
    result.defender_wounds_remaining = {
        target.unit_model_id: max(0, target.remaining_wounds) for target in all_targets
    }
    return result
