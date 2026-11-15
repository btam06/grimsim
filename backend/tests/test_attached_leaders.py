from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.engine import loader
from app.migrations import attached_leaders
from app.models import (
    ArmyList,
    Detachment,
    FactionUnit,
    LeaderBodyguard,
    ListWarlord,
    Model,
    Unit,
    UnitModel,
)


def _model(faction_id: int, name: str, **flags) -> Model:
    return Model(
        name=name, faction_id=faction_id, save=3, toughness=4, oc=1, movement=6,
        wounds=2, leadership=6, **flags,
    )


async def _list(session: AsyncSession, faction_id: int) -> ArmyList:
    detachment = Detachment(name="D", faction_id=faction_id, dp=2)
    army_list = ArmyList(name="L", points_limit=2000, faction_id=faction_id)
    army_list.detachments = [detachment]
    session.add(army_list)
    await session.flush()
    return army_list


async def test_migration_splits_leaders_out_of_their_units(
    session: AsyncSession, faction_id: int
):
    army_list = await _list(session, faction_id)
    marine = _model(faction_id, "Intercessor")
    captain = _model(faction_id, "Captain", is_leader=True)
    ancient = _model(faction_id, "Ancient", is_support=True)
    squad = FactionUnit(name="Intercessor Squad", faction_id=faction_id)
    captain_sheet = FactionUnit(name="Captain", faction_id=faction_id)
    session.add_all([marine, captain, ancient, squad, captain_sheet])
    await session.flush()
    unit = Unit(
        faction_unit_id=squad.id, points=300, list_id=army_list.id,
        unit_models=[UnitModel(model_id=marine.id) for _ in range(5)]
        + [UnitModel(model_id=captain.id), UnitModel(model_id=ancient.id)],
    )
    # (A CHARACTER on its own isn't split.)
    alone = Unit(
        faction_unit_id=captain_sheet.id, points=80, list_id=army_list.id,
        unit_models=[UnitModel(model_id=captain.id)],
    )
    session.add_all([unit, alone])
    await session.flush()
    session.add(ListWarlord(list_id=army_list.id, unit_id=unit.id))
    model_ids = sorted(um.id for um in unit.unit_models)
    await session.commit()
    list_id, unit_id, squad_id, captain_sheet_id = army_list.id, unit.id, squad.id, captain_sheet.id

    await attached_leaders.run(session)
    await session.commit()
    await attached_leaders.run(session)  # (Nothing more to do.)
    await session.commit()
    session.expire_all()

    units = (
        await session.execute(
            select(Unit)
            .options(selectinload(Unit.unit_models), selectinload(Unit.faction_unit))
            .where(Unit.list_id == list_id)
            .order_by(Unit.id)
        )
    ).scalars().all()
    assert len(units) == 4
    by_sheet = {u.faction_unit.name: u for u in units if u.attached_to_id == unit_id}
    assert set(by_sheet) == {"Captain", "Ancient"}  # (Ancient's datasheet made.)
    assert len(by_sheet["Captain"].unit_models) == 1
    remaining = next(u for u in units if u.id == unit_id)
    assert len(remaining.unit_models) == 5
    # The same models, moved.
    assert sorted(um.id for u in [remaining, *by_sheet.values()] for um in u.unit_models) == model_ids
    # (No points values: the leaders 0, the list's total kept.)
    assert remaining.points + sum(u.points for u in by_sheet.values()) == 300
    warlord = await session.get(ListWarlord, list_id)
    assert warlord.unit_id == by_sheet["Captain"].id
    pairs = {(p.leader_id, p.bodyguard_id) for p in (await session.execute(select(LeaderBodyguard))).scalars()}
    assert (captain_sheet_id, squad_id) in pairs


