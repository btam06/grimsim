from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FactionUnit
from app.seeds.lookup import get_faction_id

FACTION_NAME = "Imperial Agents"

NAMES = [
    "Callidus Assassin",
    "Culexus Assassin",
    "Eversor Assassin",
    "Inquisitor Coteaz",
    "Inquisitor Draxus",
    "Inquisitor Greyfax",
    "Vindicare Assassin",
    "Watch Captain Artemis",
    "Inquisitor Kroyle",
    "Inquisitor",
    "Ministorum Priest",
    "Navigator",
    "Rogue Trader Entourage",
    "Watch Master",
    "Aquila Kill Team",
    "Deathwatch Kill Team",
    "Imperial Navy Breachers",
    "Vigilant Squad",
    "Imperial Rhino",
    "Inquisitorial Chimera",
    "Sisters of Battle Immolator",
    "Exaction Squad",
    "Grey Knights Terminator Squad",
    "Inquisitorial Agents",
    "Sanctifiers",
    "Sisters of Battle Squad",
    "Subductor Squad",
    "Voidsmen-at-arms",
    "Corvus Blackstar",
]


async def seed(session: AsyncSession) -> None:
    faction_id = await get_faction_id(session, FACTION_NAME)
    if faction_id is None:
        return

    existing = set(
        (
            await session.execute(
                select(FactionUnit.name).where(FactionUnit.faction_id == faction_id)
            )
        )
        .scalars()
        .all()
    )
    missing = [
        FactionUnit(name=name, faction_id=faction_id) for name in NAMES if name not in existing
    ]
    if missing:
        session.add_all(missing)
        await session.commit()
