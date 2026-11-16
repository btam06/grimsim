from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.effects import (
    ADD_D3_EXTRA_HITS,
    ADD_D6_PLUS_3_ATTACKS,
    ADD_ATTACKS_1,
    ADD_EXTRA_HIT,
    ADD_ATTACKS_4,
    REROLL_ATTACKS,
    ADD_ATTACKS_9,
    ADD_ATTACKS_6,
    ADD_ATTACKS_5,
    SUCCESSFUL_HITS_CRITICAL,
    REROLL_ONE_FAILED_HIT,
    REROLL_ONE_HIT_OR_WOUND,
    ADD_ATTACKS_3,
    ADD_ATTACKS_2,
    ADD_TWO_EXTRA_HITS,
    ASSAULT,
    AUTO_PASS_WOUND,
    BENEFIT_OF_COVER,
    BLAST,
    BLAST_2,
    CANNOT_ATTACK,
    CRITICAL_HIT_4,
    CRITICAL_HIT_5,
    DEADLY_DEMISE,
    FEEL_NO_PAIN_4,
    FEEL_NO_PAIN_5,
    FEEL_NO_PAIN_6,
    FEEL_NO_PAIN_MORTAL_5,
    FEEL_NO_PAIN_MORTAL_4,
    FEEL_NO_PAIN_PSYCHIC_4,
    INVULNERABLE_2,
    SAVE_2,
    HALVE_ATTACKS,
    FORCE_CRITICAL_WOUND,
    HAZARDOUS,
    HEAVY,
    IGNORE_COVER,
    IGNORE_HIT_PENALTIES,
    IGNORE_WOUND_PENALTIES,
    IMPROVE_AP,
    PLUS_ONE_TO_SAVE,
    REROLL_DAMAGE,
    INVULNERABLE_4,
    INVULNERABLE_5,
    RANGED_INVULNERABLE_4,
    WORSE_MELEE_SKILL,
    MELTA_2,
    MELTA_3,
    MELTA_4,
    MELTA_6,
    MINUS_ONE_DAMAGE,
    MINUS_ONE_TO_HIT,
    MINUS_ONE_TO_WOUND,
    NO_SAVE,
    PISTOL,
    PLUS_ONE_DAMAGE,
    PLUS_ONE_SKILL_MELEE,
    PLUS_ONE_SKILL_RANGED,
    PLUS_ONE_STRENGTH,
    PLUS_ONE_TOUGHNESS,
    PLUS_ONE_TO_HIT,
    PLUS_ONE_TO_WOUND,
    PLUS_TWO_STRENGTH,
    PRECISION,
    RANGED_SKILL_3,
    REROLL_FAILED_HITS,
    REROLL_FAILED_WOUNDS,
    REROLL_HIT_ONES,
    REROLL_WOUND_ONES,
    TORRENT,
    WORSEN_AP,
)
from app.models import Effect

