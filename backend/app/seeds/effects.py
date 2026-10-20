from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.effects import (
    ADD_EXTRA_ATTACK,
    ADD_EXTRA_HIT,
    ADD_SIX_ATTACKS,
    ADD_TWO_EXTRA_HITS,
    ADD_THREE_ATTACKS,
    ASSAULT,
    AUTO_PASS_WOUND,
    BENEFIT_OF_COVER,
    BLAST,
    CANNOT_ATTACK,
    DEADLY_DEMISE,
    FEEL_NO_PAIN_4,
    FEEL_NO_PAIN_5,
    FORCE_CRITICAL_WOUND,
    HAZARDOUS,
    HEAVY,
    IGNORE_COVER,
    IGNORE_COVER_UNIT,
    IMPROVE_AP,
    INVULNERABLE_4,
    INVULNERABLE_5,
    MELTA_3,
    MINUS_ONE_TO_HIT,
    MINUS_ONE_TO_WOUND,
    PLUS_ONE_TO_WOUND,
    NO_SAVE,
    PISTOL,
    PLUS_ONE_SKILL_MELEE,
    PLUS_ONE_SKILL_RANGED,
    PLUS_ONE_TO_HIT,
    PRECISION,
    REROLL_FAILED_HITS,
    REROLL_FAILED_WOUNDS,
)
from app.models import Effect

# (keyword, name, description) - keyword must match a function registered in
# app/combat_rules/effects.py.
ENTRIES = [
    (
        AUTO_PASS_WOUND,
        "Auto-Pass Wound",
        "The wound roll for this attack automatically succeeds.",
    ),
    (
        ADD_EXTRA_HIT,
        "Add Extra Hit",
        "Adds one additional hit to the attack chain.",
    ),
    (
        IGNORE_COVER,
        "Ignores Cover",
        "This attack's hit roll is not worsened by the defender being in cover.",
    ),
    (
        NO_SAVE,
        "No Save",
        "The save roll for this attack is skipped entirely (no armor or invulnerable save).",
    ),
    (
        FORCE_CRITICAL_WOUND,
        "Force Critical Wound",
        "This attack's wound counts as a critical wound regardless of the actual roll.",
    ),
    (
        ADD_EXTRA_ATTACK,
        "Add Extra Attack",
        "Adds one additional attack to the chain for this weapon, with its own hit roll.",
    ),
    (
        IGNORE_COVER_UNIT,
        "Ignores Cover (Unit)",
        "The whole attacking unit, not just this model, ignores the in-cover penalty.",
    ),
    (
        HAZARDOUS,
        "Hazardous",
        "The firing model makes a hazard roll, risking a self-inflicted wound.",
    ),
    (
        PLUS_ONE_TO_HIT,
        "+1 to Hit",
        "This attack's hit roll needs 1 less to succeed.",
    ),
    (
        REROLL_FAILED_HITS,
        "Re-roll Failed Hits",
        "If this attack's hit roll fails, it is rolled once more and the second result is used instead.",
    ),
    (
        PLUS_ONE_SKILL_RANGED,
        "+1 Skill (Ranged)",
        "This attack's hit roll needs 1 less to succeed, but only for a ranged weapon.",
    ),
    (
        PLUS_ONE_SKILL_MELEE,
        "+1 Skill (Melee)",
        "This attack's hit roll needs 1 less to succeed, but only for a melee weapon.",
    ),
    (
        ASSAULT,
        "Assault",
        "This weapon may still be fired even if its bearer's unit advanced this turn.",
    ),
    (
        PISTOL,
        "Pistol",
        "This weapon may be fired while its bearer is in engagement range.",
    ),
    (
        PRECISION,
        "Precision",
        "If the attacker applies precision, this weapon's attacks target leaders first, then supports, then other models.",
    ),
    (
        MINUS_ONE_TO_HIT,
        "-1 to Hit",
        "This attack's hit roll needs 1 more to succeed.",
    ),
    (
        IMPROVE_AP,
        "Improve AP by 1",
        "This attack's Armour Penetration is improved by 1.",
    ),
    (
        INVULNERABLE_5,
        "5+ Invulnerable Save",
        "The targeted model has a 5+ invulnerable save against this attack (a better one is kept).",
    ),
    (
        INVULNERABLE_4,
        "4+ Invulnerable Save",
        "The targeted model has a 4+ invulnerable save against this attack (a better one is kept).",
    ),
    (
        CANNOT_ATTACK,
        "Cannot Attack",
        "This weapon can't be used against the current target.",
    ),
    (
        ADD_SIX_ATTACKS,
        "Add Six Attacks",
        "Adds six additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        MINUS_ONE_TO_WOUND,
        "-1 to Wound",
        "This attack's wound roll needs 1 more to succeed (an unmodified 6 still wounds).",
    ),
    (
        PLUS_ONE_TO_WOUND,
        "+1 to Wound",
        "This attack's wound roll needs 1 less to succeed (cancelled by a -1 to wound).",
    ),
    (
        FEEL_NO_PAIN_5,
        "Feel No Pain 5+",
        "The targeted model has Feel No Pain 5+ against this attack (a better one is kept).",
    ),
    (
        FEEL_NO_PAIN_4,
        "Feel No Pain 4+",
        "The targeted model has Feel No Pain 4+ against this attack (a better one is kept).",
    ),
    (
        ADD_THREE_ATTACKS,
        "Add Three Attacks",
        "Adds three additional attacks to this weapon, each with its own hit roll.",
    ),
    (
        BLAST,
        "Blast",
        "This weapon makes 1 additional attack for every five models in the target unit.",
    ),
    (
        REROLL_FAILED_WOUNDS,
        "Re-roll Failed Wounds",
        "If this attack's wound roll fails, it is rolled once more and the second result is used.",
    ),
    (
        DEADLY_DEMISE,
        "Deadly Demise",
        "When a model with this is destroyed, roll a D6: on a 6 it explodes.",
    ),
    (
        ADD_TWO_EXTRA_HITS,
        "Add Two Extra Hits",
        "Adds two additional hits to the attack chain.",
    ),
    (
        BENEFIT_OF_COVER,
        "Benefit of Cover",
        "The target has the Benefit of Cover against this attack, as if it were in cover.",
    ),
    (
        HEAVY,
        "Heavy",
        "+1 to hit for this attack's weapon. Counts once, however many sources grant Heavy.",
    ),
    (
        MELTA_3,
        "Melta 3",
        "Each attack this weapon makes inflicts 3 extra damage.",
    ),
]


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Effect.keyword))).scalars().all())
    missing = [
        Effect(keyword=keyword, name=name, description=description)
        for keyword, name, description in ENTRIES
        if keyword not in existing
    ]
    if missing:
        session.add_all(missing)
        await session.commit()
