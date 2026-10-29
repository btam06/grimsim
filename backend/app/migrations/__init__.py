from sqlalchemy.ext.asyncio import AsyncSession

from app.migrations import (
    core_rule_texts,
    core_stratagems,
    first_seat_nullable,
    hellfire_rounds_conditions,
    hull_boxes,
    kit_counts,
    reconnaissance_spelling,
    skitarii_marshal_spelling,
)

# Changes to databases made before something changed - a rename, different
# conditions for a seeded row, a column that can now be empty - that seeding
# and creating missing tables alone wouldn't make, since they only add what's
# missing (see app/seeds/__init__.py). They run at
# startup, before seeding, in this order. Each one checks whether it's needed
# and does nothing if not, so running them again (or on a new database) is
# harmless. Once every database is clean (e.g. in production), they can go.
#
# To add one: a module here with an async def run(session) function, added
# to MIGRATIONS below.
MIGRATIONS = [
    reconnaissance_spelling,
    hellfire_rounds_conditions,
    first_seat_nullable,
    skitarii_marshal_spelling,
    hull_boxes,
    kit_counts,
    core_rule_texts,
    core_stratagems,
]


async def run_all(session: AsyncSession) -> None:
    for migration in MIGRATIONS:
        await migration.run(session)
    await session.commit()
