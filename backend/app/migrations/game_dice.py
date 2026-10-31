from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import dice

# Games now have their own seeded dice (games.rng_seed and games.rng_rolls -
# see app/services/dice.py). A new database gets the columns from the model;
# an existing PostgreSQL one has them added, each game given a seed of its own
# (SQLite databases are only made fresh, by the tests).


async def run(session: AsyncSession) -> None:
    if session.bind.dialect.name != "postgresql":
        return
    present = (
        await session.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'games' AND column_name = 'rng_seed'"
            )
        )
    ).scalar_one_or_none()
    if present:
        return
    await session.execute(text("ALTER TABLE games ADD COLUMN rng_seed BIGINT"))
    await session.execute(
        text("ALTER TABLE games ADD COLUMN rng_rolls INTEGER NOT NULL DEFAULT 0")
    )
    ids = (await session.execute(text("SELECT id FROM games"))).scalars().all()
    for game_id in ids:
        await session.execute(
            text("UPDATE games SET rng_seed = :seed WHERE id = :id"),
            {"seed": dice.new_seed(), "id": game_id},
        )
    await session.execute(text("ALTER TABLE games ALTER COLUMN rng_seed SET NOT NULL"))
