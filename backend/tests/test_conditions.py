from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Condition


async def test_list_conditions(client: AsyncClient, session: AsyncSession):
    session.add(Condition(keyword="critical_hit", name="Critical Hit", description="A 6 to hit"))
    await session.commit()

    response = await client.get("/conditions")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["keyword"] == "critical_hit"
    assert body[0]["name"] == "Critical Hit"
    assert body[0]["description"] == "A 6 to hit"


async def test_list_conditions_empty(client: AsyncClient):
    response = await client.get("/conditions")
    assert response.status_code == 200
    assert response.json() == []
