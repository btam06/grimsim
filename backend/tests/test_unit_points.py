import json

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PointsSource, UnitPointCost, UnitWargearCost
from app.services import munitorum, unit_points
from app.services.munitorum import FactionPage, UnitCost, UnitEntry, WargearCost


# --- parsing a page ------------------------------------------------------------


def _el(tag, children, cls="", key=None):
    return ["$", tag, key, {"className": cls, "children": children}]


def _section(heading, lines):
    return _el("div", [
        _el("div", heading, "bg-slate-200 px-1"),
        _el("ul", [_el("li", [_el("span", label), points]) for label, points in lines], "leaders"),
    ], "space-y-1")


def _page(rows: dict) -> str:
    # A page whose RSC payload is these rows (as the site sends them: one
    # push of "<id>:<json>" lines).
    stream = "".join(f"{k}:{json.dumps(v)}\n" for k, v in rows.items())
    return f"<html><script>self.__next_f.push({json.dumps([1, stream])})</script></html>"


def test_parses_units_from_the_rsc_payload():
    card = "flex flex-col space-y-1 m-1 print:break-inside-avoid-page"
    rows = {
        "0": _el("main", [
            _el("h1", "CHAOS KNIGHTS"),
            _el("div", "v1.6"),
            _el("div", [
                "$L1",
                _section("YOUR 1ST UNIT COSTS", [("1 model", "$L2")]),
                _section("YOUR 2ND + UNIT COSTS", [("1 model", _el("span", "390 pts"))]),
                _el("div", [
                    _el("div", [_el("span", "WARGEAR OPTIONS")], "flex justify-between px-1"),
                    _el("ul", [_el("li", [_el("span", "per Despoiler gatling cannon"),
                                          _el("span", "25 pts")])], "leaders"),
                ], "space-y-1"),
            ], card, key="a"),
            _el("div", [
                _el("div", "WOLF GUARD HEADTAKERS", "bg-slate-500 text-xl"),
                _section("YOUR UNIT COSTS", [
                    ("3 Wolf Guard Headtakers, 3 Hunting Wolves", _el("span", "115 pts")),
                    ("1 model", _el("span", "2,100 pts")),
                    ("+ 1 Tidewall Defence Platform", _el("span", "20 pts")),
                ]),
                _section("LEADER", [("Some unit", "")]),
            ], card, key="b"),
        ]),
        "1": _el("div", "KNIGHT DESPOILER", "bg-slate-500 text-xl"),
        "2": _el("span", "360 pts"),
    }
    page = munitorum.parse_faction("chaos-knights", _page(rows))

    assert page.title == "CHAOS KNIGHTS" and page.version == "v1.6"
    despoiler, headtakers = page.units
    assert despoiler.name == "KNIGHT DESPOILER"
    assert despoiler.costs == [UnitCost(1, 1, 360), UnitCost(2, 1, 390)]
    assert despoiler.wargear == [WargearCost("Despoiler gatling cannon", 25)]
    assert headtakers.costs == [
        UnitCost(1, 6, 115, [(3, "Wolf Guard Headtakers"), (3, "Hunting Wolves")]),
        UnitCost(1, 1, 2100),
    ]
    assert headtakers.wargear == [WargearCost("Tidewall Defence Platform", 20)]
    assert page.unparsed == []


def test_requisition_threshold_from_heading():
    assert munitorum.from_copy("YOUR UNIT COSTS") == 1
    assert munitorum.from_copy("YOUR 1ST TO 2ND UNITS COST") == 1
    assert munitorum.from_copy("YOUR 3RD + UNIT COSTS") == 3
    assert munitorum.from_copy("YOUR 4TH + UNIT COSTS") == 4


def test_faction_slugs_from_the_index():
    index = '<a href="/en/orks">x</a><a href="/en/necrons"></a><a href="/en/orks"></a><a href="/de/x">'
    assert munitorum.faction_slugs(index) == ["orks", "necrons"]


