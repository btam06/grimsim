from httpx import AsyncClient

from app.models import Unit
from tests.test_deployment import _deployment, _game

# Units of the same datasheet in a list are numbered, to tell them apart.


async def test_units_of_the_same_datasheet_are_numbered(client: AsyncClient, session, tmp_path):
    units = {1: [("Rangers", 1, {}), ("Other", 1, {}), ("Onager", 1, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units)
    deployment = await _deployment(client, game["id"])
    first, second = sorted(u["unit_id"] for u in deployment["units"] if u["seat"] == 1)[:2]
    # (The test's units each have their own datasheet: make the second the
    # first's.)
    unit_a, unit_b = await session.get(Unit, first), await session.get(Unit, second)
    unit_b.faction_unit_id = unit_a.faction_unit_id
    await session.commit()
    session.expire_all()
    names = {u["unit_id"]: u["name"] for u in (await _deployment(client, game["id"]))["units"]}
    assert (names[first], names[second]) == ("Rangers 1", "Rangers 2")
    assert sorted(names.values()) == ["D", "Onager", "Rangers 1", "Rangers 2"]
