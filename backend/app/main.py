from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import async_session, engine
from app.models import Base
from app.routers import (
    datasheet_abilities,
    detachments,
    dispositions,
    factions,
    lists,
    models,
    units,
    wargear,
    weapon_abilities,
    weapons,
)
from app.seeds import run_all as run_seeds


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        await run_seeds(session)
    yield


app = FastAPI(title="grimsim API", lifespan=lifespan)
app.include_router(factions.router)
app.include_router(dispositions.router)
app.include_router(detachments.router)
app.include_router(models.router)
app.include_router(weapons.router)
app.include_router(wargear.router)
app.include_router(units.router)
app.include_router(lists.router)
app.include_router(weapon_abilities.router)
app.include_router(datasheet_abilities.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