# --- pricing ---------------------------------------------------------------------


def _cost(from_copy, models, points, composition=None):
    return UnitPointCost(from_copy=from_copy, models=models, points=points, composition=composition)


def test_unit_cost_by_size_and_requisition_threshold():
    costs = [_cost(1, 5, 95), _cost(1, 10, 190), _cost(3, 5, 105), _cost(3, 10, 200)]
    five, seven = ["Marine"] * 5, ["Marine"] * 7
    assert unit_points.unit_cost(costs, 1, five) == 95
    # Between two sizes: the larger one's.
    assert unit_points.unit_cost(costs, 2, seven) == 190
    assert unit_points.unit_cost(costs, 3, five) == 105
    assert unit_points.unit_cost(costs, 5, seven) == 200
    assert unit_points.unit_cost([], 1, five) is None


def test_unit_cost_by_named_composition():
    costs = [
        _cost(1, 3, 85, [[3, "Wolf Guard Headtakers"]]),
        _cost(1, 6, 115, [[3, "Wolf Guard Headtakers"], [3, "Hunting Wolves"]]),
        _cost(1, 6, 170, [[6, "Wolf Guard Headtakers"]]),
    ]
    with_wolves = ["Wolf Guard Headtaker"] * 3 + ["Hunting Wolf"] * 3
    assert unit_points.unit_cost(costs, 1, with_wolves) == 115
    assert unit_points.unit_cost(costs, 1, ["Wolf Guard Headtaker"] * 6) == 170
    assert unit_points.unit_cost(costs, 1, ["Wolf Guard Headtaker"] * 4) == 170


def test_wargear_cost_per_item():
    wargear = [UnitWargearCost(name="Despoiler gatling cannon", points=25)]
    items = ["Knight Despoiler", "Despoiler gatling cannon", "Despoiler gatling cannon", "Meltagun"]
    assert unit_points.wargear_cost(wargear, items) == 50


# --- importing and the API ----------------------------------------------------------


def _manual(*units: UnitEntry, title="TEST FACTION", slug="test-faction") -> FactionPage:
    return FactionPage(slug=slug, title=title, version="v1.6", units=list(units))


def test_matching_own_page_then_other_pages_then_near():
    own = _manual(UnitEntry("SICARIAN RUSTSTALKERS", [UnitCost(1, 5, 75)]))
    other = _manual(
        UnitEntry("DEATHWATCH TERMINATOR SQUAD", [UnitCost(1, 5, 200)]),
        title="DEATHWATCH", slug="deathwatch",
    )
    ours = [
        ("Test Faction", "Sicarial Ruststalkers"),
        ("Test Faction", "Deathwatch Terminator Squad"),
        ("Test Faction", "Exorcist"),
    ]
    found, report = unit_points.match_entries([own, other], ours)
    assert found[ours[0]].how.startswith("near")
    assert found[ours[1]].page.slug == "deathwatch"
    assert report.unmatched == [("Test Faction", "Exorcist")]


async def _setup(client: AsyncClient, faction_id: int) -> tuple[int, int, int, int]:
    model = {
        "faction_id": faction_id, "save": 3, "toughness": 4, "oc": 2,
        "movement": 6, "wounds": 2, "leadership": 7,
    }
    model_id = (await client.post("/models", json={**model, "name": "Marine"})).json()["id"]
    weapon_id = (
        await client.post("/weapons", json={
            "name": "Meltagun", "model_id": model_id, "damage": "1", "range": 12,
            "strength": 9, "ap": -4, "attacks": "1", "skill": 3,
        })
    ).json()["id"]
    unit_id = (
        await client.post("/faction-units", json={"name": "Tactical Squad", "faction_id": faction_id})
    ).json()["id"]
    detachment_id = (
        await client.post("/detachments", json={"name": "D", "faction_id": faction_id, "dp": 2})
    ).json()["id"]
    list_id = (
        await client.post("/lists", json={
            "name": "L", "points_limit": 2000, "faction_id": faction_id,
            "detachment_ids": [detachment_id],
        })
    ).json()["id"]
    return model_id, weapon_id, unit_id, list_id


