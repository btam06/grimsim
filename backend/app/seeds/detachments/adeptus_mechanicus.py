from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Detachment
from app.seeds.lookup import get_dispositions_by_name, get_faction_id

FACTION_NAME = "Adeptus Mechanicus"

# (name, disposition name, dp)
ENTRIES = [
    ("Haloscreed Battle Clade", "Priority Assets", 3),
    ("Eradication Cohort", "Purge the Foe", 2),
    ("Data-Psalm Conclave", "Disruption", 2),
    ("Explorator Maniple", "Priority Assets", 2),
    ("Skitarii Hunter Cohort", "Reconnaisance", 2),
    ("Cohort Cybernetica", "Take and Hold", 1),
    ("Rad-Zone Corps", "Take and Hold", 2),
    ("Luminen Auto-choir", "Disruption", 1),
    ("Lords of the Forge", "Priority Assets", 2),
    ("Cohort Acquisitus", "Reconnaisance", 1),
]


async def seed(session: AsyncSession) -> None:
    faction_id = await get_faction_id(session, FACTION_NAME)
    if faction_id is None:
        return

    dispositions_by_name = await get_dispositions_by_name(session)

    existing = set(
        (
            await session.execute(
                select(Detachment.name).where(Detachment.faction_id == faction_id)
            )
        )
        .scalars()
        .all()
    )

    missing = []
    for name, disposition_name, dp in ENTRIES:
        if name in existing:
            continue
        disposition = dispositions_by_name.get(disposition_name)
        missing.append(
            Detachment(
                name=name,
                faction_id=faction_id,
                dp=dp,
                dispositions=[disposition] if disposition else [],
            )
        )

    if missing:
        session.add_all(missing)
        await session.commit()
