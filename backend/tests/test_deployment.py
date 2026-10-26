import math

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import (
    BaseSize,
    Condition,
    DatasheetAbility,
    Effect,
    FactionUnit,
    Keyword,
    Model,
    Unit,
    UnitModel,
    Weapon,
    WeaponAbility,
)
from app.seeds import terrain_layouts as terrain_seed
from app.services.in_game.deployment import (
    _grid,
    distance_to_polygon,
    gap,
    overlaps,
    wholly_inside,
)
from app.services.in_game.terrain import Base
from tests.test_games import _game_payload, _setup
from tests.test_terrain import _layout_file

# The test layout's deployment ("Strips"): the attacker's zone is y 32-44,
# the defender's y 0-12, the whole width of the board.
R32 = 32 / 2 / 25.4


async def _base_size(session, name):
    query = select(BaseSize).where(BaseSize.name == name)
    found = (await session.execute(query)).scalar_one_or_none()
    if found is None:
        found = BaseSize(name=name)
        session.add(found)
    return found


async def _unit(
    session,
    list_id,
    faction_id,
    name,
    count,
    base="32mm",
    infiltrators=False,
    weapon_range=None,
    keywords=(),
    assault_range=None,
    melee=False,
    fights_first=False,
    deep_strike=False,
):
    # A unit of `count` identical models in a list - each with a gun of
    # `weapon_range` (1 attack, always hits on 2+) if given, an Assault gun of
    # `assault_range` likewise, a melee blade likewise if `melee`, the Fights
    # First ability if `fights_first`, and `keywords`.
    abilities = []
    if deep_strike:
        query = select(DatasheetAbility).where(DatasheetAbility.name == "Deep Strike")
        abilities.append(
            (await session.execute(query)).scalar_one_or_none()
            or DatasheetAbility(name="Deep Strike")
        )
    if fights_first:
        query = select(DatasheetAbility).where(DatasheetAbility.name == "Fights First")
        abilities.append(
            (await session.execute(query)).scalar_one_or_none()
            or DatasheetAbility(name="Fights First")
        )
    if infiltrators:
        query = select(DatasheetAbility).where(DatasheetAbility.name == "Infiltrators")
        ability = (await session.execute(query)).scalar_one_or_none() or DatasheetAbility(
            name="Infiltrators"
        )
        abilities.append(ability)
    model = Model(
        name=name, faction_id=faction_id, save=3, toughness=4, oc=1, movement=6, wounds=2,
        leadership=6, abilities=abilities, base_size=await _base_size(session, base),
    )
    # (No autoflush: the model isn't in the session yet.)
    with session.no_autoflush:
        for keyword in keywords:
            query = select(Keyword).where(Keyword.name == keyword)
            model.keywords.append(
                (await session.execute(query)).scalar_one_or_none() or Keyword(name=keyword)
            )
    weapons = []
    if weapon_range is not None:
        weapons = [
            Weapon(
                name=f"{name} gun", range=weapon_range, attacks="1", skill=2, strength=4,
                ap=0, damage="1", weapon_type="ranged", model=model,
            )
        ]
    if melee:
        weapons.append(
            Weapon(
                name=f"{name} blade", range=None, attacks="1", skill=2, strength=4, ap=0,
                damage="1", weapon_type="melee", model=model,
            )
        )
    if assault_range is not None:
        query = select(Effect).where(Effect.keyword == "assault")
        effect = (await session.execute(query)).scalar_one_or_none() or Effect(
            keyword="assault", name="Assault"
        )
        query = select(Condition).where(Condition.keyword == "always")
        always = (await session.execute(query)).scalar_one_or_none() or Condition(
            keyword="always", name="Always"
        )
        weapons.append(
            Weapon(
                name=f"{name} assault gun", range=assault_range, attacks="1", skill=2,
                strength=4, ap=0, damage="1", weapon_type="ranged", model=model,
                abilities=[WeaponAbility(name="Assault", conditions=[always], effects=[effect])],
            )
        )
    unit = Unit(
        faction_unit=FactionUnit(name=name, faction_id=faction_id),
        points=100,
        list_id=list_id,
        unit_models=[UnitModel(model=model, weapons=list(weapons)) for _ in range(count)],
    )
    session.add(unit)
    await session.commit()
    return unit.id


