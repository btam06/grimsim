from __future__ import annotations

import random
from collections import deque
from typing import Any

# Each effect is a hardcoded keyword + a function that mutates the current
# attack's state and/or the queue of pending attacks for the weapon still being
# resolved. The keyword is what gets stored on an Effect row
# (app/models/effect.py) and seeded (app/seeds/effects.py) so it can be attached
# to a WeaponAbility; the engine (app/services/combat.py) looks the function
# back up by that same keyword once one of the ability's conditions matches.
#
# To add another effect: write a `(state, pending) -> None` function below,
# register its keyword in EFFECTS, then add a matching row in
# app/seeds/effects.py.

AUTO_PASS_WOUND = "auto_pass_wound"
ADD_EXTRA_HIT = "add_extra_hit"
IGNORE_COVER = "ignore_cover"
NO_SAVE = "no_save"
FORCE_CRITICAL_WOUND = "force_critical_wound"
ADD_EXTRA_ATTACK = "add_extra_attack"
HAZARDOUS = "hazardous"
PLUS_ONE_TO_HIT = "plus_one_to_hit"
REROLL_FAILED_HITS = "reroll_failed_hits"
PLUS_ONE_SKILL_RANGED = "plus_one_skill_ranged"
PLUS_ONE_SKILL_MELEE = "plus_one_skill_melee"
ASSAULT = "assault"
PISTOL = "pistol"
PRECISION = "precision"
MINUS_ONE_TO_HIT = "minus_one_to_hit"
IMPROVE_AP = "improve_ap"
INVULNERABLE_5 = "invulnerable_5"
INVULNERABLE_4 = "invulnerable_4"
CANNOT_ATTACK = "cannot_attack"
ADD_SIX_ATTACKS = "add_six_attacks"
MINUS_ONE_TO_WOUND = "minus_one_to_wound"
PLUS_ONE_TO_WOUND = "plus_one_to_wound"
FEEL_NO_PAIN_5 = "feel_no_pain_5"
FEEL_NO_PAIN_4 = "feel_no_pain_4"
ADD_THREE_ATTACKS = "add_three_attacks"
ADD_TWO_ATTACKS = "add_two_attacks"
REROLL_HIT_ONES = "reroll_hit_ones"
REROLL_WOUND_ONES = "reroll_wound_ones"
RANGED_SKILL_3 = "ranged_skill_3"
PLUS_ONE_STRENGTH = "plus_one_strength"
PLUS_ONE_DAMAGE = "plus_one_damage"
WORSEN_AP = "worsen_ap"
FEEL_NO_PAIN_6 = "feel_no_pain_6"
FEEL_NO_PAIN_MORTAL_5 = "feel_no_pain_mortal_5"
TORRENT = "torrent"
MELTA_2 = "melta_2"
MELTA_6 = "melta_6"
ADD_D6_PLUS_3_ATTACKS = "add_d6_plus_3_attacks"
PLUS_ONE_TOUGHNESS = "plus_one_toughness"
BLAST = "blast"
REROLL_FAILED_WOUNDS = "reroll_failed_wounds"
DEADLY_DEMISE = "deadly_demise"
ADD_TWO_EXTRA_HITS = "add_two_extra_hits"
BENEFIT_OF_COVER = "benefit_of_cover"
HEAVY = "heavy"
MELTA_3 = "melta_3"
CRITICAL_HIT_5 = "critical_hit_5"
MINUS_ONE_DAMAGE = "minus_one_damage"
PLUS_TWO_STRENGTH = "plus_two_strength"
IGNORE_HIT_PENALTIES = "ignore_hit_penalties"
IGNORE_WOUND_PENALTIES = "ignore_wound_penalties"


