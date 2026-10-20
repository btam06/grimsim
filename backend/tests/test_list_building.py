import pytest
from httpx import AsyncClient


class Army:
    # Builds factions, keywords, models and lists through the API.

    def __init__(self, client: AsyncClient):
        self.client = client
        self.factions: dict[str, int] = {}
        self.keywords: dict[str, int] = {}
        self.units_made = 0

    async def faction(self, name: str) -> int:
        if name not in self.factions:
            response = await self.client.post("/factions", json={"name": name})
            self.factions[name] = response.json()["id"]
        return self.factions[name]

    async def keyword(self, name: str) -> int:
        if name not in self.keywords:
            response = await self.client.post("/keywords", json={"name": name})
            self.keywords[name] = response.json()["id"]
        return self.keywords[name]

    async def model(self, faction: str, name: str, *keywords: str) -> int:
        response = await self.client.post(
            "/models",
            json={
                "name": name,
                "faction_id": await self.faction(faction),
                "save": 4,
                "toughness": 4,
                "oc": 1,
                "movement": 6,
                "wounds": 3,
                "leadership": 7,
                "keyword_ids": [await self.keyword(k) for k in keywords],
            },
        )
        assert response.status_code == 201
        return response.json()["id"]

    async def list(self, faction: str, points_limit: int = 2000, detachment_ids=()) -> int:
        response = await self.client.post(
            "/lists",
            json={
                "name": "List",
                "points_limit": points_limit,
                "faction_id": await self.faction(faction),
                "detachment_ids": list(detachment_ids),
            },
        )
        return response.json()["id"]

    async def unit(self, list_id, faction: str, model_id: int, points=100, enhancement_id=None):
        self.units_made += 1
        faction_unit = await self.client.post(
            "/faction-units",
            json={"name": f"Unit {self.units_made}", "faction_id": await self.faction(faction)},
        )
        return await self.client.post(
            "/units",
            json={
                "faction_unit_id": faction_unit.json()["id"],
                "points": points,
                "list_id": list_id,
                "unit_models": [{"model_id": model_id, "enhancement_id": enhancement_id}],
            },
        )


@pytest.fixture
def army(client: AsyncClient) -> Army:
    return Army(client)


# --- Imperium: Imperial Agents and Imperial Knights join Imperium lists ---


@pytest.mark.parametrize(
    "ally,keywords",
    [
        ("Imperial Agents", ("CHARACTER",)),
        ("Imperial Agents", ("RETINUE", "INFANTRY")),
        ("Imperial Agents", ("REQUISITIONED", "VEHICLE")),
        ("Imperial Knights", ("TITANIC", "VEHICLE")),
        ("Imperial Knights", ("ARMIGER", "VEHICLE")),
    ],
)
@pytest.mark.parametrize("host", ["Adeptus Mechanicus", "Space Marines", "Adeptus Titanicus"])
async def test_imperial_allies_join_imperium_lists(army: Army, host, ally, keywords):
    list_id = await army.list(host)
    # No need for the rest of the list to be anything in particular.
    trooper = await army.model(host, "Trooper", "INFANTRY")
    assert (await army.unit(list_id, host, trooper)).status_code == 201
    model = await army.model(ally, "Ally", *keywords)
    response = await army.unit(list_id, ally, model)
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "ally,keywords",
    [("Imperial Agents", ("INFANTRY", "IMPERIUM")), ("Imperial Knights", ("VEHICLE", "IMPERIUM"))],
)
async def test_imperial_allies_need_one_of_their_keywords(army: Army, ally, keywords):
    list_id = await army.list("Adeptus Mechanicus")
    model = await army.model(ally, "Not Eligible", *keywords)
    response = await army.unit(list_id, ally, model)
    assert response.status_code == 400
    assert "can't be included" in response.json()["detail"]


@pytest.mark.parametrize(
    "ally,keyword", [("Imperial Agents", "CHARACTER"), ("Imperial Knights", "TITANIC")]
)
async def test_imperial_allies_only_join_imperium_lists(army: Army, ally, keyword):
    list_id = await army.list("Orks")
    model = await army.model(ally, "Ally", keyword, "IMPERIUM")
    assert (await army.unit(list_id, ally, model)).status_code == 400


async def test_imperial_agents_and_knights_join_each_others_lists(army: Army):
    knights = await army.list("Imperial Knights")
    agent = await army.model("Imperial Agents", "Inquisitor", "CHARACTER")
    assert (await army.unit(knights, "Imperial Agents", agent)).status_code == 201
    agents = await army.list("Imperial Agents")
    armiger = await army.model("Imperial Knights", "Armiger", "ARMIGER")
    assert (await army.unit(agents, "Imperial Knights", armiger)).status_code == 201


async def test_units_from_other_factions_are_rejected(army: Army):
    list_id = await army.list("Adeptus Mechanicus")
    boy = await army.model("Orks", "Boy", "INFANTRY")
    response = await army.unit(list_id, "Orks", boy)
    assert response.status_code == 400
    assert "Adeptus Mechanicus list" in response.json()["detail"]


async def test_units_outside_a_list_are_not_checked(army: Army):
    boy = await army.model("Orks", "Boy", "INFANTRY")
    assert (await army.unit(None, "Orks", boy)).status_code == 201


# --- Drukhari: Corsairs and Travelling Players ---


async def test_harlequins_and_anhrathe_join_a_drukhari_list(army: Army):
    list_id = await army.list("Drukhari")
    for keyword in ("HARLEQUINS", "ANHRATHE"):
        model = await army.model("Aeldari", keyword.title(), "AELDARI", keyword)
        response = await army.unit(list_id, "Aeldari", model, points=200)
        assert response.status_code == 201, response.text