async def _game(client, session, tmp_path, units=None, declare=True, first=2):
    # A game on the test layout, attacker seat 1. `units` is
    # {seat: [(name, count, kwargs)]}; by default each side has one unit of 5.
    # Both players have declared their battle formations (every unit on the
    # battlefield), unless not `declare`. Seat `first` goes first (None: the
    # players roll off once everything is set up).
    ids = await _setup(client)
    await terrain_seed.seed(session, _layout_file(tmp_path))
    units = units or {1: [("Attackers", 5, {})], 2: [("Defenders", 5, {})]}
    for seat, specs in units.items():
        for name, count, kwargs in specs:
            await _unit(session, ids[f"list{seat}"], ids[f"faction{seat}"], name, count, **kwargs)
    response = await client.post("/games", json=_game_payload(ids, attacker=1, first=first))
    assert response.status_code == 201, response.text
    game = response.json()
    if declare and game["status"] == "deployment":
        for seat in (1, 2):
            url = f"/games/{game['id']}/formations/done"
            response = await client.post(url, json={"seat": seat})
            assert response.status_code == 200, response.text
        game = response.json()
    return game


async def _deployment(client, game_id):
    return (await client.get(f"/games/{game_id}/deployment")).json()


def _unit_named(deployment, name):
    return next(u for u in deployment["units"] if u["name"] == name)