async def test_units_are_priced_from_imported_costs(
    client: AsyncClient, session: AsyncSession, faction_id: int
):
    model_id, weapon_id, faction_unit_id, list_id = await _setup(client, faction_id)
    entry = UnitEntry(
        "TACTICAL SQUAD",
        [UnitCost(1, 5, 80), UnitCost(1, 10, 160), UnitCost(2, 5, 90), UnitCost(2, 10, 180)],
        [WargearCost("Meltagun", 5)],
    )
    report = await unit_points.import_pages(session, [_manual(entry)])
    assert report.updated == [("Test Faction", "Tactical Squad", "exact")]
    source = await session.get(PointsSource, faction_unit_id)
    assert source.page == "test-faction" and source.version == "v1.6"

    def payload(n, melta=0, **extra):
        models = [{"model_id": model_id, "weapon_ids": [weapon_id] if i < melta else []} for i in range(n)]
        return {"faction_unit_id": faction_unit_id, "list_id": list_id, "unit_models": models, **extra}

    # (Given points are ignored for a datasheet with costs.)
    first = await client.post("/units", json=payload(5, melta=1, points=1))
    assert first.status_code == 201, first.text
    assert first.json()["points"] == 85
    second = (await client.post("/units", json=payload(7))).json()
    assert second["points"] == 180  # the 2nd+ tier, 10-model size

    # Deleting the first makes the second the first copy.
    assert (await client.delete(f"/units/{first.json()['id']}")).status_code == 204
    units = {u["id"]: u for u in (await client.get("/units")).json()}
    assert units[second["id"]]["points"] == 160

    # Importing again replaces the costs, not adds to them.
    await unit_points.import_pages(session, [_manual(entry)])
    rows = (
        await session.execute(
            select(UnitPointCost).where(UnitPointCost.faction_unit_id == faction_unit_id)
        )
    ).scalars().all()
    assert len(rows) == 4


async def test_datasheet_without_costs_needs_its_points(client: AsyncClient, faction_id: int):
    _, _, faction_unit_id, list_id = await _setup(client, faction_id)
    body = {"faction_unit_id": faction_unit_id, "list_id": list_id, "unit_models": []}
    assert (await client.post("/units", json=body)).status_code == 400
    response = await client.post("/units", json={**body, "points": 120})
    assert response.status_code == 201
    assert response.json()["points"] == 120


async def test_attached_leaders_are_priced_from_their_own_datasheets(
    client: AsyncClient, session: AsyncSession, faction_id: int
):
    marine_id, _, faction_unit_id, list_id = await _setup(client, faction_id)
    leader = {
        "name": "Captain", "faction_id": faction_id, "save": 3, "toughness": 4, "oc": 1,
        "movement": 6, "wounds": 5, "leadership": 6, "is_leader": True,
    }
    captain_id = (await client.post("/models", json=leader)).json()["id"]
    await client.post("/faction-units", json={"name": "Captain", "faction_id": faction_id})
    squad = UnitEntry("TACTICAL SQUAD", [UnitCost(1, 5, 80), UnitCost(1, 10, 160)])
    await unit_points.import_pages(session, [_manual(squad)])

    body = {
        "faction_unit_id": faction_unit_id, "list_id": list_id,
        "unit_models": [{"model_id": marine_id}] * 5 + [{"model_id": captain_id}],
    }
    # The Captain's datasheet has no costs yet: priced by hand.
    assert (await client.post("/units", json=body)).status_code == 400

    captain = UnitEntry("CAPTAIN", [UnitCost(1, 1, 75)])
    await unit_points.import_pages(session, [_manual(squad, captain)])
    response = await client.post("/units", json=body)
    assert response.status_code == 201, response.text
    # 5 Marines (not 6: the 10-model size) and the Captain.
    assert response.json()["points"] == 80 + 75
