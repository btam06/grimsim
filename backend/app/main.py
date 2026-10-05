from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine, get_session
from app.models import Base, Item


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="grimsim API", lifespan=lifespan)


class ItemIn(BaseModel):
    name: str


class ItemOut(ItemIn):
    id: int

    class Config:
        from_attributes = True


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/items", response_model=list[ItemOut])
async def list_items(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item).order_by(Item.id))
    return result.scalars().all()


@app.post("/items", response_model=ItemOut, status_code=201)
async def create_item(item: ItemIn, session: AsyncSession = Depends(get_session)):
    db_item = Item(name=item.name)
    session.add(db_item)
    await session.commit()
    await session.refresh(db_item)
    return db_item
