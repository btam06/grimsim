from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FactionUnit
from app.seeds.lookup import get_faction_id

FACTION_NAME = "Adeptus Mechanicus"

NAMES = [
    "Belisarius Cawl",
    "Thulia Ghuld",
    "Skitarii Marshall",
    "Sydonian Skatros",
    "Tech-priest Dominus",
    "Tech-priest Manipulus",
    "Technoarchaelogist",
    "Cybernetica Datasmith",
    "Skitarii Rangers",
    "Skitarii Vanguard",
    "Skorpius Dunerider",
    "Archaeopter Fusilave",
    "Archaeopter Stratoraptor",
    "Corpuscarii Electro-priests",
    "Fulgurite Electro-priests",
    "Hastarii Exterminators",
    "Hastarii Fusiliers",
    "Kataphron Breachers",
    "Kataphron Destroyers",
    "Pteraxii Skystalkers",
    "Pteraxii Sterylizors",
    "Servitor Battleclade",
    "Sicarian Infiltrators",
    "Sicarial Ruststalkers",
    "Serberys Raiders",
    "Serberys Sulphurhounds",
    "Archaeopter Transvector",
    "Ironstrider Balistarii",
    "Kastelan Robots",
    "Onager Dunecrawler",
    "Sydonian Dragoons With Radium Jezzails",
    "Sydonian Dragoons With Taser Lances",
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
