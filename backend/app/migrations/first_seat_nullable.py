from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Who goes first used to be chosen when a game was made (games.first_seat NOT
# NULL); it's now rolled off once everything is set up, so it's empty until
# then. A new database gets the nullable column from the model; an existing
# PostgreSQL one has the constraint dropped (SQLite databases are only made
# fresh, by the tests).


async def run(session: AsyncSession) -> None:
    if session.bind.dialect.name != "postgresql":
        return
    nullable = (
        await session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'games' AND column_name = 'first_seat'"
            )
        )
    ).scalar_one_or_none()
    if nullable == "NO":
        await session.execute(text("ALTER TABLE games ALTER COLUMN first_seat DROP NOT NULL"))