async def _api_setup(client: AsyncClient, faction_id: int):
    async def model(name, **flags):
        body = {
            "name": name, "faction_id": faction_id, "save": 3, "toughness": 4, "oc": 1,
            "movement": 6, "wounds": 2, "leadership": 6, **flags,
        }
        return (await client.post("/models", json=body)).json()["id"]

    async def sheet(name, bodyguard_ids=()):
        body = {"name": name, "faction_id": faction_id, "bodyguard_ids": list(bodyguard_ids)}
        response = await client.post("/faction-units", json=body)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    detachment_id = (
        await client.post("/detachments", json={"name": "D", "faction_id": faction_id, "dp": 2})
    ).json()["id"]
    list_id = (
        await client.post("/lists", json={
            "name": "L", "points_limit": 2000, "faction_id": faction_id,
            "detachment_ids": [detachment_id],
        })
    ).json()["id"]
    squad = await sheet("Intercessor Squad")
    other = await sheet("Hellblaster Squad")
    ids = {
        "list": list_id, "squad": squad, "other": other,
        "captain": await sheet("Captain", [squad]),
        "lieutenant": await sheet("Lieutenant", [squad]),
        "ancient": await sheet("Ancient", [squad]),
        "marine": await model("Intercessor"),
        "captain_model": await model("Captain", is_leader=True),
        "lieutenant_model": await model("Lieutenant", is_leader=True),
        "ancient_model": await model("Ancient", is_support=True),
    }
    return ids


async def _unit(client, ids, sheet, model, n=1, **extra):
    body = {
        "faction_unit_id": ids[sheet], "list_id": ids["list"], "points": 50,
        "unit_models": [{"model_id": ids[model]}] * n, **extra,
    }
    return await client.post("/units", json=body)


async def test_attaching_leaders_through_the_api(client: AsyncClient, faction_id: int):
    ids = await _api_setup(client, faction_id)
    squad = (await _unit(client, ids, "squad", "marine", 5)).json()["id"]
    hellblasters = (await _unit(client, ids, "other", "marine", 5)).json()["id"]

    captain = await _unit(client, ids, "captain", "captain_model", attached_to_id=squad)
    assert captain.status_code == 201, captain.text
    assert captain.json()["attached_to_id"] == squad
    sheet = next(f for f in (await client.get("/faction-units")).json() if f["id"] == ids["captain"])
    assert sheet["bodyguard_ids"] == [ids["squad"]]

    # One leader and one support unit each (Core Rules 24.22).
    second = await _unit(client, ids, "lieutenant", "lieutenant_model", attached_to_id=squad)
    assert second.status_code == 400
    support = await _unit(client, ids, "ancient", "ancient_model", attached_to_id=squad)
    assert support.status_code == 201, support.text
    # Only to a datasheet it can lead; only a leader or support unit.
    assert (await _unit(client, ids, "lieutenant", "lieutenant_model",
                        attached_to_id=hellblasters)).status_code == 400
    assert (await _unit(client, ids, "other", "marine", 5, attached_to_id=squad)).status_code == 400

    # Its bodyguard gone, it's a unit on its own.
    assert (await client.delete(f"/units/{squad}")).status_code == 204
    units = {u["id"]: u for u in (await client.get("/units")).json()}
    assert units[captain.json()["id"]]["attached_to_id"] is None


async def test_a_game_plays_an_attached_unit_as_one(
    client: AsyncClient, session: AsyncSession, faction_id: int
):
    ids = await _api_setup(client, faction_id)
    squad = (await _unit(client, ids, "squad", "marine", 5)).json()
    captain = (await _unit(client, ids, "captain", "captain_model", attached_to_id=squad["id"])).json()
    # (Set directly: the test's Captain has no CHARACTER keyword to pass the
    # list's Warlord check.)
    session.add(ListWarlord(list_id=ids["list"], unit_id=captain["id"]))
    await session.commit()

    catalog = await loader.load(session, [ids["list"]], [], [], [], None)
    army_list = catalog.get("ArmyList", ids["list"])
    assert [u.id for u in army_list.units] == [squad["id"]]
    unit = army_list.units[0]
    assert len(unit.unit_models) == 6
    assert unit.points == squad["points"] + captain["points"]
    assert army_list.warlord_unit_id == squad["id"]
    assert catalog.get("Unit", captain["id"]) is None