# (keyword, name, description) - keyword must match a function registered in
# app/combat_rules/effects.py.
ENTRIES = [
    (
        ADD_D3_EXTRA_HITS,
        "Add D3 Extra Hits",
        "Adds D3 additional hits to the attack chain.",
    ),
    (
        ADD_D6_PLUS_3_ATTACKS,
        "Add D6+3 Attacks",
        "Adds D6+3 additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        ADD_ATTACKS_1,
        "Add Extra Attack",
        "Adds one additional attack to the chain for this weapon, with its own hit roll.",
    ),
    (
        ADD_EXTRA_HIT,
        "Add Extra Hit",
        "Adds one additional hit to the attack chain.",
    ),
    (
        REROLL_ONE_FAILED_HIT,
        "Re-roll One Failed Hit",
        "One failed Hit roll among the unit's attacks can be re-rolled.",
    ),
    (
        REROLL_ONE_HIT_OR_WOUND,
        "Re-roll One Hit or Wound Roll",
        "One failed Hit roll or one failed Wound roll among the unit's attacks can be "
        "re-rolled - in a game, its player chooses which as they fail.",
    ),
    (
        SUCCESSFUL_HITS_CRITICAL,
        "Successful Hits Are Critical",
        "Every successful Hit roll for this attack scores a Critical Hit.",
    ),
    (
        ADD_ATTACKS_5,
        "Add Five Attacks",
        "Adds five additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        ADD_ATTACKS_6,
        "Add Six Attacks",
        "Adds six additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        ADD_ATTACKS_3,
        "Add Three Attacks",
        "Adds three additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        ADD_ATTACKS_2,
        "Add Two Attacks",
        "Adds two additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        ADD_TWO_EXTRA_HITS,
        "Add Two Extra Hits",
        "Adds two additional hits to the attack chain.",
    ),
    (
        ASSAULT,
        "Assault",
        "This weapon may still be fired even if its bearer's unit advanced this turn.",
    ),
    (
        AUTO_PASS_WOUND,
        "Auto-Pass Wound",
        "The wound roll for this attack automatically succeeds.",
    ),
    (
        BENEFIT_OF_COVER,
        "Benefit of Cover",
        "The target has the Benefit of Cover against this attack, as if it were in cover.",
    ),
    (
        BLAST,
        "Blast",
        "This weapon makes 1 additional attack for every five models in the target unit.",
    ),
    (
        BLAST_2,
        "Blast 2",
        "This weapon makes 2 additional attacks for every five models in the target unit.",
    ),
    (
        CANNOT_ATTACK,
        "Cannot Attack",
        "This weapon can't be used against the current target.",
    ),
    (
        CRITICAL_HIT_4,
        "Critical Hit on 4+",
        "An unmodified Hit roll of 4+ scores a Critical Hit for this attack.",
    ),
    (
        CRITICAL_HIT_5,
        "Critical Hit on 5+",
        "An unmodified Hit roll of 5+ scores a Critical Hit for this attack.",
    ),
    (
        DEADLY_DEMISE,
        "Deadly Demise",
        "When a model with this is destroyed, roll a D6: on a 6 it explodes.",
    ),
    (
        FEEL_NO_PAIN_4,
        "Feel No Pain 4+",
        "The targeted model has Feel No Pain 4+ against this attack (a better one is kept).",
    ),
    (
        FEEL_NO_PAIN_5,
        "Feel No Pain 5+",
        "The targeted model has Feel No Pain 5+ against this attack (a better one is kept).",
    ),
    (
        FEEL_NO_PAIN_6,
        "Feel No Pain 6+",
        "The targeted model has Feel No Pain 6+ against this attack (a better one is kept).",
    ),
    (
        FEEL_NO_PAIN_MORTAL_5,
        "Feel No Pain 5+ vs Mortal Wounds",
        "Feel No Pain 5+ against mortal wounds only (a better one is kept).",
    ),
    (
        FEEL_NO_PAIN_MORTAL_4,
        "Feel No Pain 4+ vs Mortal Wounds",
        "Feel No Pain 4+ against mortal wounds only (a better one is kept).",
    ),
    (
        FEEL_NO_PAIN_PSYCHIC_4,
        "Feel No Pain 4+ vs Psychic Attacks",
        "Feel No Pain 4+ against Psychic Attacks only (a better one is kept).",
    ),
    (
        INVULNERABLE_2,
        "2+ Invulnerable Save",
        "The model has a 2+ invulnerable save (a better one is kept).",
    ),
    (
        HALVE_ATTACKS,
        "Halve Attacks",
        "The weapon's Attacks characteristic is halved (rounding up).",
    ),
    (
        SAVE_2,
        "Save 2+",
        "The model has a Save characteristic of 2+ (a better one is kept).",
    ),
    (
        FORCE_CRITICAL_WOUND,
        "Force Critical Wound",
        "This attack's wound counts as a critical wound regardless of the actual roll.",
    ),
    (
        HAZARDOUS,
        "Hazardous",
        "The firing model makes a hazard roll, risking a self-inflicted wound.",
    ),
    (
        HEAVY,
        "Heavy",
        "+1 to hit for this attack's weapon. Counts once, however many sources grant Heavy.",
    ),
    (
        IGNORE_COVER,
        "Ignores Cover",
        "This attack's hit roll is not worsened by the defender being in cover.",
    ),
    (
        IGNORE_HIT_PENALTIES,
        "Ignore Hit Roll Penalties",
        "Modifiers that worsen this attack's hit roll (including cover) are ignored.",
    ),
    (
        IGNORE_WOUND_PENALTIES,
        "Ignore Wound Roll Penalties",
        "Modifiers that worsen this attack's wound roll are ignored.",
    ),
    (
        PLUS_ONE_TO_SAVE,
        "+1 to Save",
        "Add 1 to the save roll against this attack (an unmodified 1 still fails).",
    ),
    (
        REROLL_DAMAGE,
        "Re-roll Damage",
        "This attack's damage roll is re-rolled if it came up below its average.",
    ),
    (
        ADD_ATTACKS_9,
        "Add Nine Attacks",
        "Adds nine additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        ADD_ATTACKS_4,
        "Add Four Attacks",
        "Adds four additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        REROLL_ATTACKS,
        "Re-roll Attacks",
        "The weapon's roll for its Attacks characteristic is re-rolled if it came up below "
        "its average (checked once per weapon).",
    ),
    (
        IMPROVE_AP,
        "Improve AP by 1",
        "This attack's Armour Penetration is improved by 1.",
    ),
    (
        WORSE_MELEE_SKILL,
        "Worse Melee Weapon Skill",
        "The attacking model's melee weapons' Weapon Skill is worsened by 1.",
    ),
    (
        RANGED_INVULNERABLE_4,
        "4+ Invulnerable Save Against Ranged Attacks",
        "The model has a 4+ invulnerable save against ranged attacks (a better one is kept).",
    ),
    (
        INVULNERABLE_4,
        "4+ Invulnerable Save",
        "The targeted model has a 4+ invulnerable save against this attack (a better one is kept).",
    ),
    (
        INVULNERABLE_5,
        "5+ Invulnerable Save",
        "The targeted model has a 5+ invulnerable save against this attack (a better one is kept).",
    ),
    (
        MELTA_2,
        "Melta 2",
        "Each attack this weapon makes inflicts 2 extra damage.",
    ),
    (
        MELTA_3,
        "Melta 3",
        "Each attack this weapon makes inflicts 3 extra damage.",
    ),
    (
        MELTA_4,
        "Melta 4",
        "Each attack this weapon makes inflicts 4 extra damage.",
    ),
    (
        MELTA_6,
        "Melta 6",
        "Each attack this weapon makes inflicts 6 extra damage.",
    ),
    (
        MINUS_ONE_DAMAGE,
        "-1 Damage",
        "Subtract 1 from this attack's Damage (to a minimum of 1).",
    ),
    (
        MINUS_ONE_TO_HIT,
        "-1 to Hit",
        "This attack's hit roll needs 1 more to succeed.",
    ),
    (
        MINUS_ONE_TO_WOUND,
        "-1 to Wound",
        "This attack's wound roll needs 1 more to succeed (an unmodified 6 still wounds).",
    ),
    (
        NO_SAVE,
        "No Save",
        "The save roll for this attack is skipped entirely (no armor or invulnerable save).",
    ),
    (
        PISTOL,
        "Pistol",
        "This weapon may be fired while its bearer is in engagement range.",
    ),
    (
        PLUS_ONE_DAMAGE,
        "+1 Damage",
        "Add 1 to this attack's Damage.",
    ),
    (
        PLUS_ONE_SKILL_MELEE,
        "+1 Skill (Melee)",
        "This attack's hit roll needs 1 less to succeed, but only for a melee weapon.",
    ),
    (
        PLUS_ONE_SKILL_RANGED,
        "+1 Skill (Ranged)",
        "This attack's hit roll needs 1 less to succeed, but only for a ranged weapon.",
    ),
    (
        PLUS_ONE_STRENGTH,
        "+1 Strength",
        "Add 1 to the weapon's Strength for this attack.",
    ),
    (
        PLUS_ONE_TOUGHNESS,
        "+1 Toughness",
        "Add 1 to the Toughness of the defending model it applies to.",
    ),
    (
        PLUS_ONE_TO_HIT,
        "+1 to Hit",
        "This attack's hit roll needs 1 less to succeed.",
    ),
    (
        PLUS_ONE_TO_WOUND,
        "+1 to Wound",
        "This attack's wound roll needs 1 less to succeed (cancelled by a -1 to wound).",
    ),
    (
        PLUS_TWO_STRENGTH,
        "+2 Strength",
        "Add 2 to the weapon's Strength for this attack.",
    ),
    (
        PRECISION,
        "Precision",
        "If the attacker applies precision, this weapon's attacks target leaders first, then supports, then other models.",
    ),
    (
        RANGED_SKILL_3,
        "Ranged BS 3+",
        "Ranged weapons have a Ballistic Skill of 3+ (before any improvements).",
    ),
    (
        REROLL_FAILED_HITS,
        "Re-roll Failed Hits",
        "If this attack's hit roll fails, it is rolled once more and the second result is used instead.",
    ),
    (
        REROLL_FAILED_WOUNDS,
        "Re-roll Failed Wounds",
        "If this attack's wound roll fails, it is rolled once more and the second result is used.",
    ),
    (
        REROLL_HIT_ONES,
        "Re-roll Hit Rolls of 1",
        "A Hit roll of 1 for this attack can be re-rolled.",
    ),
    (
        REROLL_WOUND_ONES,
        "Re-roll Wound Rolls of 1",
        "A Wound roll of 1 for this attack can be re-rolled.",
    ),
    (
        TORRENT,
        "Torrent",
        "Every attack this weapon makes hits automatically.",
    ),
    (
        WORSEN_AP,
        "Worsen AP by 1",
        "This attack's Armour Penetration is worsened by 1 (AP0 stays AP0).",
    ),
]


# Keywords that have been renamed: {old: new}. Existing rows are renamed in
# place on startup, so the abilities linked to them keep them.
RENAMED = {
    "add_extra_attack": "add_attacks_1",
    "add_two_attacks": "add_attacks_2",
    "add_three_attacks": "add_attacks_3",
    "add_four_attacks": "add_attacks_4",
    "add_six_attacks": "add_attacks_6",
    "add_nine_attacks": "add_attacks_9",
}


async def _rename(session: AsyncSession) -> None:
    rows = (await session.execute(select(Effect).where(Effect.keyword.in_(RENAMED)))).scalars()
    taken = set(
        (await session.execute(select(Effect.keyword).where(Effect.keyword.in_(RENAMED.values()))))
        .scalars()
        .all()
    )
    for row in rows.all():
        if RENAMED[row.keyword] not in taken:
            row.keyword = RENAMED[row.keyword]
    await session.flush()


async def seed(session: AsyncSession) -> None:
    await _rename(session)
    existing = set((await session.execute(select(Effect.keyword))).scalars().all())
    missing = [
        Effect(keyword=keyword, name=name, description=description)
        for keyword, name, description in ENTRIES
        if keyword not in existing
    ]
    session.add_all(missing)
    await session.commit()
