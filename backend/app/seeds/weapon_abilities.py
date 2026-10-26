from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import (
    ALWAYS,
    ANTI_FLY_2,
    ANTI_INFANTRY_2,
    ANTI_INFANTRY_3,
    ANTI_INFANTRY_4,
    ANTI_INFANTRY_5,
    ANTI_MONSTER_4,
    ANTI_VEHICLE_2,
    ANTI_VEHICLE_3,
    ANTI_VEHICLE_4,
    ANTI_WALKER_2,
    BEYOND_HALF_RANGE_ATTACK,
    CHARGED,
    CRITICAL_HIT,
    CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE,
    CRITICAL_WOUND,
    MOVED_LESS_THAN_3,
    PRE_WEAPON,
    PRE_WEAPON_NOT_MONSTER_OR_VEHICLE,
    TARGET_INFANTRY,
    TARGET_MONSTER_OR_VEHICLE,
    TARGET_NOT_MONSTER_OR_VEHICLE,
    WITHIN_HALF_RANGE,
)
from app.combat_rules.effects import (
    ADD_D3_EXTRA_HITS,
    ADD_D6_PLUS_3_ATTACKS,
    ADD_EXTRA_ATTACK,
    ADD_EXTRA_HIT,
    ADD_FOUR_ATTACKS,
    ADD_NINE_ATTACKS,
    ADD_SIX_ATTACKS,
    ADD_THREE_ATTACKS,
    ADD_TWO_ATTACKS,
    ADD_TWO_EXTRA_HITS,
    ASSAULT,
    AUTO_PASS_WOUND,
    BLAST,
    BLAST_2,
    CANNOT_ATTACK,
    CRITICAL_HIT_4,
    FORCE_CRITICAL_WOUND,
    HAZARDOUS,
    HEAVY,
    IGNORE_COVER,
    IGNORE_HIT_PENALTIES,
    IMPROVE_AP,
    MELTA_2,
    MELTA_3,
    MELTA_4,
    MELTA_6,
    NO_SAVE,
    PISTOL,
    PLUS_ONE_DAMAGE,
    PLUS_ONE_STRENGTH,
    PLUS_ONE_TO_HIT,
    PLUS_ONE_TO_WOUND,
    PRECISION,
    REROLL_FAILED_WOUNDS,
    TORRENT,
)
from sqlalchemy.orm import selectinload