def auto_pass_wound(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The wound roll for *this* attack is skipped and treated as an automatic success.
    state["auto_pass_wound"] = True


def force_critical_wound(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's wound counts as a critical wound regardless of the actual
    # roll (e.g. an Anti-Infantry/Anti-Vehicle threshold was met) - it still
    # triggers critical_wound-dependent effects like Devastating Wounds.
    state["critical_wound"] = True


def add_extra_hit(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues one additional hit onto the attack chain - it's already a hit, so it
    # skips straight to the wound step with no hit roll of its own.
    pending.append({"auto_hit": True})


def ignore_cover(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll is not worsened by the defender being in cover.
    state["ignore_cover"] = True


def no_save(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The save roll for *this* attack is skipped entirely and treated as failed -
    # no armor save, and no invulnerable save either.
    state["no_save"] = True


def add_extra_attack(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues one additional attack onto the chain for this weapon - unlike
    # add_extra_hit, this is a fresh attack that still needs its own hit roll.
    pending.append({"auto_hit": False})


def hazardous(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Marks this weapon as hazardous - the engine makes a hazard roll for the
    # firing model once per weapon used, separately from the attack sequence.
    state["hazardous"] = True


def plus_one_to_hit(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll needs 1 less to succeed (e.g. Heavy, when the
    # firing unit moved less than 3" this turn).
    # Counted per source: several +1s add up before the hit roll's modifiers
    # are capped at +1/-1 overall.
    state["plus_one_to_hit"] = state.get("plus_one_to_hit", 0) + 1


def reroll_failed_hits(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # If this attack's hit roll fails, it is rolled once more and the second
    # result is used instead.
    state["reroll_failed_hits"] = True


def plus_one_skill_ranged(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll needs 1 less to succeed, but only if the weapon
    # firing is ranged (no effect on a melee attack).
    state["plus_one_skill_ranged"] = True


def plus_one_skill_melee(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll needs 1 less to succeed, but only if the weapon
    # swinging is melee (no effect on a ranged attack).
    state["plus_one_skill_melee"] = True


def assault(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This weapon may still be fired even if the bearer's unit advanced this
    # turn, when a ranged weapon would otherwise be unable to shoot at all.
    state["assault"] = True


def pistol(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This weapon may be fired while its bearer is in engagement range,
    # without becoming a melee weapon - it's still subject to every other
    # normal restriction on ranged weapons.
    state["pistol"] = True


def precision(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This weapon's attacks may (if the attacker chooses to apply precision)
    # target leaders in the defending unit first, then supports, then
    # everything else - instead of the normal order where they die last.
    state["precision"] = True


def minus_one_to_hit(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's hit roll needs 1 more to succeed (e.g. a defensive rule
    # on the unit being attacked). Cancels out a +1 to hit.
    # Counted per source, like plus_one_to_hit.
    state["minus_one_to_hit"] = state.get("minus_one_to_hit", 0) + 1


def improve_ap(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's Armour Penetration is improved by 1 (e.g. AP-1 becomes
    # AP-2), worsening the defender's armour save but not its invulnerable.
    state["improve_ap"] = True


def invulnerable_5(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The model this attack targets has a 5+ invulnerable save against it
    # (e.g. Orks while riled up). If it already has a better one, that's kept.
    state["invulnerable_save"] = min(state.get("invulnerable_save", 7), 5)


def invulnerable_4(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The model this attack targets has a 4+ invulnerable save against it
    # (e.g. Bulwark Imperative). If it already has a better one, that's kept.
    state["invulnerable_save"] = min(state.get("invulnerable_save", 7), 4)


def cannot_attack(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This weapon can't be used against the current target at all (e.g. a
    # HUNTER profile against a unit without the keywords it hunts).
    state["cannot_attack"] = True


def add_six_attacks(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues six additional attacks for this weapon, each with its own hit
    # roll (e.g. "+6 A").
    for _ in range(6):
        pending.append({"auto_hit": False})


def minus_one_to_wound(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's wound roll needs 1 more to succeed (an unmodified 6 still
    # always wounds).
    state["minus_one_to_wound"] = True


def plus_one_to_wound(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's wound roll needs 1 less to succeed - cancelled out by a -1
    # to wound (an unmodified 1 still always fails).
    state["plus_one_to_wound"] = True


def feel_no_pain_5(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The model this attack targets has Feel No Pain 5+ against its damage. If
    # it already has a better one (its own, or another granted), that's kept.
    state["feel_no_pain"] = min(state.get("feel_no_pain", 7), 5)


def feel_no_pain_4(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # As feel_no_pain_5, but 4+.
    state["feel_no_pain"] = min(state.get("feel_no_pain", 7), 4)


def add_three_attacks(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues three additional attacks for this weapon, each with its own hit
    # roll (e.g. Rapid Fire 3 within half range).
    for _ in range(3):
        pending.append({"auto_hit": False})


def add_two_attacks(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues two additional attacks for this weapon, each with its own hit
    # roll (e.g. Rapid Fire 2 within half range).
    for _ in range(2):
        pending.append({"auto_hit": False})


def reroll_hit_ones(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # A Hit roll of 1 for this attack can be re-rolled (any failed Hit roll,
    # with reroll_failed_hits).
    state["reroll_hit_ones"] = True


def reroll_wound_ones(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # A Wound roll of 1 for this attack can be re-rolled.
    state["reroll_wound_ones"] = True


def ranged_skill_3(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Ranged weapons have a Ballistic Skill characteristic of 3+ (before any
    # improvements, e.g. Auto-Divinatory Targeting).
    state["ranged_skill_3"] = True


def plus_one_strength(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Add 1 to this weapon's Strength characteristic for this attack.
    state["plus_one_strength"] = True


def plus_one_damage(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Add 1 to this attack's Damage.
    state["plus_one_damage"] = True


def worsen_ap(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's Armour Penetration is worsened by 1 (e.g. AP-2 becomes
    # AP-1; AP0 stays AP0) - e.g. a defensive "-1 AP" rule.
    state["worsen_ap"] = True


def feel_no_pain_6(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # As feel_no_pain_5, but 6+.
    state["feel_no_pain"] = min(state.get("feel_no_pain", 7), 6)


def feel_no_pain_mortal_5(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Feel No Pain 5+ against mortal wounds only (a better one is kept) - e.g.
    # Benevolence of the Omnissiah.
    state["feel_no_pain_mortal"] = min(state.get("feel_no_pain_mortal", 7), 5)


def torrent(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # [TORRENT]: every attack this weapon makes hits automatically - checked
    # once per weapon (see the pre_weapon condition).
    state["torrent"] = True


def plus_one_toughness(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Add 1 to a defending model's Toughness - checked for each model in the
    # defending unit (step "target_model"), e.g. the Aegis Protocol.
    state["plus_one_toughness"] = True


def blast(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Marks this weapon as Blast - the engine adds 1 attack for every five
    # models in the target unit when the weapon fires.
    state["blast"] = True


def reroll_failed_wounds(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # If this attack's wound roll fails, it is rolled once more and the second
    # result is used instead (e.g. Twin-linked).
    state["reroll_failed_wounds"] = True


def deadly_demise(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # A marker rather than an attack modifier: a model with an ability that has
    # this effect rolls a D6 when destroyed, exploding on a 6. The engine reads
    # it straight off the defending model's abilities, so this does nothing.
    pass


def add_two_extra_hits(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues two additional hits onto the attack chain (e.g. Sustained Hits 2) -
    # like add_extra_hit, each skips straight to the wound step.
    for _ in range(2):
        pending.append({"auto_hit": True})


def benefit_of_cover(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # The target has the Benefit of Cover against this attack (e.g. Stealth),
    # exactly as if the defender were in cover - it doesn't stack with being in
    # cover, and Ignores Cover still ignores it.
    state["benefit_of_cover"] = True


def heavy(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack's weapon has [HEAVY] in effect (its bearer's unit moved less
    # than 3"): +1 to hit. A flag rather than a count - a weapon either has
    # Heavy or it doesn't, so Heavy from more than one source (its own profile
    # and e.g. Protector Imperative) is still a single +1.
    state["heavy"] = True


def melta_3(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This weapon's attacks each inflict 3 extra damage (e.g. Melta 3 within
    # half range) - read once per weapon, when it fires.
    state["melta"] = max(state.get("melta", 0), 3)


def melta_2(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # As melta_3, but 2 extra damage (Melta 2).
    state["melta"] = max(state.get("melta", 0), 2)


def melta_6(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # As melta_3, but 6 extra damage (Melta 6).
    state["melta"] = max(state.get("melta", 0), 6)


def add_d6_plus_3_attacks(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Queues D6+3 additional attacks for this weapon, each with its own hit
    # roll (e.g. Rapid Fire D6+3 within half range).
    for _ in range(random.randint(1, 6) + 3):
        pending.append({"auto_hit": False})


def critical_hit_5(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # An unmodified Hit roll of 5+ scores a Critical Hit for this attack (so it
    # always hits, and Sustained/Lethal Hits trigger on it).
    state["critical_hit_on"] = min(state.get("critical_hit_on", 6), 5)


def minus_one_damage(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Subtract 1 from this attack's Damage (to a minimum of 1) - e.g. a
    # defensive rule on the model it's allocated to.
    state["minus_one_damage"] = True


def plus_two_strength(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # Add 2 to the weapon's Strength for this attack.
    state["plus_two_strength"] = True


def ignore_hit_penalties(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # This attack ignores modifiers that make its Hit roll worse (e.g. -1 to
    # hit, or the target being in cover); bonuses still count.
    state["ignore_hit_penalties"] = True


def ignore_wound_penalties(state: dict[str, Any], pending: deque[dict[str, Any]]) -> None:
    # As ignore_hit_penalties, for the Wound roll (e.g. -1 to wound).
    state["ignore_wound_penalties"] = True


EFFECTS = {
    AUTO_PASS_WOUND: auto_pass_wound,
    ADD_EXTRA_HIT: add_extra_hit,
    IGNORE_COVER: ignore_cover,
    NO_SAVE: no_save,
    FORCE_CRITICAL_WOUND: force_critical_wound,
    ADD_EXTRA_ATTACK: add_extra_attack,
    HAZARDOUS: hazardous,
    PLUS_ONE_TO_HIT: plus_one_to_hit,
    REROLL_FAILED_HITS: reroll_failed_hits,
    PLUS_ONE_SKILL_RANGED: plus_one_skill_ranged,
    PLUS_ONE_SKILL_MELEE: plus_one_skill_melee,
    ASSAULT: assault,
    PISTOL: pistol,
    PRECISION: precision,
    MINUS_ONE_TO_HIT: minus_one_to_hit,
    IMPROVE_AP: improve_ap,
    INVULNERABLE_5: invulnerable_5,
    INVULNERABLE_4: invulnerable_4,
    CANNOT_ATTACK: cannot_attack,
    ADD_SIX_ATTACKS: add_six_attacks,
    MINUS_ONE_TO_WOUND: minus_one_to_wound,
    PLUS_ONE_TO_WOUND: plus_one_to_wound,
    FEEL_NO_PAIN_5: feel_no_pain_5,
    FEEL_NO_PAIN_4: feel_no_pain_4,
    ADD_THREE_ATTACKS: add_three_attacks,
    ADD_TWO_ATTACKS: add_two_attacks,
    REROLL_HIT_ONES: reroll_hit_ones,
    REROLL_WOUND_ONES: reroll_wound_ones,
    RANGED_SKILL_3: ranged_skill_3,
    PLUS_ONE_STRENGTH: plus_one_strength,
    PLUS_ONE_DAMAGE: plus_one_damage,
    WORSEN_AP: worsen_ap,
    FEEL_NO_PAIN_6: feel_no_pain_6,
    FEEL_NO_PAIN_MORTAL_5: feel_no_pain_mortal_5,
    TORRENT: torrent,
    MELTA_2: melta_2,
    MELTA_6: melta_6,
    ADD_D6_PLUS_3_ATTACKS: add_d6_plus_3_attacks,
    PLUS_ONE_TOUGHNESS: plus_one_toughness,
    BLAST: blast,
    REROLL_FAILED_WOUNDS: reroll_failed_wounds,
    DEADLY_DEMISE: deadly_demise,
    ADD_TWO_EXTRA_HITS: add_two_extra_hits,
    BENEFIT_OF_COVER: benefit_of_cover,
    HEAVY: heavy,
    MELTA_3: melta_3,
    CRITICAL_HIT_5: critical_hit_5,
    MINUS_ONE_DAMAGE: minus_one_damage,
    PLUS_TWO_STRENGTH: plus_two_strength,
    IGNORE_HIT_PENALTIES: ignore_hit_penalties,
    IGNORE_WOUND_PENALTIES: ignore_wound_penalties,
}


# Effects that protect a unit rather than modify an attack. A stratagem with
# one, used on the attacking unit (e.g. Benevolence of the Omnissiah, which
# lasts the whole battle round), protects that unit - e.g. against its own
# Hazardous weapons - instead of the target of its attacks.
OWN_UNIT_EFFECTS = {
    FEEL_NO_PAIN_4,
    FEEL_NO_PAIN_5,
    FEEL_NO_PAIN_6,
    FEEL_NO_PAIN_MORTAL_5,
    INVULNERABLE_4,
    INVULNERABLE_5,
}
