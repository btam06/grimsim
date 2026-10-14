from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stratagem

# (name, description, cp) - core stratagems, usable by any army regardless of
# detachment. Descriptive only for now: none of them have conditions/effects
# for the combat engine to key off, though one can be added via the API.
CORE_ENTRIES = [
    (
        "Command Re-roll",
        "Re-roll one hit roll, wound roll, damage roll, saving throw, advance roll, "
        "charge roll, or the number of attacks made by a weapon.",
        1,
    ),
    (
        "Counter-offensive",
        "After an enemy unit has fought, select one of your units in engagement range "
        "to fight next.",
        2,
    ),
    (
        "Epic Challenge",
        "A CHARACTER's melee attacks gain Precision until the end of the phase.",
        1,
    ),
    (
        "Insane Bravery",
        "A unit automatically passes a Battle-shock test.",
        1,
    ),
    (
        "Grenade",
        "A GRENADES unit rolls six D6 against a nearby enemy unit, inflicting a mortal "
        "wound for each 4+.",
        1,
    ),
    (
        "Tank Shock",
        "After a VEHICLE ends a charge move, roll D6 equal to its Toughness, inflicting "
        "a mortal wound on the target for each 5+.",
        1,
    ),
    (
        "Rapid Ingress",
        "At the end of the opponent's Movement phase, set up a unit from Reserves.",
        1,
    ),
    (
        "Fire Overwatch",
        "Shoot at an enemy unit that moved or charged nearby, hitting only on unmodified 6s.",
        1,
    ),
    (
        "Go to Ground",
        "An INFANTRY unit targeted by a ranged attack gains a 6+ invulnerable save and "
        "the Benefit of Cover.",
        1,
    ),
    (
        "Smokescreen",
        "A SMOKE unit targeted by a ranged attack gains the Benefit of Cover and Stealth.",
        1,
    ),
    (
        "Heroic Intervention",
        "After an enemy unit ends a charge move nearby, one of your units can declare "
        "a charge against it.",
        2,
    ),
]


async def seed(session: AsyncSession) -> None:
    existing = set(
        (
            await session.execute(select(Stratagem.name).where(Stratagem.is_core.is_(True)))
        )
        .scalars()
        .all()
    )

    missing = [
        Stratagem(name=name, description=description, cp=cp, is_core=True)
        for name, description, cp in CORE_ENTRIES
        if name not in existing
    ]

    if missing:
        session.add_all(missing)
        await session.commit()
