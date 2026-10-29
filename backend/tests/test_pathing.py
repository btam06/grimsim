import math

import pytest
from httpx import AsyncClient

from app.services.in_game.pathing import Obstacles, _grow
from tests.test_deployment import R32, _deployment, _unit_named
from tests.test_movement import _battle, _check, _move, _shifted
from tests.test_shooting import _place

# A wall from x 7 to 11, y 8 to 8.5 (and, on the test layout, its L's other
# leg down x 7-7.5 to y 11).
WALL = [(7, 8), (11, 8), (11, 8.5), (7, 8.5)]


def test_grown_wall_keeps_a_base_off_it():
    grown = _grow(WALL, R32)
    xs, ys = [p[0] for p in grown], [p[1] for p in grown]
    assert min(xs) == pytest.approx(7 - R32, abs=0.1)
    assert max(xs) == pytest.approx(11 + R32, abs=0.1)
    assert min(ys) <= 8 - R32 + 1e-6 and max(ys) >= 8.5 + R32 - 1e-6


def test_straight_line_when_nothing_is_in_the_way():
    obstacles = Obstacles([WALL], R32, [(20, 4)], 10)
    assert obstacles.route((20, 4), (20, 10), cap=20) == pytest.approx(6)


def test_route_round_a_wall():
    obstacles = Obstacles([WALL], R32, [(9, 6.5)], 10)
    length = obstacles.route((9, 6.5), (9, 11), cap=20)
    # Round its nearer end (x 11): longer than straight through (4.5").
    assert length > 4.5 + 1
    # Round the wall's end corners, keeping its clearance from each: at least
    # the tangents to circles of that radius round them, plus the end's 0.5";
    # at most out to its grown box's square corners and back in.
    def tangent(point, corner):
        return math.sqrt(math.dist(point, corner) ** 2 - R32**2)

    least = tangent((9, 6.5), (11, 8)) + 0.5 + tangent((9, 11), (11, 8.5))
    most = (
        math.dist((9, 6.5), (11 + R32, 8 - R32))
        + (0.5 + 2 * R32)
        + math.dist((11 + R32, 8.5 + R32), (9, 11))
    )
    assert least < length < most
    # More than the cap: no route.
    assert obstacles.route((9, 6.5), (9, 11), cap=5) is None


def test_starting_against_a_wall_doesnt_trap_a_base():
    # Touching the wall's bottom edge, stepping away from it.
    obstacles = Obstacles([WALL], R32, [(9, 8.5 + R32)], 10)
    assert obstacles.route((9, 8.5 + R32), (9, 11), cap=20) == pytest.approx(11 - 8.5 - R32)


async def _wall_game(client, session, tmp_path, keywords=()):
    # D (seat 2, moving first) just above the test layout's ruin wall.
    units = {1: [("A", 1, {})], 2: [("D", 1, {"keywords": keywords})]}
    game, deployment = await _battle(client, session, tmp_path, units=units)
    d = _unit_named(deployment, "D")
    await _place(session, d, [(9, 6.5)])
    d = _unit_named(await _deployment(client, game["id"]), "D")
    return game["id"], d


async def test_has_to_go_round_dense_terrain(client: AsyncClient, session, tmp_path):
    game_id, d = await _wall_game(client, session, tmp_path)
    # 5" straight down - but the wall's in the way: round it is over 6".
    check = await _check(client, game_id, d, "normal", _shifted(d, dy=5))
    [problem] = check["problems"]
    assert "going round dense terrain and enemy models (it can move 6\")" in problem
    # Somewhere it can reach round the wall's end: fine.
    assert (await _check(client, game_id, d, "normal", _shifted(d, dx=3, dy=3)))["valid"]


@pytest.mark.parametrize("keyword", ["INFANTRY", "BEAST", "SWARM"])
async def test_infantry_beasts_and_swarms_go_through_terrain(
    client: AsyncClient, session, tmp_path, keyword
):
    game_id, d = await _wall_game(client, session, tmp_path, keywords=[keyword])
    assert (await _check(client, game_id, d, "normal", _shifted(d, dy=5)))["valid"]


async def test_the_move_records_the_way_round(client: AsyncClient, session, tmp_path):
    # Its move's distance (for shooting: moved less than 3"?) is the way
    # round, not straight.
    game_id, d = await _wall_game(client, session, tmp_path)
    positions = _shifted(d, dx=3, dy=3)
    assert (await _move(client, game_id, d, "normal", positions)).status_code == 200
    for phase in ("shooting",):
        await client.post(f"/games/{game_id}/advance")
    [unit] = (await client.get(f"/games/{game_id}/shooting")).json()["units"]
    assert unit["distance"] > math.dist((0, 0), (3, 3)) + 0.1



async def test_check_gives_the_way_round(client: AsyncClient, session, tmp_path):
    game_id, d = await _wall_game(client, session, tmp_path)
    # 3" right and 3" down: round the wall's end.
    check = await _check(client, game_id, d, "normal", _shifted(d, dx=3, dy=3))
    [path] = check["paths"]
    points = [(p["x"], p["y"]) for p in path["points"]]
    assert path["unit_model_id"] == d["models"][0]["unit_model_id"]
    assert points[0] == (9, 6.5) and points[-1] == (12, 9.5)
    assert len(points) > 2  # it bends
    # A straight move has no path to show.
    check = await _check(client, game_id, d, "normal", _shifted(d, dx=-1))
    assert check["paths"] == []


async def _reach(client, game_id, d, distance):
    model = d["models"][0]
    response = await client.post(
        f"/games/{game_id}/reach",
        json={
            "unit_id": d["unit_id"],
            "models": [
                {
                    "unit_model_id": model["unit_model_id"],
                    "x": model["position"]["x"],
                    "y": model["position"]["y"],
                    "distance": distance,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    [out] = response.json()["models"]
    return out


def _covers(regions, point):
    # Whether a point is inside any of the (star-shaped) regions.
    from app.services.in_game.deployment import _contains

    return any(_contains(point, [(p["x"], p["y"]) for p in region]) for region in regions)


async def test_reach_goes_round_dense_terrain(client: AsyncClient, session, tmp_path):
    game_id, d = await _wall_game(client, session, tmp_path)
    out = await _reach(client, game_id, d, 6)
    assert out["clearance"] == pytest.approx(R32)
    # Straight up: 5" away, reachable.
    assert _covers(out["regions"], (9, 1.6))
    # 5" straight down, behind the wall: more than 6" round, so not.
    assert not _covers(out["regions"], (9, 11.5))
    # Round the wall's end, within 6": reachable.
    assert _covers(out["regions"], (12, 9.5))


async def test_infantry_reach_is_a_circle(client: AsyncClient, session, tmp_path):
    game_id, d = await _wall_game(client, session, tmp_path, keywords=["INFANTRY"])
    out = await _reach(client, game_id, d, 6)
    [region] = out["regions"]
    assert _covers(out["regions"], (9, 11.5))
    assert all(
        math.dist((p["x"], p["y"]), (9, 6.5)) == pytest.approx(6, abs=0.01) for p in region
    )
