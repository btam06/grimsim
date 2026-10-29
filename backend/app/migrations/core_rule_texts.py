from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DatasheetAbility, WeaponAbility
from app.seeds import datasheet_abilities, weapon_abilities

# Core abilities' text rewritten from the 11th edition Core Rules PDF (e.g.
# Deep Strike: more than 8" from enemy units, even in the opponent's
# deployment zone): seeding only fills in missing rows, so existing ones keep
# the old wording. Bring each core datasheet ability's and weapon ability's
# description in line with the seed data's.


async def run(session: AsyncSession) -> None:
    for model, entries in (
        (DatasheetAbility, datasheet_abilities.CORE_ENTRIES),
        (WeaponAbility, weapon_abilities.ENTRIES),
    ):
        texts = {entry[0]: entry[1] for entry in entries}
        rows = (await session.execute(select(model).where(model.name.in_(texts)))).scalars()
        for row in rows:
            if row.description != texts[row.name]:
                row.description = texts[row.name]
