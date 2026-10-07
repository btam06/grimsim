from sqlalchemy.ext.asyncio import AsyncSession

from app.seeds import dispositions, factions

# To seed another table on startup: add a module here with a NAMES list and an
# async def seed(session) function (see dispositions.py / factions.py), then
# register its `seed` function below.
SEED_FUNCS = [
    dispositions.seed,
    factions.seed,
]


async def run_all(session: AsyncSession) -> None:
    for seed_func in SEED_FUNCS:
        await seed_func(session)