from app.models import Condition, Effect, WeaponAbility

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "+1 Damage",
        "Add 1 to this weapon's Damage characteristic.",
        [ALWAYS],
        [PLUS_ONE_DAMAGE],
    ),
    (
        "+1 Strength",
        "Add 1 to this weapon's Strength characteristic.",
        [ALWAYS],
        [PLUS_ONE_STRENGTH],
    ),
    (
        "+2 Attacks",
        "Add 2 to this weapon's Attacks characteristic.",
        [PRE_WEAPON],
        [ADD_TWO_ATTACKS],
    ),
    (
        "Anti-Fly 2+",
        "Against a defending unit that contains a FLY model, a wound roll of 2+ is a critical wound.",
        [ANTI_FLY_2],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Infantry 2+",
        "Against a defending unit that contains an INFANTRY model, a wound roll of 2+ is a critical wound.",
        [ANTI_INFANTRY_2],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Infantry 3+",
        "Against a defending unit that contains an INFANTRY model, a wound roll of 3+ is a critical wound.",
        [ANTI_INFANTRY_3],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Infantry 4+",
        "Against a defending unit that contains an INFANTRY model, a wound roll of 4+ is a critical wound.",
        [ANTI_INFANTRY_4],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Infantry 5+",
        "Against a defending unit that contains an INFANTRY model, a wound roll of 5+ is a critical wound.",
        [ANTI_INFANTRY_5],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Monster 4+",
        "Against a defending unit that contains a MONSTER model, a wound roll of 4+ is a critical wound.",
        [ANTI_MONSTER_4],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Vehicle 2+",
        "Against a defending unit that contains a VEHICLE model, a wound roll of 2+ is a critical wound.",
        [ANTI_VEHICLE_2],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Vehicle 3+",
        "Against a defending unit that contains a VEHICLE model, a wound roll of 3+ is a critical wound.",
        [ANTI_VEHICLE_3],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Vehicle 4+",
        "Against a defending unit that contains a VEHICLE model, a wound roll of 4+ is a critical wound.",
        [ANTI_VEHICLE_4],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Anti-Walker 2+",
        "Against a defending unit that contains a WALKER model, a wound roll of 2+ is a critical wound.",
        [ANTI_WALKER_2],
        [FORCE_CRITICAL_WOUND],
    ),
    (
        "Assault",
        "This weapon may still be fired even if the attacking unit advanced this turn.",
        [ALWAYS],
        [ASSAULT],
    ),
    (
        "Blast",
        "This weapon makes 1 additional attack for every five models in the target unit.",
        [ALWAYS],
        [BLAST],
    ),
    (
        "Blast 2",
        "This weapon makes 2 additional attacks for every five models in the target unit.",
        [ALWAYS],
        [BLAST_2],
    ),
    (
        "Blistering Salvoes: Infantry",
        "Each time an attack is made with this weapon that targets an INFANTRY unit, add 1 to the Hit roll.",
        [TARGET_INFANTRY],
        [PLUS_ONE_TO_HIT],
    ),
    (
        "Blistering Salvoes: Monster/Vehicle",
        "Each time an attack is made with this weapon that targets a MONSTER or VEHICLE unit, add 1 to the Hit roll.",
        [TARGET_MONSTER_OR_VEHICLE],
        [PLUS_ONE_TO_HIT],
    ),
    (
        "Blitz Dem Gitz!",
        "If this weapon targets a unit (excluding MONSTER/VEHICLE units), it has +6 A.",
        [PRE_WEAPON_NOT_MONSTER_OR_VEHICLE],
        [ADD_SIX_ATTACKS],
    ),
    (
        "Close-Quarters",
        "This weapon may be fired while the attacking unit is in engagement range (as Pistol).",
        [ALWAYS],
        [PISTOL],
    ),
    (
        # Approximated: "not within 12\"" as "not within half range", which is
        # the same on the 24\" weapons that have it.
        "Conversion",
        "Each time an attack made with this weapon targets an enemy unit that is not within "
        "12\", an unmodified Hit roll of 4+ scores a Critical Hit. (In the calculator: when "
        "the target isn't within half range.)",
        [BEYOND_HALF_RANGE_ATTACK],
        [CRITICAL_HIT_4],
    ),
    (
        "Devastating Wounds",
        "Each critical wound (an unmodified roll of 6 to wound) allows no save.",
        [CRITICAL_WOUND],
        [NO_SAVE],
    ),
    (
        # Blast 2, for melee weapons.
        "Cleave 2",
        "This melee weapon makes 2 additional attacks for every five models in the target unit "
        "(Blast 2, for melee).",
        [ALWAYS],
        [BLAST_2],
    ),
    (
        # [PSYCHIC]: any or all modifiers to the attack's BS/WS and Hit roll
        # can be ignored - so its penalties are (its bonuses kept; the engine
        # only ever improves BS/WS). (Rules triggered by psychic attacks, e.g.
        # Feel No Pain against them, aren't modelled yet.)
        "Psychic",
        "Each time an attack is made with this weapon, you can ignore any or all modifiers to "
        "its BS or WS characteristic and any or all modifiers to the Hit roll. Attacks made "
        "with this weapon are psychic attacks.",
        [ALWAYS],
        [IGNORE_HIT_PENALTIES],
    ),
    (
        # Descriptive only: the calculator already fires every weapon ticked.
        "Extra Attacks",
        "This weapon can be used in addition to the bearer's other melee weapons.",
        [],
        [],
    ),
    (
        "Hazardous",
        "After shooting, the firing model makes a hazard roll, risking a self-inflicted wound.",
        [ALWAYS],
        [HAZARDOUS],
    ),
    (
        "Heavy",
        "If the attacking unit moved less than 3\" this turn, this weapon's attacks get +1 to hit.",
        [MOVED_LESS_THAN_3],
        [HEAVY],
    ),
    (
        "Hunter: Monster/Vehicle",
        "This profile can only target units that contain a MONSTER or VEHICLE model.",
        [TARGET_NOT_MONSTER_OR_VEHICLE],
        [CANNOT_ATTACK],
    ),
    (
        "Ignores Cover",
        "This weapon's attacks are not worsened by the defender being in cover.",
        [ALWAYS],
        [IGNORE_COVER],
    ),
    (
        "Improve AP by 1",
        "Improve this weapon's Armour Penetration characteristic by 1.",
        [ALWAYS],
        [IMPROVE_AP],
    ),
    (
        # Descriptive only: the calculator doesn't model line of sight, and
        # Indirect Fire only changes anything against a target that isn't visible.
        "Indirect Fire",
        "This weapon can target units that are not visible to the attacking model.",
        [],
        [],
    ),
    (
        "Lance",
        "If the bearer made a Charge move this turn, add 1 to this weapon's Wound rolls.",
        [CHARGED],
        [PLUS_ONE_TO_WOUND],
    ),
    (
        "Lethal Hits",
        "Each critical hit (an unmodified roll of 6 to hit) automatically wounds.",
        [CRITICAL_HIT],
        [AUTO_PASS_WOUND],
    ),
    (
        "Lethal Hits: non-Monster/Vehicle",
        "Lethal Hits, but only against a unit with no MONSTER or VEHICLE model.",
        [CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE],
        [AUTO_PASS_WOUND],
    ),
    (
        "Melta 2",
        "When the target is within half range, each attack made with this weapon inflicts 2 extra damage.",
        [WITHIN_HALF_RANGE],
        [MELTA_2],
    ),
    (
        "Melta 3",
        "When the target is within half range, each attack made with this weapon inflicts 3 extra damage.",
        [WITHIN_HALF_RANGE],
        [MELTA_3],
    ),
    (
        "Melta 4",
        "When the target is within half range, each attack made with this weapon inflicts 4 extra damage.",
        [WITHIN_HALF_RANGE],
        [MELTA_4],
    ),
    (
        "Melta 6",
        "When the target is within half range, each attack made with this weapon inflicts 6 extra damage.",
        [WITHIN_HALF_RANGE],
        [MELTA_6],
    ),
    (
        "Pistol",
        "This weapon may be fired while the attacking unit is in engagement range, without becoming a melee weapon.",
        [ALWAYS],
        [PISTOL],
    ),
    (
        "Precision",
        "If the attacker applies precision, attacks target leaders first, then supports, then other models.",
        [ALWAYS],
        [PRECISION],
    ),
    (
        "Rapid Fire 1",
        "When the shooting model is within half range, this weapon makes 1 additional attack.",
        [WITHIN_HALF_RANGE],
        [ADD_EXTRA_ATTACK],
    ),
    (
        "Rapid Fire 2",
        "When the shooting model is within half range, this weapon makes 2 additional attacks.",
        [WITHIN_HALF_RANGE],
        [ADD_TWO_ATTACKS],
    ),
    (
        "Rapid Fire 3",
        "When the shooting model is within half range, this weapon makes 3 additional attacks.",
        [WITHIN_HALF_RANGE],
        [ADD_THREE_ATTACKS],
    ),
    (
        "Rapid Fire 4",
        "When the shooting model is within half range, this weapon makes 4 additional attacks.",
        [WITHIN_HALF_RANGE],
        [ADD_FOUR_ATTACKS],
    ),
    (
        "Rapid Fire 9",
        "When the shooting model is within half range, this weapon makes 9 additional attacks.",
        [WITHIN_HALF_RANGE],
        [ADD_NINE_ATTACKS],
    ),
    (
        "Rapid Fire 6",
        "When the shooting model is within half range, this weapon makes 6 additional attacks.",
        [WITHIN_HALF_RANGE],
        [ADD_SIX_ATTACKS],
    ),
    (
        "Rapid Fire D6+3",
        "When the shooting model is within half range, this weapon makes D6+3 additional attacks.",
        [WITHIN_HALF_RANGE],
        [ADD_D6_PLUS_3_ATTACKS],
    ),
    (
        "Sustained 1",
        "Each critical hit (an unmodified roll of 6 to hit) scores 1 additional hit.",
        [CRITICAL_HIT],
        [ADD_EXTRA_HIT],
    ),
    (
        "Sustained 1: non-Monster/Vehicle",
        "Sustained 1, but only against a unit with no MONSTER or VEHICLE model.",
        [CRITICAL_HIT_NOT_MONSTER_OR_VEHICLE],
        [ADD_EXTRA_HIT],
    ),
    (
        "Sustained 2",
        "Each critical hit (an unmodified roll of 6 to hit) scores 2 additional hits.",
        [CRITICAL_HIT],
        [ADD_TWO_EXTRA_HITS],
    ),
    (
        "Sustained D3",
        "Each critical hit (an unmodified roll of 6 to hit) scores D3 additional hits.",
        [CRITICAL_HIT],
        [ADD_D3_EXTRA_HITS],
    ),
    (
        "Torrent",
        "Every attack this weapon makes hits automatically.",
        [PRE_WEAPON],
        [TORRENT],
    ),
    (
        "Twin-linked",
        "Each time an attack is made with this weapon, you can re-roll that attack's Wound roll.",
        [ALWAYS],
        [REROLL_FAILED_WOUNDS],
    ),
]


