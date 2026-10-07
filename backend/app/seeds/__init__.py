from sqlalchemy.ext.asyncio import AsyncSession

from app.seeds import dispositions, factions
from app.seeds.detachments import adeptus_mechanicus as adeptus_mechanicus_detachments
from app.seeds.faction_units import adeptus_mechanicus as adeptus_mechanicus_units

# To seed another table on startup: add a module here with a NAMES list and an
# async def seed(session) function (see dispositions.py / factions.py), then
# register its `seed` function below.
#
# Per-faction unit rosters live in app/seeds/faction_units/ (one file per
# faction, e.g. adeptus_mechanicus.py) since each needs its own NAMES list.
# Per-faction detachment rosters live in app/seeds/detachments/ the same way,
# each with an ENTRIES list of (name, disposition name, dp). To add another
# faction: add a module to the relevant directory following the same shape,
# then register it below — after dispositions.seed/factions.seed, since both
# look up rows by name.
SEED_FUNCS = [
    dispositions.seed,
    factions.seed,
    adeptus_mechanicus_units.seed,
    adeptus_mechanicus_detachments.seed,
]


async def run_all(session: AsyncSession) -> None:
    for seed_func in SEED_FUNCS:
        await seed_func(session)
