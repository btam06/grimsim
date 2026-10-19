import os
from collections.abc import AsyncGenerator
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Base, Faction


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as test_session:
            yield test_session

    app.dependency_overrides[get_session] = override_get_session

    async with test_session_factory() as test_session:
        yield test_session

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest_asyncio.fixture
async def faction_id(session: AsyncSession) -> int:
    faction = Faction(name="Test Faction")
    session.add(faction)
    await session.commit()
    return faction.id


@pytest_asyncio.fixture(autouse=True)
async def no_local_game_data(monkeypatch, tmp_path):
    # Datasheets and mission cards come from uncommitted local files (see
    # app/data/README.md); point the seeds at an empty folder so tests don't
    # depend on whether those files exist.
    from app.seeds import data_files

    monkeypatch.setattr(data_files, "DATA_DIR", tmp_path / "no-data")


@pytest_asyncio.fixture
async def fixture_game_data(monkeypatch):
    # A small made-up datasheet ("Test Squad", in tests/fixtures/data) to seed.
    from app.seeds import data_files

    monkeypatch.setattr(data_files, "DATA_DIR", Path(__file__).parent / "fixtures" / "data")