async def test_other_aeldari_cannot_join_a_drukhari_list(army: Army):
    list_id = await army.list("Drukhari")
    guardian = await army.model("Aeldari", "Guardian", "AELDARI", "ASURYANI", "INFANTRY")
    assert (await army.unit(list_id, "Aeldari", guardian)).status_code == 400


async def test_harlequins_only_join_drukhari_lists(army: Army):
    list_id = await army.list("Orks")
    player = await army.model("Aeldari", "Player", "AELDARI", "HARLEQUINS")
    assert (await army.unit(list_id, "Aeldari", player)).status_code == 400


@pytest.mark.parametrize("points_limit,cap", [(1000, 250), (2000, 500)])
async def test_harlequins_and_anhrathe_points_are_capped(army: Army, points_limit, cap):
    list_id = await army.list("Drukhari", points_limit=points_limit)
    player = await army.model("Aeldari", "Player", "AELDARI", "HARLEQUINS")
    corsair = await army.model("Aeldari", "Corsair", "AELDARI", "ANHRATHE")
    assert (await army.unit(list_id, "Aeldari", player, points=cap - 50)).status_code == 201
    # Together over the cap, whichever of the two keywords.
    response = await army.unit(list_id, "Aeldari", corsair, points=51)
    assert response.status_code == 400
    assert f"at most {cap} pts" in response.json()["detail"]
    assert (await army.unit(list_id, "Aeldari", corsair, points=50)).status_code == 201


async def test_editing_a_unit_counts_its_new_points_not_its_old_ones(army: Army):
    list_id = await army.list("Drukhari", points_limit=2000)
    player = await army.model("Aeldari", "Player", "AELDARI", "HARLEQUINS")
    unit = (await army.unit(list_id, "Aeldari", player, points=500)).json()
    response = await army.client.put(
        f"/units/{unit['id']}",
        json={
            "faction_unit_id": unit["faction_unit_id"],
            "points": 450,
            "list_id": list_id,
            "unit_models": [{"model_id": player}],
        },
    )
    assert response.status_code == 200, response.text


async def test_harlequins_cannot_be_given_enhancements(army: Army):
    drukhari = await army.faction("Drukhari")
    detachment = (
        await army.client.post(
            "/detachments", json={"name": "Realspace Raid", "faction_id": drukhari, "dp": 2}
        )
    ).json()["id"]
    relic = (
        await army.client.post(
            "/enhancements",
            json={
                "name": "Relic",
                "points": 10,
                "kind": "enhancement",
                "detachment_id": detachment,
            },
        )
    ).json()["id"]
    list_id = await army.list("Drukhari", detachment_ids=[detachment])
    archon = await army.model("Drukhari", "Archon", "DRUKHARI", "CHARACTER")
    troupe_master = await army.model("Aeldari", "Troupe Master", "HARLEQUINS", "CHARACTER")

    available = await army.client.get(
        "/enhancements/available", params={"list_id": list_id, "model_id": troupe_master}
    )
    assert available.json() == []
    response = await army.unit(list_id, "Aeldari", troupe_master, enhancement_id=relic)
    assert response.status_code == 400
    assert "ally rule" in response.json()["detail"]
    # A Drukhari CHARACTER can take it.
    assert (await army.unit(list_id, "Drukhari", archon, enhancement_id=relic)).status_code == 201


# --- what the unit form is offered ---


async def test_eligible_lists_own_faction_and_allowed_allies(army: Army):
    list_id = await army.list("Drukhari")
    wych = await army.model("Drukhari", "Wych", "DRUKHARI", "INFANTRY")
    player = await army.model("Aeldari", "Player", "AELDARI", "HARLEQUINS")
    await army.model("Aeldari", "Guardian", "AELDARI", "ASURYANI")
    await army.model("Orks", "Boy", "INFANTRY")
    for faction in ("Drukhari", "Aeldari", "Orks"):
        await army.client.post(
            "/faction-units", json={"name": faction, "faction_id": await army.faction(faction)}
        )

    eligible = (await army.client.get(f"/lists/{list_id}/eligible")).json()
    assert set(eligible["model_ids"]) == {wych, player}
    faction_units = {
        fu["id"]: fu["name"] for fu in (await army.client.get("/faction-units")).json()
    }
    assert {faction_units[i] for i in eligible["faction_unit_ids"]} == {"Drukhari", "Aeldari"}


async def test_eligible_for_a_missing_list_is_404(client: AsyncClient):
    assert (await client.get("/lists/9999/eligible")).status_code == 404


async def test_imperial_allies_cannot_be_given_enhancements(army: Army):
    mechanicus = await army.faction("Adeptus Mechanicus")
    detachment = (
        await army.client.post(
            "/detachments", json={"name": "Cohort", "faction_id": mechanicus, "dp": 2}
        )
    ).json()["id"]
    relic = (
        await army.client.post(
            "/enhancements",
            json={
                "name": "Relic",
                "points": 10,
                "kind": "enhancement",
                "detachment_id": detachment,
            },
        )
    ).json()["id"]
    list_id = await army.list("Adeptus Mechanicus", detachment_ids=[detachment])
    inquisitor = await army.model("Imperial Agents", "Inquisitor", "CHARACTER", "IMPERIUM")
    dominus = await army.model("Adeptus Mechanicus", "Dominus", "CHARACTER", "IMPERIUM")

    available = await army.client.get(
        "/enhancements/available", params={"list_id": list_id, "model_id": inquisitor}
    )
    assert available.json() == []
    response = await army.unit(list_id, "Imperial Agents", inquisitor, enhancement_id=relic)
    assert response.status_code == 400
    assert "ally rule" in response.json()["detail"]
    assert (
        await army.unit(list_id, "Adeptus Mechanicus", dominus, enhancement_id=relic)
    ).status_code == 201
