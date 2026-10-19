from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.models import Keyword, Stratagem, StratagemTiming

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


# Keywords a model needs (all of them) for these core stratagems to apply to
# it; any not listed apply to any model.
REQUIRED_KEYWORDS = {
    "Epic Challenge": ("CHARACTER",),
    "Grenade": ("GRENADES",),
    "Tank Shock": ("VEHICLE",),
    "Go to Ground": ("INFANTRY",),
    "Smokescreen": ("SMOKE",),
}


# When each core stratagem can be used in a game, as (phase, whose turn) pairs
# from the using player's point of view. Not listed means any time (e.g.
# Command Re-roll).
TIMINGS = {
    "Counter-offensive": [("fight", "either")],
    "Epic Challenge": [("fight", "either")],
    "Insane Bravery": [("command", "either")],
    "Grenade": [("shooting", "your_turn")],
    "Tank Shock": [("charge", "your_turn")],
    "Rapid Ingress": [("movement", "opponent_turn")],
    "Fire Overwatch": [("movement", "opponent_turn"), ("charge", "opponent_turn")],
    "Go to Ground": [("shooting", "opponent_turn")],
    "Smokescreen": [("shooting", "opponent_turn")],
    "Heroic Intervention": [("charge", "opponent_turn")],
}


async def seed(session: AsyncSession) -> None:
    # Must run after keywords.seed, since requirements are looked up by name.
    keywords_by_name = {
        k.name: k for k in (await session.execute(select(Keyword))).scalars().all()
    }
    existing = {
        s.name: s
        for s in (
            await session.execute(
                select(Stratagem)
                .options(selectinload(Stratagem.keywords), selectinload(Stratagem.timings))
                .where(Stratagem.is_core.is_(True))
            )
        )
        .scalars()
        .all()
    }

    changed = False
    for name, description, cp in CORE_ENTRIES:
        required = [
            keywords_by_name[k] for k in REQUIRED_KEYWORDS.get(name, ()) if k in keywords_by_name
        ]
        timings = [StratagemTiming(phase=phase, turn=turn) for phase, turn in TIMINGS.get(name, [])]
        stratagem = existing.get(name)
        if stratagem is None:
            session.add(
                Stratagem(
                    name=name,
                    description=description,
                    cp=cp,
                    is_core=True,
                    keywords=required,
                    timings=timings,
                )
            )
            changed = True
            continue
        # Seeded before core stratagems had keyword requirements/timings.
        if required and not stratagem.keywords:
            stratagem.keywords = required
            changed = True
        if timings and not stratagem.timings:
            stratagem.timings = timings
            changed = True

    if changed:
        await session.commit()
