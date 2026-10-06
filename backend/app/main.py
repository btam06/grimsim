from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import engine
from app.models import Base
from app.routers import datasheet_abilities, factions, models, units, weapon_abilities, weapons


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="grimsim API", lifespan=lifespan)
app.include_router(factions.router)
app.include_router(models.router)
app.include_router(weapons.router)
app.include_router(units.router)
app.include_router(weapon_abilities.router)
app.include_router(datasheet_abilities.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
