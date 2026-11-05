import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import async_session, engine
from app.engine import context, store
from app.models import Base
from app.routers import (
    agent,
    base_sizes,
    combat,
    conditions,
    datasheet_abilities,
    detachment_rules,
    detachments,
    dispositions,
    effects,
    enhancements,
    faction_abilities,
    faction_units,
    factions,
    games,
    keywords,
    lists,
    missions,
    ml,
    models,
    stratagems,
    terrain,
    units,
    users,
    wargear,
    wargear_abilities,
    weapon_abilities,
    weapons,
)
from app.migrations import run_all as run_migrations
from app.seeds import run_all as run_seeds


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        await run_migrations(session)
        await run_seeds(session)
    store.start()
    task = asyncio.create_task(_put_away_idle_games())
    yield
    task.cancel()


async def _put_away_idle_games() -> None:
    # Every minute: games left alone out of memory (see app/engine/store.py).
    while True:
        await asyncio.sleep(60)
        games.evict_idle(settings.idle_minutes * 60)


app = FastAPI(title="grimsim API", lifespan=lifespan)


@app.middleware("http")
async def game_requests(request, call_next):
    # Each request plays the game it loads (see app/engine/context.py) -
    # never the last request's - and one that changes it and fails leaves it
    # as it was.
    tracked = context.begin_request(changes=request.method not in ("GET", "HEAD", "OPTIONS"))
    try:
        response = await call_next(request)
    except Exception:
        context.end_request(tracked, failed=True)
        raise
    context.end_request(tracked, failed=response.status_code >= 400)
    return response


app.include_router(factions.router)
app.include_router(ml.router)
app.include_router(faction_units.router)
app.include_router(faction_abilities.router)
app.include_router(dispositions.router)
app.include_router(detachments.router)
app.include_router(detachment_rules.router)
app.include_router(stratagems.router)
app.include_router(enhancements.router)
app.include_router(keywords.router)
app.include_router(models.router)
app.include_router(base_sizes.router)
app.include_router(weapons.router)
app.include_router(wargear.router)
app.include_router(wargear_abilities.router)
app.include_router(units.router)
app.include_router(lists.router)
app.include_router(users.router)
app.include_router(missions.secondary_router)
app.include_router(missions.primary_router)
app.include_router(games.router)
app.include_router(agent.router)
app.include_router(weapon_abilities.router)
app.include_router(datasheet_abilities.router)
app.include_router(conditions.router)
app.include_router(effects.router)
app.include_router(combat.router)
app.include_router(terrain.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