# {old name: new name} for entries that have been renamed. Existing rows are
# renamed in place (keeping them attached to their weapons) rather than a
# second row being seeded under the new name.
RENAMED = {
    "SUSTAINED 1": "Sustained 1",
    "RAPID FIRE 1": "Rapid Fire 1",
}


async def _rename(session: AsyncSession) -> None:
    rows = (
        await session.execute(select(WeaponAbility).where(WeaponAbility.name.in_(RENAMED)))
    ).scalars().all()
    taken = set(
        (
            await session.execute(
                select(WeaponAbility.name).where(WeaponAbility.name.in_(RENAMED.values()))
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if RENAMED[row.name] not in taken:
            row.name = RENAMED[row.name]
    await session.flush()


# Entries whose conditions/effects have changed since they were first seeded.
# Existing rows with these names have them reset to the entry above on
# startup (rather than being left alone, as other existing rows are).
RESYNCED = {
    # Was a generic +1 to hit; now the HEAVY flag, so Heavy from more than one
    # source still counts once.
    "Heavy",
}


async def seed(session: AsyncSession) -> None:
    await _rename(session)
    for name, description, condition_keywords, effect_keywords in ENTRIES:
        existing = (
            await session.execute(
                select(WeaponAbility)
                .options(selectinload(WeaponAbility.conditions), selectinload(WeaponAbility.effects))
                .where(WeaponAbility.name == name)
            )
        ).scalar_one_or_none()
        # An existing row is left alone unless it was seeded before this entry
        # had any conditions/effects (e.g. "Precision") - then fill them in -
        # or it's listed in RESYNCED.
        if (
            existing is not None
            and (existing.conditions or existing.effects)
            and name not in RESYNCED
        ):
            continue

        conditions = (
            await session.execute(select(Condition).where(Condition.keyword.in_(condition_keywords)))
        ).scalars().all()
        effects = (
            await session.execute(select(Effect).where(Effect.keyword.in_(effect_keywords)))
        ).scalars().all()
        if len(conditions) != len(condition_keywords) or len(effects) != len(effect_keywords):
            continue  # conditions/effects haven't been seeded yet

        if existing is not None:
            if conditions or effects:
                existing.description = description
                existing.conditions = list(conditions)
                existing.effects = list(effects)
            continue

        session.add(
            WeaponAbility(
                name=name,
                description=description,
                conditions=list(conditions),
                effects=list(effects),
            )
        )
    await session.commit()