def _row(unit, x, y, spacing=1.5):
    # The unit's models side by side in a row from (x, y) - spaced so each is
    # within 2" of its neighbours - and in a second row when there are more
    # than 3, so every model has 2 near it.
    return [
        {
            "unit_model_id": m["unit_model_id"],
            "x": x + (i % 3) * spacing,
            "y": y + (i // 3) * spacing,
        }
        for i, m in enumerate(unit["models"])
    ]


async def _check(client, game_id, unit, positions):
    response = await client.post(
        f"/games/{game_id}/deployment/check",
        json={"unit_id": unit["unit_id"], "positions": positions},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _deploy(client, game_id, unit, positions):
    return await client.post(
        f"/games/{game_id}/deployment", json={"unit_id": unit["unit_id"], "positions": positions}
    )


# --- geometry ---


L_ZONE = [(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)]  # concave


@pytest.mark.parametrize(
    "x,y,expected",
    [
        (5, 5, True),
        (15, 5, True),
        (5, 15, True),
        (15, 15, False),  # in the notch
        (10.3, 10.3, False),  # centre in, but over the inner corner
        (9, 9, True),
        (19.37, 5, True),  # touching the edge
        (19.5, 5, False),
    ],
)
def test_wholly_inside_a_concave_zone(x, y, expected):
    assert wholly_inside(Base(x, y, 32, 32), L_ZONE) is expected


def test_wholly_inside_an_oval():
    # 105 x 70mm: about 4.13" x 2.76".
    assert wholly_inside(Base(17, 5, 105, 70), L_ZONE)
    assert not wholly_inside(Base(17, 5, 105, 70, rotation=0), [(0, 0), (19, 0), (19, 10), (0, 10)])
    assert wholly_inside(Base(17.5, 5, 105, 70, rotation=90), [(0, 0), (19, 0), (19, 10), (0, 10)])


def test_gap_and_overlap_between_round_bases():
    a, b = Base(0, 0, 32, 32), Base(3, 0, 32, 32)
    assert gap(a, b) == pytest.approx(3 - 2 * R32)
    assert not overlaps(a, b)
    assert not overlaps(a, Base(2 * R32, 0, 32, 32))  # touching
    assert overlaps(a, Base(1, 0, 32, 32))


def test_gap_and_overlap_with_an_oval():
    oval = Base(0, 0, 105, 70)  # 2.07" along x, 1.38" along y from the centre
    assert gap(oval, Base(2.07 + R32 + 1, 0, 32, 32)) == pytest.approx(1, abs=0.01)
    assert gap(oval, Base(0, 1.38 + R32 + 1, 32, 32)) == pytest.approx(1, abs=0.01)
    assert overlaps(oval, Base(2.5, 0, 32, 32))
    # Turned, its long axis is along y.
    assert overlaps(Base(0, 0, 105, 70, rotation=90), Base(0, 2.5, 32, 32))


def test_distance_to_a_zone():
    zone = [(0, 32), (60, 32), (60, 44), (0, 44)]
    assert distance_to_polygon(Base(10, 20, 32, 32), zone) == pytest.approx(12 - R32)
    assert distance_to_polygon(Base(10, 32, 32, 32), zone) == 0
    assert distance_to_polygon(Base(10, 20, 105, 70, rotation=90), zone) == pytest.approx(
        12 - 105 / 2 / 25.4, abs=0.01
    )


@pytest.mark.parametrize("count", range(1, 31))
def test_formation_grid_never_leaves_a_model_alone(count):
    rows, columns = _grid(count)
    assert rows * columns >= count
    if count >= 3:
        assert rows >= 2
        # A lone model in the last row sits between two above it, not
        # under one.
        assert count % columns != 1 or columns % 2 == 0


# --- the flow ---


async def test_new_game_with_zones_and_units_starts_in_deployment(
    client: AsyncClient, session, tmp_path
):
    game = await _game(client, session, tmp_path)
    assert game["status"] == "deployment"
    assert game["battle_round"] == 0
    # The attacker deploys first.
    assert game["deploying_seat"] == 1

    deployment = await _deployment(client, game["id"])
    assert deployment["deploying_seat"] == 1
    attackers = _unit_named(deployment, "Attackers")
    assert (attackers["seat"], attackers["deployed"]) == (1, False)
    assert not attackers["infiltrators"]
    model = attackers["models"][0]
    assert (model["base_size"], model["measured"]) == ("32mm", True)
    assert model["width"] == pytest.approx(2 * R32)
    assert model["position"] is None


async def test_game_without_units_stays_in_setup(client: AsyncClient, session, tmp_path):
    ids = await _setup(client)
    await terrain_seed.seed(session, _layout_file(tmp_path))
    game = (await client.post("/games", json=_game_payload(ids))).json()
    assert game["status"] == "setup"
    assert game["deploying_seat"] is None
    # Starting it goes straight to the first battle round.
    game = (await client.post(f"/games/{game['id']}/start")).json()
    assert (game["status"], game["battle_round"]) == ("in_progress", 1)


async def test_starting_a_game_in_setup_begins_deployment(client: AsyncClient, session, tmp_path):
    # A game created before its lists had units (or before deployment
    # existed) deploys when it's started.
    ids = await _setup(client)
    await terrain_seed.seed(session, _layout_file(tmp_path))
    game = (await client.post("/games", json=_game_payload(ids))).json()
    await _unit(session, ids["list1"], ids["faction1"], "Late", 1)
    game = (await client.post(f"/games/{game['id']}/start")).json()
    # Declaring battle formations first.
    assert (game["status"], game["deployment_step"]) == ("deployment", "formations")


async def test_players_take_turns_then_the_battle_begins(client: AsyncClient, session, tmp_path):
    # The attacker has 3 units, the defender 1: attacker, defender, then the
    # attacker sets up both of the rest.
    game = await _game(
        client,
        session,
        tmp_path,
        units={1: [("A1", 1, {}), ("A2", 1, {}), ("A3", 1, {})], 2: [("D1", 1, {})]},
    )
    game_id = game["id"]
    deployment = await _deployment(client, game_id)

    order = [("A1", 1, 5), ("D1", 2, 5), ("A2", 1, 10), ("A3", 1, 15)]
    for name, seat, x in order:
        assert (await _deployment(client, game_id))["deploying_seat"] == seat
        y = 40 if seat == 1 else 4
        unit = _unit_named(deployment, name)
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    game = response.json()
    # Everything's down: the first battle round begins.
    assert (game["status"], game["battle_round"], game["phase"], game["turn_seat"]) == (
        "in_progress", 1, "command", 2
    )
    assert game["deploying_seat"] is None
    deployment = await _deployment(client, game_id)
    assert all(u["deployed"] for u in deployment["units"])
    a1 = _unit_named(deployment, "A1")["models"][0]["position"]
    assert (a1["x"], a1["y"]) == (5, 40)


async def test_only_the_deploying_player_can_deploy(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path)
    deployment = await _deployment(client, game["id"])
    defenders = _unit_named(deployment, "Defenders")
    response = await _deploy(client, game["id"], defenders, _row(defenders, 5, 4))
    assert response.status_code == 400
    assert "turn" in response.json()["detail"]
    # Nor twice.
    attackers = _unit_named(deployment, "Attackers")
    assert (await _deploy(client, game["id"], attackers, _row(attackers, 5, 40))).status_code == 200
    response = await _deploy(client, game["id"], attackers, _row(attackers, 20, 40))
    assert response.status_code == 400


async def test_every_model_must_be_placed(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path)
    attackers = _unit_named(await _deployment(client, game["id"]), "Attackers")
    response = await _deploy(client, game["id"], attackers, _row(attackers, 5, 40)[:-1])
    assert response.status_code == 400
    assert "every model" in response.json()["detail"]


# --- placement ---


async def test_valid_placement(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path)
    attackers = _unit_named(await _deployment(client, game["id"]), "Attackers")
    check = await _check(client, game["id"], attackers, _row(attackers, 5, 38))
    assert check == {"valid": True, "problems": [], "models": [], "paths": []}


async def test_outside_the_deployment_zone(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path)
    attackers = _unit_named(await _deployment(client, game["id"]), "Attackers")
    # The first row's bases cross the zone's edge at y 32.
    check = await _check(client, game["id"], attackers, _row(attackers, 5, 32.3))
    assert not check["valid"]
    assert "Attackers isn't wholly within the attacker's deployment zone (x3)" in check["problems"]
    assert len(check["models"]) == 3
    response = await _deploy(client, game["id"], attackers, _row(attackers, 5, 32.3))
    assert response.status_code == 400
    assert "deployment zone" in response.json()["detail"]


async def test_off_the_battlefield(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path)
    attackers = _unit_named(await _deployment(client, game["id"]), "Attackers")
    check = await _check(client, game["id"], attackers, _row(attackers, 0.2, 38))
    assert any("off the battlefield" in p for p in check["problems"])


async def test_coherency(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path)
    attackers = _unit_named(await _deployment(client, game["id"]), "Attackers")
    positions = _row(attackers, 5, 38)
    # One model wanders off: more than 2" from any of the others, and more
    # than 9" from all of them.
    positions[0] = {**positions[0], "x": 30}
    check = await _check(client, game["id"], attackers, positions)
    stray = next(m for m in check["models"] if m["unit_model_id"] == positions[0]["unit_model_id"])
    assert any('within 2" of another model' in p for p in stray["problems"])
    assert any('more than 9" from 4 other models' in p for p in stray["problems"])
    # The rest are still within 9" of each other, but each is more than 9"
    # from the stray.
    assert len(check["models"]) == 5


async def test_coherency_needs_one_nearby_model(client: AsyncClient, session, tmp_path):
    # In a line 2.5" apart (1.24" between bases), each model has one within
    # 2" - enough. Pull the last one 2" further out and it has none.
    game = await _game(client, session, tmp_path, units={1: [("Line", 3, {})], 2: [("D", 1, {})]})
    line = _unit_named(await _deployment(client, game["id"]), "Line")
    positions = [
        {"unit_model_id": m["unit_model_id"], "x": 5 + i * 2.5, "y": 38}
        for i, m in enumerate(line["models"])
    ]
    assert (await _check(client, game["id"], line, positions))["valid"]
    positions[2] = {**positions[2], "x": positions[2]["x"] + 2}
    check = await _check(client, game["id"], line, positions)
    assert check["problems"] == ['Line isn\'t within 2" of another model in its unit']


async def test_unit_of_two_needs_only_each_other(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path, units={1: [("Pair", 2, {})], 2: [("D", 1, {})]})
    pair = _unit_named(await _deployment(client, game["id"]), "Pair")
    check = await _check(client, game["id"], pair, _row(pair, 5, 38))
    assert check["valid"], check


async def test_overlapping_models(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path)
    attackers = _unit_named(await _deployment(client, game["id"]), "Attackers")
    positions = _row(attackers, 5, 38, spacing=1.0)  # 1" apart: 32mm bases overlap
    check = await _check(client, game["id"], attackers, positions)
    assert any("overlaps another model in its unit" in p for p in check["problems"])


async def test_infiltrators(client: AsyncClient, session, tmp_path):
    game = await _game(
        client,
        session,
        tmp_path,
        units={1: [("Scouts", 3, {"infiltrators": True}), ("Grunts", 3, {})], 2: [("D", 3, {})]},
    )
    deployment = await _deployment(client, game["id"])
    scouts, grunts = _unit_named(deployment, "Scouts"), _unit_named(deployment, "Grunts")
    assert scouts["infiltrators"] and not grunts["infiltrators"]

    # Mid-board, more than 9" from the defender's zone (y 0-12): fine for
    # Infiltrators, not for anyone else.
    assert (await _check(client, game["id"], scouts, _row(scouts, 20, 24)))["valid"]
    check = await _check(client, game["id"], grunts, _row(grunts, 20, 24))
    assert any("deployment zone" in p for p in check["problems"])
    # Within 9" of the defender's zone.
    check = await _check(client, game["id"], scouts, _row(scouts, 20, 20))
    assert any('within 9" of the enemy deployment zone' in p for p in check["problems"])


async def test_infiltrators_away_from_an_enemy_model_outside_its_zone(
    client: AsyncClient, session, tmp_path
):
    # The attacker's infiltrating unit is set up first, mid-board; the
    # defender's infiltrators then can't come within 9" of it.
    game = await _game(
        client,
        session,
        tmp_path,
        units={
            1: [("Scouts", 1, {"infiltrators": True})],
            2: [("Other scouts", 1, {"infiltrators": True})],
        },
    )
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    scouts = _unit_named(deployment, "Scouts")
    assert (await _deploy(client, game_id, scouts, _row(scouts, 10, 22))).status_code == 200
    other = _unit_named(deployment, "Other scouts")
    # 21.5" from the attacker's zone, but 5" from their scouts.
    check = await _check(client, game_id, other, _row(other, 15, 22))
    assert any('within 9" of an enemy model' in p for p in check["problems"])
    assert (await _check(client, game_id, other, _row(other, 40, 22)))["valid"]


async def test_cant_overlap_a_deployed_model(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {}), ("B", 1, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, b, d = (_unit_named(deployment, n) for n in ("A", "B", "D"))
    assert (await _deploy(client, game_id, a, _row(a, 10, 40))).status_code == 200
    assert (await _deploy(client, game_id, d, _row(d, 10, 4))).status_code == 200
    check = await _check(client, game_id, b, _row(b, 10.5, 40))
    assert check["problems"] == ["B overlaps A"]


async def test_cant_overlap_a_terrain_feature(client: AsyncClient, session, tmp_path):
    # The test layout's ruin wall is an L at (7, 8): x 7-11 along y 8-8.5,
    # and down x 7-7.5 to y 11 - in the defender's zone. Its terrain areas
    # are fine to stand on.
    game = await _game(client, session, tmp_path, units={1: [("A", 1, {})], 2: [("D", 1, {})]})
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, d = _unit_named(deployment, "A"), _unit_named(deployment, "D")
    assert (await _deploy(client, game_id, a, _row(a, 10, 40))).status_code == 200
    check = await _check(client, game_id, d, _row(d, 9, 8.25))
    assert check["problems"] == ["D overlaps a ruin wall"]
    # Touching it is fine.
    assert (await _check(client, game_id, d, _row(d, 9, 8.5 + R32)))["valid"]
    response = await _deploy(client, game_id, d, _row(d, 9, 8.6))
    assert response.status_code == 400
    assert "ruin wall" in response.json()["detail"]


def test_base_overlapping_a_polygon():
    from app.services.in_game.deployment import overlaps_polygon

    wall = [(7, 8), (11, 8), (11, 8.5), (7, 8.5)]
    assert overlaps_polygon(Base(9, 8.25, 32, 32), wall)
    assert overlaps_polygon(Base(9, 9, 32, 32), wall)
    assert not overlaps_polygon(Base(9, 8.5 + R32, 32, 32), wall)  # touching
    assert not overlaps_polygon(Base(9, 10, 32, 32), wall)
    # An oval reaches further along its length.
    assert overlaps_polygon(Base(12.5, 8.25, 105, 70), wall)
    assert not overlaps_polygon(Base(12.5, 8.25, 105, 70, rotation=90), wall)


async def test_formation_avoids_terrain_features(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("Squad", 5, {})]}
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, squad = _unit_named(deployment, "A"), _unit_named(deployment, "Squad")
    assert (await _deploy(client, game_id, a, _row(a, 10, 40))).status_code == 200
    positions = await _formation(client, game_id, squad, 9, 8.25)
    check = await _check(client, game_id, squad, positions)
    assert not any("ruin wall" in p for p in check["problems"]), check


# --- formations ---


async def _formation(client, game_id, unit, x, y):
    response = await client.post(
        f"/games/{game_id}/deployment/formation", json={"unit_id": unit["unit_id"], "x": x, "y": y}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("count", [1, 2, 3, 5, 7, 10, 20])
async def test_formation_is_a_valid_starting_point(client: AsyncClient, session, tmp_path, count):
    units = {1: [("Squad", count, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units)
    squad = _unit_named(await _deployment(client, game["id"]), "Squad")
    positions = await _formation(client, game["id"], squad, 30, 38)
    assert {p["unit_model_id"] for p in positions} == {m["unit_model_id"] for m in squad["models"]}
    check = await _check(client, game["id"], squad, positions)
    assert check["valid"], check


async def test_formation_stays_in_the_zone_near_its_edge(client: AsyncClient, session, tmp_path):
    # Set down on the zone's edge, a unit of 10 is moved up into it.
    game = await _game(client, session, tmp_path, units={1: [("Squad", 10, {})], 2: [("D", 1, {})]})
    squad = _unit_named(await _deployment(client, game["id"]), "Squad")
    positions = await _formation(client, game["id"], squad, 0.5, 32.5)
    assert all(p["y"] >= 32 + R32 - 1e-6 and p["x"] >= R32 - 1e-6 for p in positions)
    assert (await _check(client, game["id"], squad, positions))["valid"]


async def test_formation_moves_models_off_others(client: AsyncClient, session, tmp_path):
    game = await _game(
        client, session, tmp_path, units={1: [("A", 1, {}), ("Squad", 5, {})], 2: [("D", 1, {})]}
    )
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, d, squad = (_unit_named(deployment, n) for n in ("A", "D", "Squad"))
    assert (await _deploy(client, game_id, a, _row(a, 30, 38))).status_code == 200
    assert (await _deploy(client, game_id, d, _row(d, 30, 4))).status_code == 200
    positions = await _formation(client, game_id, squad, 30, 38)
    check = await _check(client, game_id, squad, positions)
    assert not any("overlaps" in p for p in check["problems"]), check


async def test_formation_of_oval_bases(client: AsyncClient, session, tmp_path):
    game = await _game(
        client,
        session,
        tmp_path,
        units={1: [("Bikes", 3, {"base": "75 x 42mm"})], 2: [("D", 1, {})]},
    )
    bikes = _unit_named(await _deployment(client, game["id"]), "Bikes")
    assert bikes["models"][0]["width"] == pytest.approx(75 / 25.4)
    positions = await _formation(client, game["id"], bikes, 30, 38)
    assert (await _check(client, game["id"], bikes, positions))["valid"]


async def test_model_without_a_measured_base_uses_a_placeholder(
    client: AsyncClient, session, tmp_path
):
    game = await _game(
        client,
        session,
        tmp_path,
        units={1: [("Tank", 1, {"base": "Use model"})], 2: [("D", 1, {})]},
    )
    tank = _unit_named(await _deployment(client, game["id"]), "Tank")["models"][0]
    assert (tank["base_size"], tank["measured"]) == ("Use model", False)
    assert tank["width"] == pytest.approx(32 / 25.4)
    assert math.isclose(tank["height"], tank["width"])



# --- declaring battle formations ---


async def _formations(client, game_id):
    return (await client.get(f"/games/{game_id}/formations")).json()


async def _set(client, game_id, seat, unit, place, transport=None):
    return await client.post(
        f"/games/{game_id}/formations",
        json={
            "seat": seat,
            "unit_id": unit["unit_id"],
            "place": place,
            "transport_unit_id": transport["unit_id"] if transport else None,
        },
    )


async def _declare(client, game_id, seat):
    return await client.post(f"/games/{game_id}/formations/done", json={"seat": seat})


async def test_deployment_starts_with_battle_formations(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path, declare=False)
    assert (game["status"], game["deployment_step"], game["deploying_seat"]) == (
        "deployment", "formations", None
    )
    state = await _formations(client, game["id"])
    [attacker] = [p for p in state["players"] if p["seat"] == 1]
    assert (attacker["done"], attacker["reserves_points"]) == (False, 0)
    # Every unit's points are 100 (see _unit): 50 can go into reserves.
    assert (attacker["army_points"], attacker["reserves_limit"]) == (100, 50)
    # No deploying until both have declared.
    attackers = _unit_named(await _deployment(client, game["id"]), "Attackers")
    response = await _deploy(client, game["id"], attackers, _row(attackers, 5, 40))
    assert "battle formations first" in response.json()["detail"]
    await _declare(client, game["id"], 1)
    game = (await _declare(client, game["id"], 2)).json()
    assert (game["deployment_step"], game["deploying_seat"]) == ("deploying", 1)


async def test_strategic_reserves_up_to_half_the_army(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {}), ("B", 1, {}), ("C", 1, {}), ("E", 1, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, b, c = (_unit_named(deployment, n) for n in "ABC")
    # 400 points: 200 can be in reserves.
    assert (await _set(client, game_id, 1, a, "reserves")).status_code == 200
    response = await _set(client, game_id, 1, b, "reserves")
    assert response.json()["players"][0]["reserves_points"] == 200
    response = await _set(client, game_id, 1, c, "reserves")
    assert response.status_code == 400
    assert "at most 200" in response.json()["detail"]
    # Back on the battlefield.
    response = await _set(client, game_id, 1, b, None)
    assert response.json()["players"][0]["reserves_points"] == 100
    # Only their own units.
    d = _unit_named(deployment, "D")
    assert (await _set(client, game_id, 1, d, "reserves")).status_code == 400


async def test_units_in_reserves_arent_deployed(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {}), ("B", 1, {})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a, b, d = (_unit_named(deployment, n) for n in "ABD")
    await _set(client, game_id, 1, b, "reserves")
    await _declare(client, game_id, 1)
    await _declare(client, game_id, 2)
    assert _unit_named(await _deployment(client, game_id), "B")["formation"] == "reserves"
    response = await _deploy(client, game_id, b, _row(b, 5, 40))
    assert "in Strategic Reserves" in response.json()["detail"]
    # A and D are all there is to deploy: then the battle begins.
    assert (await _deploy(client, game_id, a, _row(a, 5, 40))).status_code == 200
    game = (await _deploy(client, game_id, d, _row(d, 5, 4))).json()
    assert (game["status"], game["battle_round"]) == ("in_progress", 1)


async def test_embarking_in_a_transport(client: AsyncClient, session, tmp_path):
    units = {
        1: [("Rhino", 1, {"keywords": ["TRANSPORT"]}), ("Squad", 1, {}), ("Big", 1, {})],
        2: [("D", 1, {})],
    }
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    rhino, squad, big = (_unit_named(deployment, n) for n in ("Rhino", "Squad", "Big"))
    state = await _formations(client, game_id)
    transports = {u["name"]: u["transport"] for u in state["players"][0]["units"]}
    assert transports == {"Rhino": True, "Squad": False, "Big": False}

    response = await _set(client, game_id, 1, squad, "embarked", rhino)
    assert response.status_code == 200, response.text
    player = response.json()["players"][0]
    squad_out = next(u for u in player["units"] if u["name"] == "Squad")
    assert (squad_out["place"], squad_out["transport_unit_id"]) == ("embarked", rhino["unit_id"])
    # Embarked isn't in reserves.
    assert player["reserves_points"] == 0
    # Only in a TRANSPORT; a transport can't embark.
    assert (await _set(client, game_id, 1, big, "embarked", squad)).status_code == 400
    assert (await _set(client, game_id, 1, rhino, "embarked", rhino)).status_code == 400

    await _declare(client, game_id, 1)
    await _declare(client, game_id, 2)
    response = await _deploy(client, game_id, squad, _row(squad, 5, 40))
    assert "embarked" in response.json()["detail"]
    # The Squad isn't counted for the turns: Rhino, D, Big.
    assert (await _deploy(client, game_id, rhino, _row(rhino, 5, 40))).status_code == 200
    d = _unit_named(deployment, "D")
    assert (await _deploy(client, game_id, d, _row(d, 5, 4))).status_code == 200
    game = (await _deploy(client, game_id, big, _row(big, 15, 40))).json()
    assert game["status"] == "in_progress"


async def test_formations_lock_once_declared(client: AsyncClient, session, tmp_path):
    game = await _game(client, session, tmp_path, declare=False)
    game_id = game["id"]
    attackers = _unit_named(await _deployment(client, game_id), "Attackers")
    await _declare(client, game_id, 1)
    assert (await _set(client, game_id, 1, attackers, "reserves")).status_code == 400
    assert (await _declare(client, game_id, 1)).status_code == 400
