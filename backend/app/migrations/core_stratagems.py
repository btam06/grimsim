from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Stratagem
from app.seeds import stratagems as stratagem_seeds

# The core stratagems as the 11th edition Core Rules PDF has them (15.02-15.12):
# Grenade, Tank Shock and Counter-offensive are renamed, Go to Ground is gone,
# and the rest have new costs, timings, targets and text. Seeding only fills
# in what's missing, so each core stratagem's cost and text are brought in
# line with stratagems.json, and its keyword requirements and timings
# cleared for the seed to fill in again. Go to Ground goes, unless a game has
# used it.
RENAMED = {
    "Grenade": "Explosives",
    "Tank Shock": "Crushing Impact",
    "Counter-offensive": "Counteroffensive",
}
REMOVED = "Go to Ground"


async def run(session: AsyncSession) -> None:
    try:
        entries = {e["name"]: e for e in stratagem_seeds.load() if e.get("core")}
    except FileNotFoundError:
        return
    core = {
        s.name: s
        for s in (
            await session.execute(
                select(Stratagem)
                .options(
                    selectinload(Stratagem.keywords),
                    selectinload(Stratagem.excluded_keywords),
                    selectinload(Stratagem.keyword_option_links),
                    selectinload(Stratagem.timings),
                )
                .where(Stratagem.is_core)
            )
        ).scalars()
    }
    for old, new in RENAMED.items():
        if old in core and new not in core and new in entries:
            core[new] = core.pop(old)
            core[new].name = new
    removed = core.pop(REMOVED, None)
    if removed is not None and REMOVED not in entries:
        if not await _used_in_old_games(session, removed.id):
            await session.delete(removed)
    for name, stratagem in core.items():
        entry = entries.get(name)
        if entry is None:
            continue
        timings = sorted((t["phase"], t["turn"]) for t in entry.get("timings", []))
        if (
            stratagem.cp == entry["cp"]
            and stratagem.description == entry.get("description")
            and sorted((t.phase, t.turn) for t in stratagem.timings) == timings
            and sorted(k.name for k in stratagem.keywords) == sorted(entry.get("keywords", []))
            and sorted(k.name for k in stratagem.excluded_keywords)
            == sorted(entry.get("excluded_keywords", []))
            and len(stratagem.keyword_option_links)
            == sum(len(o) for o in entry.get("keyword_options", []))
        ):
            continue
        stratagem.cp = entry["cp"]
        stratagem.description = entry.get("description")
        stratagem.keywords = []
        stratagem.excluded_keywords = []
        stratagem.keyword_option_links = []
        stratagem.timings = []
    await session.flush()


async def _used_in_old_games(session: AsyncSession, stratagem_id: int) -> bool:
    # Whether a game from when games were kept in the database (they're now
    # played in memory - see app/engine/) used it: its old table may still
    # be there, pointing at it.
    if session.bind.dialect.name != "postgresql":
        return False
    table = (await session.execute(text("SELECT to_regclass('game_stratagem_uses')"))).scalar()
    if table is None:
        return False
    used = await session.execute(
        text("SELECT 1 FROM game_stratagem_uses WHERE stratagem_id = :id LIMIT 1"),
        {"id": stratagem_id},
    )
    return used.first() is not None
