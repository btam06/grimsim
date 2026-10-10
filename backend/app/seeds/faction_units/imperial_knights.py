from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FactionUnit
from app.seeds.lookup import get_faction_id

FACTION_NAME = "Imperial Knights"

NAMES = [
    "Sir Hekhtur",
    "Canis Rex",
    "Skitarii Marshal",
    "Tech-priest Dominus",
    "Tech-priest Manipulus",
    "Knight Destrier",
    "Knight Castellan",
    "Knight Crusader",
    "Knight Defender",
    "Knight Errant",
    "Knight Gallant",
    "Knight Paladin",
    "Knight Preceptor",
    "Knight Valiant",
    "Knight Warden",
    "Cerastus Knight Acheron",
    "Cerastus Knight Atrapos",
    "Cerastus Knight Castigator",
    "Cerastus Knight Lancer",
    "Questoris Knight Magaera",
    "Questoris Knight Styrix",
    "Skitarii Rangers",
    "Skitarii Vanguard",
    "Acastus Knight Asterius",
    "Acastus Knight Porphyrion",
    "Armiger Helverin",
    "Armiger Warglaive",
    "Armiger Moirax",
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
