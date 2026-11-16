from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import ALWAYS
from app.combat_rules.effects import (
    FEEL_NO_PAIN_5,
    FEEL_NO_PAIN_MORTAL_4,
    FEEL_NO_PAIN_PSYCHIC_4,
    IGNORE_COVER,
    INVULNERABLE_4,
    INVULNERABLE_5,
    REROLL_HIT_ONES,
)
from app.models import Condition, Effect, WargearAbility

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Ignores Cover",
        "Wargear equipped with this is not worsened by the defender being in cover.",
        [ALWAYS],
        [IGNORE_COVER],
    ),
    (
        # Protects the bearer (e.g. a Shield Dome): it applies to attacks
        # against it.
        "5+ Invulnerable Save",
        "The bearer has a 5+ invulnerable save.",
        [ALWAYS],
        [INVULNERABLE_5],
    ),
    (
        # Its bearer's unit can resurrect (see
        # app/seeds/factions/necrons/reanimation.py) - as the datasheet
        # ability of the same name.
        "Resurrection Orb",
        "(Once per battle, per unit) At the end of any phase, you can use this ability. If you "
        "do, this unit resurrects: its Reanimation Protocols activate, but it heals D6 wounds "
        "(instead of D3 wounds). You cannot resurrect more than one unit per turn.",
        [],
        [],
    ),
    (
        "Dispersion Shield",
        "The bearer has a 4+ invulnerable save.",
        [ALWAYS],
        [INVULNERABLE_4],
    ),
    (
        # In a game, a Stratagem used on the bearer's unit rolls for the CP
        # (see datasheet_abilities STRATAGEM_TARGET_CP).
        "Enhanced data-tether",
        "Each time you select the bearer's unit as the target of a Stratagem, roll one D6: on "
        "a 5+, you gain 1CP.",
        [],
        [],
    ),
    (
        # As Enhanced data-tether, for a model that can take one (e.g. an
        # Onager Dunecrawler); it loses SMOKE (not modelled).
        "Broad Spectrum Data-tether",
        "The bearer loses the SMOKE keyword, but each time you target the bearer with a "
        "Stratagem, roll one D6: on a 5+, you gain 1CP.",
        [],
        [],
    ),
    (
        # A Canoness's: protects every model in her unit (scope bearers_unit).
        "Null Rod",
        "Models in the bearer's unit have the Feel No Pain 4+ ability against mortal wounds "
        "and Psychic Attacks.",
        [ALWAYS],
        [FEEL_NO_PAIN_MORTAL_4, FEEL_NO_PAIN_PSYCHIC_4],
    ),
    (
        # A Canoness's: for every model in her unit (scope bearers_unit).
        "Rod of Office",
        "Each time a model in the bearer's unit makes an attack, re-roll a Hit roll of 1.",
        [ALWAYS],
        [REROLL_HIT_ONES],
    ),
    (
        # Re-rolls of the bearer's unit's Advance and Charge rolls (see
        # datasheet_abilities CHARGE_REROLLS, ADVANCE_REROLLS).
        "Sacred Banner",
        "You can re-roll Advance and Charge rolls made for the bearer's unit.",
        [],
        [],
    ),
    (
        # A new quarry for its unit's Virtue of Intolerance when one is
        # destroyed (see app/seeds/factions/adepta_sororitas/unit_abilities.py).
        "Denuncia Oratory",
        "Each time the bearer's unit's quarry is destroyed, you can select a new unit from "
        "your opponent's army to be its quarry.",
        [],
        [],
    ),
    (
        # Returns destroyed models in its player's Command phase (see
        # app/seeds/factions/adepta_sororitas/unit_abilities.py).
        "Salvationist Medikit",
        "In your Command phase, if the bearer is on the battlefield, you can return up to D3 "
        "destroyed models (excluding CHARACTER models) to this unit.",
        [],
        [],
    ),
    (
        # As Enhanced data-tether, on an Archaeopter.
        "Command uplink",
        "Each time you select the bearer's unit as the target of a Stratagem, roll one D6: on "
        "a 5+, you gain 1CP.",
        [],
        [],
    ),
    (
        # A pre-battle move (e.g. an Orbital Comms Array - see
        # app/services/in_game/scouts.py).
        "Scouts 6\"",
        "The bearer's unit has Scouts 6\": at the start of the first battle round, before the "
        "first turn begins, it can make a Normal move of up to 6\".",
        [],
        [],
    ),
]

# Necrons (11th edition datasheets).
ENTRIES += [
    (
        "Nanoscarab Amulet",
        "The bearer has the Feel No Pain 5+ ability.",
        [ALWAYS],
        [FEEL_NO_PAIN_5],
    ),
    (
        "Accelerator Mandible",
        "At the start of the Fight phase, select one friendly CANOPTEK unit within 3\" of the "
        "bearer's unit. Until the end of the phase, improve the Weapon Skill characteristic of "
        "weapons equipped by models in that unit by 1.",
        [],
        [],
    ),
    (
        "Nanoscarab Projector",
        "Once per battle round, when a friendly NECRONS unit within 3\" of the bearer activates its"
        " Reanimation Protocols, the bearer can use this ability. If it does, that unit reanimates"
        " 1 additional wound.",
        [],
        [],
    ),
    (
        "Nebuloscope",
        "Ranged weapons equipped by the bearer have the [IGNORES COVER] ability.",
        [ALWAYS],
        [IGNORE_COVER],
    ),
    (
        "Shadowloom",
        "The bearer has the Stealth ability.",
        [],
        [],
    ),
    (
        "Shieldvanes",
        "The bearer has a 3+ Save characteristic and a Move characteristic of 8\".",
        [],
        [],
    ),
    (
        "Fabricator Claw Array (Aura)",
        "While a friendly NECRONS VEHICLE unit is within 6\" of the bearer, that unit has the Feel "
        "No Pain 6+ ability.",
        [],
        [],
    ),
    (
        "Gloom Prism (Aura)",
        "While a friendly NECRONS unit is within 6\" of the bearer, models in that unit have the "
        "Feel No Pain 5+ ability against mortal wounds and Psychic Attacks.",
        [],
        [],
    ),
]

# Chaos Knights' DAMNED units (11th edition datasheets).
ENTRIES += [
    (
        "Chaos Icon",
        "Each time the bearer's unit takes a Leadership test for the Dark Pacts ability, you can "
        "re-roll that test. (Dark Pacts only works in a HERETIC ASTARTES army - in a Chaos "
        "Knights one, neither does.)",
        [],
        [],
    ),
]


async def seed(session: AsyncSession) -> None:
    for name, description, condition_keywords, effect_keywords in ENTRIES:
        existing = (
            await session.execute(select(WargearAbility.id).where(WargearAbility.name == name))
        ).scalar_one_or_none()
        if existing is not None:
            continue

        conditions = (
            await session.execute(select(Condition).where(Condition.keyword.in_(condition_keywords)))
        ).scalars().all()
        effects = (
            await session.execute(select(Effect).where(Effect.keyword.in_(effect_keywords)))
        ).scalars().all()
        if len(conditions) != len(condition_keywords) or len(effects) != len(effect_keywords):
            continue  # conditions/effects haven't been seeded yet

        session.add(
            WargearAbility(
                name=name,
                description=description,
                conditions=list(conditions),
                effects=list(effects),
            )
        )
    await session.commit()
