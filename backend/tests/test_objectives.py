import math

from httpx import AsyncClient

from app.routers.games import _load_game
from app.services.in_game import deployment, regions
from tests.test_casualties import _set_models
from tests.test_deployment import _deployment, _unit_named
from tests.test_movement import _battle
from tests.test_shooting import _place

# Games on the test layout ("Strips": the attacker, seat 1, deploys along y
# 32-44, the defender, seat 2, along y 0-12). Its one objective is the Medium
# ruin's terrain area (x 7-13, y 8-12), a central objective. A and D have 2
# models each, OC 1.

UNITS = {1: [("A", 2, {})], 2: [("D", 2, {})]}
ON_THE_RUIN = [(9, 10), (11, 10)]


async def _objective(client, game_id):
    [objective] = (await _deployment(client, game_id))["objectives"]
    return objective


async def test_the_player_with_more_oc_on_it_controls_it(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    objective = await _objective(client, game_id)
    assert (objective["kind"], objective["oc"], objective["live_controller"]) == (
        "centre", {"1": 0, "2": 0}, None
    )

    # D's two models on it: seat 2 would control it (as determined at the end
    # of the phase).
    await _place(session, d, ON_THE_RUIN)
    objective = await _objective(client, game_id)
    assert (objective["oc"], objective["live_controller"]) == ({"1": 0, "2": 2}, 2)

    # One of A's too (any part of its base over the area counts): 1 to 2.
    await _place(session, a, [(10, 12.5), (10, 14)])
    objective = await _objective(client, game_id)
    assert (objective["oc"], objective["live_controller"]) == ({"1": 1, "2": 2}, 2)

    # Both of A's: a tie - no one controls it.
    await _place(session, a, [(8, 9), (12, 11)])
    objective = await _objective(client, game_id)
    assert (objective["oc"], objective["live_controller"]) == ({"1": 2, "2": 2}, None)


async def test_control_is_determined_at_the_end_of_each_phase(
    client: AsyncClient, session, tmp_path
):
    # 14.02: D moves onto it mid-phase - nobody controls it until the phase
    # ends; then seat 2 does, even once D's moved off, until the next ends.
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    d = _unit_named(deployment_, "D")
    await _place(session, d, ON_THE_RUIN)
    objective = await _objective(client, game_id)
    assert (objective["controller"], objective["live_controller"]) == (None, 2)
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 200
    objective = await _objective(client, game_id)
    assert (objective["controller"], objective["live_controller"]) == (2, 2)
    await _place(session, d, [(30, 6), (31.5, 6)])
    objective = await _objective(client, game_id)
    assert (objective["controller"], objective["live_controller"]) == (2, None)
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 200
    assert (await _objective(client, game_id))["controller"] is None


async def test_no_one_controls_it_with_0_oc(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    d = _unit_named(deployment_, "D")
    await _set_models(session, d, oc=0)
    await _place(session, d, ON_THE_RUIN)
    objective = await _objective(client, game["id"])
    assert (objective["oc"], objective["controller"]) == ({"1": 0, "2": 0}, None)


async def test_territories_and_no_mans_land(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    territory = (await _deployment(client, game_id))["territory"]
    # The zones are at the top and bottom: halved across the middle.
    assert territory["split"] == "horizontal"
    corners = {seat: {(p["x"], p["y"]) for p in t} for seat, t in territory["territories"].items()}
    assert corners["1"] == {(0, 22), (60, 22), (60, 44), (0, 44)}
    assert corners["2"] == {(0, 0), (60, 0), (60, 22), (0, 22)}

    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    # A: one model in its zone, one just out of it (in No Man's Land).
    await _place(session, a, [(20, 33), (20, 30)])
    # D: wholly in No Man's Land, in seat 1's territory.
    await _place(session, d, [(30, 25), (31.5, 25)])
    loaded = await _load_game(session, game_id)
    unit_a, unit_d = (deployment.find_unit(loaded, u["unit_id"]) for u in (a, d))
    zone_1 = regions.deployment_zone(loaded, 1)
    assert regions.unit_within(loaded, unit_a, zone_1)
    assert not regions.unit_wholly_within(loaded, unit_a, zone_1)
    assert regions.unit_within_no_mans_land(loaded, unit_a)
    assert not regions.unit_wholly_within_no_mans_land(loaded, unit_a)
    assert regions.unit_wholly_within_no_mans_land(loaded, unit_d)
    assert regions.unit_wholly_within(loaded, unit_d, regions.territory(loaded, 1))
    assert not regions.unit_within(loaded, unit_d, regions.territory(loaded, 2))


def _fake_game(attacker_zone, defender_zone, name="Test deployment"):
    # Just what regions needs: the layout's deployment (its name and zones),
    # and who's the attacker.
    from types import SimpleNamespace

    zones = {"attacker": attacker_zone, "defender": defender_zone}
    deployment_ = SimpleNamespace(name=name, zone=lambda side: zones[side])
    return SimpleNamespace(layout=SimpleNamespace(deployment=deployment_), attacker_seat=1)


def test_search_and_destroy_territories_are_split_corner_to_corner():
    # Opposite table quarters (attacker bottom-left, defender top-right), less
    # a circle round the centre: the territory line runs from the top-left
    # corner to the bottom-right one - the corners neither zone is in.
    angles = [math.radians(d) for d in range(0, 91, 10)]
    arc = [(30 - 9 * math.cos(a), 22 + 9 * math.sin(a)) for a in angles]
    attacker = [(0, 44), (0, 22), *arc, (30, 44)]
    defender = [(60, 0), (60, 22), *[(60 - x, 44 - y) for x, y in arc], (30, 0)]
    game = _fake_game(attacker, defender)
    assert regions.split(game) == "diagonal"
    assert set(regions.split_line(game)) == {(0, 0), (60, 44)}
    assert set(regions.territory(game, 1)) == {(0, 0), (60, 44), (0, 44)}
    assert set(regions.territory(game, 2)) == {(0, 0), (60, 44), (60, 0)}


def test_sweeping_engagement_territories_are_split_by_its_slanted_line():
    # Its card draws the line from the left edge, 19" down, to the right
    # edge, 25" down - not straight across the middle.
    game = _fake_game(
        [(0, 44), (0, 30), (30, 30), (30, 36), (60, 36), (60, 44)],
        [(60, 0), (60, 14), (30, 14), (30, 8), (0, 8), (0, 0)],
        name="Sweeping Engagement",
    )
    assert regions.split(game) == "slanted"
    assert set(regions.split_line(game)) == {(0, 19), (60, 25)}
    assert set(regions.territory(game, 1)) == {(0, 19), (60, 25), (60, 44), (0, 44)}
    assert set(regions.territory(game, 2)) == {(0, 19), (60, 25), (60, 0), (0, 0)}
    # (5, 20) is below the line at the left edge, in the attacker's half;
    # (55, 24) is above it at the right, in the defender's.
    assert regions.point_in((5, 20), regions.territory(game, 1))
    assert regions.point_in((55, 24), regions.territory(game, 2))


def test_side_by_side_zones_split_down_the_middle():
    game = _fake_game(
        [(0, 0), (18, 0), (18, 44), (0, 44)], [(42, 0), (60, 0), (60, 44), (42, 44)]
    )
    assert regions.split(game) == "vertical"
    assert set(regions.territory(game, 1)) == {(0, 0), (30, 0), (30, 44), (0, 44)}
