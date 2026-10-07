from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Effect


async def test_list_effects(client: AsyncClient, session: AsyncSession):
    session.add(
        Effect(keyword="add_extra_hit", name="Add Extra Hit", description="One more hit")
    )
    await session.commit()

    response = await client.get("/effects")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["keyword"] == "add_extra_hit"
    assert body[0]["name"] == "Add Extra Hit"
    assert body[0]["description"] == "One more hit"


async def test_list_effects_empty(client: AsyncClient):
    response = await client.get("/effects")
    assert response.status_code == 200
    assert response.json() == []
