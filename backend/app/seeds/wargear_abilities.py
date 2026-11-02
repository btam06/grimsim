from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.conditions import ALWAYS
from app.combat_rules.effects import IGNORE_COVER, INVULNERABLE_4, INVULNERABLE_5
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
        # A pre-battle move (e.g. an Orbital Comms Array - see
        # app/services/in_game/scouts.py).
        "Scouts 6\"",
        "The bearer's unit has Scouts 6\": at the start of the first battle round, before the "
        "first turn begins, it can make a Normal move of up to 6\".",
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