async def test_leading_and_upgrades_last_while_their_unit_does(
    session: AsyncSession, faction_id: int, monkeypatch
):
    # Core Rules 19.04, in a game: a leader that started the battle attached
    # leads even once its bodyguard unit's destroyed; each unit's upgrade
    # applies to the attached unit while that unit (bodyguard, or leader)
    # does.
    from types import SimpleNamespace

    from app.engine import context
    from app.models import Enhancement
    from app.services.in_game import shooting
    from app.services.list_building import enhancements as rules

    army_list = await _list(session, faction_id)
    detachment_id = army_list.detachments[0].id
    marine = _model(faction_id, "Intercessor")
    captain = _model(faction_id, "Captain", is_leader=True)
    squad_sheet = FactionUnit(name="Intercessor Squad", faction_id=faction_id)
    captain_sheet = FactionUnit(name="Captain", faction_id=faction_id)
    squad_upgrade = Enhancement(name="Drilled", points=10, kind="upgrade", detachment_id=detachment_id)
    captain_upgrade = Enhancement(name="Fierce", points=10, kind="upgrade", detachment_id=detachment_id)
    session.add_all([marine, captain, squad_sheet, captain_sheet, squad_upgrade, captain_upgrade])
    await session.flush()
    squad = Unit(
        faction_unit_id=squad_sheet.id, points=80, list_id=army_list.id,
        unit_models=[UnitModel(model_id=marine.id) for _ in range(2)], upgrade=squad_upgrade,
    )
    session.add(squad)
    await session.flush()
    leader = Unit(
        faction_unit_id=captain_sheet.id, points=80, list_id=army_list.id,
        attached_to_id=squad.id, unit_models=[UnitModel(model_id=captain.id)],
        upgrade=captain_upgrade,
    )
    session.add(leader)
    await session.commit()
    ids = (squad.id, leader.id, squad_upgrade.id, captain_upgrade.id)

    # (In a list: the leader's unit is attached, so its model leads.)
    assert rules.is_leading(leader, leader.unit_models[0])

    catalog = await loader.load(session, [army_list.id], [], [], [], None)
    unit = catalog.get("Unit", ids[0])
    bodyguard = [m for m in unit.unit_models if m.led_from is None]
    captain_model = next(m for m in unit.unit_models if m.led_from == ids[1])
    destroyed: list[int] = []
    monkeypatch.setattr(context, "current", lambda: SimpleNamespace(
        game=SimpleNamespace(model_damage=[
            SimpleNamespace(unit_model_id=i, destroyed=True) for i in destroyed
        ]),
    ))
    monkeypatch.setattr(context, "catalog", lambda: catalog)

    def upgrades():
        return sorted(u.id for u in rules._upgrades_reaching(unit))

    assert rules.is_leading(unit, captain_model) and shooting.leading(unit)
    assert not rules.is_leading(unit, bodyguard[0])
    assert upgrades() == sorted(ids[2:])

    destroyed.extend(m.id for m in bodyguard)  # The bodyguard unit's gone.
    assert rules.is_leading(unit, captain_model) and shooting.leading(unit)
    assert upgrades() == [ids[3]]
    destroyed.clear()
    destroyed.append(captain_model.id)  # The leader's gone instead.
    assert upgrades() == [ids[2]]

    # An autosave keeps it all (see app/engine/catalog.py).
    import json

    from app.engine.catalog import Catalog

    restored = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
    again = restored.get("Unit", ids[0])
    assert [u.id for u in again.attached_upgrades] == [ids[3]]
    assert again.attached_upgrade_units == [ids[1]]
    assert sorted(m.led_from or 0 for m in again.unit_models) == [0, 0, ids[1]]


def test_bearers_unit_grant_ends_with_the_bearer(monkeypatch):
    # Core Rules 19.04: an ability from a specific model (the bearer of an
    # enhancement) applies to its unit until that model is destroyed.
    from types import SimpleNamespace

    from app.engine import context
    from app.services.list_building import enhancements as rules

    grant = SimpleNamespace(scope="bearers_unit")
    bearer = SimpleNamespace(id=1, enhancement=SimpleNamespace(grants=[grant]))
    other = SimpleNamespace(id=2, enhancement=None)
    unit = SimpleNamespace(unit_models=[bearer, other], upgrade=None)
    destroyed: list[int] = []
    monkeypatch.setattr(context, "current", lambda: SimpleNamespace(
        game=SimpleNamespace(model_damage=[
            SimpleNamespace(unit_model_id=i, destroyed=True) for i in destroyed
        ]),
    ))

    def reaching():
        return rules._grants_reaching(unit, other, lambda e: e.grants)

    assert reaching() == [grant]
    destroyed.append(bearer.id)
    assert reaching() == []
    # Destroyed by the attacks being made: it lasts until they're all made.
    with rules.lasting([bearer.id]):
        assert reaching() == [grant]
    assert reaching() == []
