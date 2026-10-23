import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import GameModelPosition
from app.services.in_game.shooting import _blocks, _obstacles, _visible_region, can_see
from app.services.in_game.terrain import Base
from tests.test_deployment import R32, _deployment, _unit_named
from tests.test_movement import _battle, _move, _shifted

# Games on the test layout (see tests/test_deployment.py), the defender (seat
# 2) shooting first. The layout's one ruin wall is an L at (7, 8): x 7-11
# along y 8-8.5, and down x 7-7.5 to y 11. Its Medium ruin terrain area is
# x 7-13, y 8-12. Each gun is 1 attack that hits on a 2+.

WALL = [(7, 8), (11, 8), (11, 8.5), (7, 8.5)]


# --- line of sight ---


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((9, 4), (9, 14), True),  # straight through
        ((5, 4), (5, 14), False),  # beside it
        ((9, 8.25), (9, 14), True),  # starting inside it
        ((7, 4), (7, 14), False),  # along its edge: touching isn't blocking
        ((3, 8), (14, 8), False),  # along its top edge
        ((3, 8.25), (14, 8.25), True),  # along its middle
        ((12, 4), (12, 14), False),
    ],
)
def test_wall_blocks_a_line(a, b, expected):
    assert _blocks(a, b, WALL) is expected


def test_can_see_past_a_wall():
    behind = Base(9, 14, 32, 32)
    assert not can_see(Base(9, 4, 32, 32), behind, [WALL])
    # Off to the side, some line gets round it.
    assert can_see(Base(12.5, 4, 32, 32), behind, [WALL])
    assert can_see(Base(9, 4, 32, 32), behind, [])


def _reach_at(region, angle_index):
    # How far the region reaches from (0, 0) along ray `angle_index` (of 180,
    # 2 degrees apart).
    x, y = region[angle_index]
    return (x**2 + y**2) ** 0.5


def test_sight_region_stops_at_a_wall():
    # A wall 5" to the right (x 5-6, y -1 to 1): rays that way stop at it.
    wall = [(5, -1), (6, -1), (6, 1), (5, 1)]
    region = _visible_region((0, 0), 20, _obstacles((0, 0), 20, [wall], []))
    assert _reach_at(region, 0) == pytest.approx(5)  # straight at it
    assert _reach_at(region, 90) == pytest.approx(20)  # the other way
    assert _reach_at(region, 45) == pytest.approx(20)  # down: clear


def test_sight_region_sees_into_a_terrain_area_but_not_past_it():
    # An area x 5-8: rays that way stop at its far side.
    area = [(5, -1), (8, -1), (8, 1), (5, 1)]
    region = _visible_region((0, 0), 20, _obstacles((0, 0), 20, [], [area]))
    assert _reach_at(region, 0) == pytest.approx(8)
    assert _reach_at(region, 90) == pytest.approx(20)


def test_sight_region_ignores_far_terrain():
    wall = [(30, -1), (31, -1), (31, 1), (30, 1)]
    assert _obstacles((0, 0), 20, [wall], []) == []


# --- setting up ---


async def _place(session, unit, spots):
    # Puts the unit's models at `spots` directly.
    for model, (x, y) in zip(unit["models"], spots):
        position = (
            await session.execute(
                select(GameModelPosition).where(
                    GameModelPosition.unit_model_id == model["unit_model_id"]
                )
            )
        ).scalar_one()
        position.x, position.y = x, y
    await session.commit()


async def _to_shooting(client, game_id):
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "shooting"
    return game


async def _shooting_game(client, session, tmp_path, d=1, a=1, d_kwargs=None, a_kwargs=None):
    # The defender's unit "D" (d models, a 24" gun each) and the attacker's
    # "A" (a models), in the defender's movement phase.
    units = {
        1: [("A", a, {"weapon_range": 24, **(a_kwargs or {})})],
        2: [("D", d, {"weapon_range": 24, **(d_kwargs or {})})],
    }
    return await _battle(client, session, tmp_path, units=units)


async def _shooting(client, game_id):
    return (await client.get(f"/games/{game_id}/shooting")).json()


async def _targets(client, game_id, unit):
    response = await client.get(f"/games/{game_id}/shooting/targets?unit_id={unit['unit_id']}")
    assert response.status_code == 200, response.text
    return response.json()


async def _shoot(client, game_id, unit, target, weapon_ids=None):
    if weapon_ids is None:
        targets = await _targets(client, game_id, unit)
        weapon_ids = [
            w["id"] for t in targets if t["unit_id"] == target["unit_id"] for w in t["weapons"]
        ]
    return await client.post(
        f"/games/{game_id}/shooting",
        json={
            "unit_id": unit["unit_id"],
            "target_unit_id": target["unit_id"],
            "weapon_ids": weapon_ids,
        },
    )


# --- the flow ---


async def test_shooting_lists_the_turn_players_units(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game = await _to_shooting(client, game["id"])
    [unit] = (await _shooting(client, game["id"]))["units"]
    assert (unit["name"], unit["can_shoot"], unit["shot"]) == ("D", True, None)
    # It didn't move.
    assert (unit["remained_stationary"], unit["moved_less_than_3"], unit["advanced"]) == (
        True, True, False
    )


async def test_no_shooting_outside_the_shooting_phase(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    assert (await _shooting(client, game["id"]))["units"] == []
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    response = await _shoot(client, game["id"], d, a, weapon_ids=[1])
    assert response.status_code == 400
    assert "shooting phase" in response.json()["detail"]


async def test_shoot(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path, d=3, a=5)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    # Within 24" of each other, nothing in the way.
    await _place(session, a, [(20 + i * 1.5, 22) for i in range(5)])
    await _to_shooting(client, game_id)

    [target] = await _targets(client, game_id, d)
    assert (target["name"], target["visible"], target["in_cover"]) == ("A", True, False)
    [gun] = target["weapons"]
    assert (gun["name"], gun["range"], gun["carried_by"], gun["in_range"]) == ("D gun", 24, 3, 3)
    assert not gun["enhancement"]

    response = await _shoot(client, game_id, d, a)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["remained_stationary"], body["in_cover"]) == (True, False)
    # 3 models, 1 attack each.
    assert len(body["combat"]["attack_rolls"]) == 3

    [unit] = (await _shooting(client, game_id))["units"]
    assert unit["shot"]["target_name"] == "A"
    assert unit["shot"]["total_damage"] == body["combat"]["total_damage"]
    assert (unit["can_shoot"], unit["reason"]) == (False, "it has already shot this phase")
    # Once a phase.
    response = await _shoot(client, game_id, d, a, weapon_ids=[gun["id"]])
    assert response.status_code == 400
    assert "already shot" in response.json()["detail"]


async def test_only_models_that_can_see_and_reach_fire(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path, d=2)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    # One of D's models is behind the wall (and the ruin's area) from A; the
    # other has a clear view past it.
    await _place(session, d, [(9, 4), (16, 4)])
    await _place(session, a, [(16, 14)])
    await _to_shooting(client, game_id)
    [target] = await _targets(client, game_id, d)
    assert target["visible"]
    assert target["weapons"][0]["in_range"] == 1
    body = (await _shoot(client, game_id, d, a)).json()
    assert len(body["combat"]["attack_rolls"]) == 1


async def test_cant_shoot_what_it_cant_see(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, d, [(9, 4)])
    await _place(session, a, [(9, 14)])
    await _to_shooting(client, game_id)
    [target] = await _targets(client, game_id, d)
    assert not target["visible"]
    assert target["weapons"][0]["in_range"] == 0
    response = await _shoot(client, game_id, d, a, weapon_ids=[target["weapons"][0]["id"]])
    assert response.status_code == 400
    assert "can see the target" in response.json()["detail"]


async def test_obstacles_dont_block_sight(client: AsyncClient, session, tmp_path):
    # Only ruin walls are dense - the test layout has no obstacle, so a target
    # clear of the wall is seen whatever else is between.
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, d, [(30, 4)])
    await _place(session, a, [(30, 25)])
    await _to_shooting(client, game_id)
    [target] = await _targets(client, game_id, d)
    assert target["visible"]


async def test_range(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, d, [(30, 4)])
    # 24.5" base to base: out of range of a 24" gun.
    await _place(session, a, [(30, 4 + 2 * R32 + 24.5)])
    await _to_shooting(client, game_id)
    [target] = await _targets(client, game_id, d)
    assert target["visible"]
    assert (target["weapons"][0]["in_range"], target["weapons"][0]["half_range"]) == (0, False)
    response = await _shoot(client, game_id, d, a, weapon_ids=[target["weapons"][0]["id"]])
    assert "can't reach" in response.json()["detail"]


async def test_half_range(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, d, [(30, 4)])
    await _place(session, a, [(30, 4 + 2 * R32 + 11)])
    await _to_shooting(client, game_id)
    [target] = await _targets(client, game_id, d)
    assert (target["weapons"][0]["in_range"], target["weapons"][0]["half_range"]) == (1, True)


@pytest.mark.parametrize(
    "keywords,expected", [(["INFANTRY"], True), (["BEAST"], True), (["SWARM"], True), ([], False)]
)
async def test_cover_on_a_terrain_area(
    client: AsyncClient, session, tmp_path, keywords, expected
):
    game, deployment = await _shooting_game(
        client, session, tmp_path, a_kwargs={"keywords": keywords}
    )
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, d, [(20, 4)])
    # On the Medium ruin's terrain area, clear of its wall.
    await _place(session, a, [(12, 11)])
    await _to_shooting(client, game_id)
    [target] = await _targets(client, game_id, d)
    assert target["visible"]
    assert target["in_cover"] is expected
    body = (await _shoot(client, game_id, d, a)).json()
    assert body["in_cover"] is expected


async def test_infantry_off_terrain_isnt_in_cover(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(
        client, session, tmp_path, a_kwargs={"keywords": ["INFANTRY"]}, a=2
    )
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, d, [(20, 4)])
    # One model on the terrain area, one off it.
    await _place(session, a, [(12, 11), (14.5, 11)])
    await _to_shooting(client, game_id)
    [target] = await _targets(client, game_id, d)
    assert not target["in_cover"]


# --- terrain areas ---


async def _area_game(client, session, tmp_path):
    # The Medium ruin's terrain area (x 7-13, y 8-12) between D and A, off to
    # the side of its wall (x 7-11 at y 8-8.5).
    game, deployment = await _shooting_game(client, session, tmp_path, a=2)
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, d, [(12, 4)])
    return game, d, a


async def test_terrain_area_blocks_sight_between_units_off_it(
    client: AsyncClient, session, tmp_path
):
    game, d, a = await _area_game(client, session, tmp_path)
    # Straight behind it, clear of the wall: only the area is in the way.
    await _place(session, a, [(12, 16), (12, 17.5)])
    await _to_shooting(client, game["id"])
    [target] = await _targets(client, game["id"], d)
    assert not target["visible"]


async def test_terrain_area_doesnt_block_a_unit_touching_it(
    client: AsyncClient, session, tmp_path
):
    # One of the target's models touches the area: it no longer hides them.
    game, d, a = await _area_game(client, session, tmp_path)
    await _place(session, a, [(12, 16), (13.5, 12.5)])
    await _to_shooting(client, game["id"])
    [target] = await _targets(client, game["id"], d)
    assert target["visible"]
    # Both models can be seen through it (not just the one on it).
    assert target["weapons"][0]["in_range"] == 1


async def test_terrain_area_doesnt_block_a_shooter_touching_it(
    client: AsyncClient, session, tmp_path
):
    game, d, a = await _area_game(client, session, tmp_path)
    await _place(session, d, [(12, 7.6)])
    await _place(session, a, [(12, 16), (12, 17.5)])
    await _to_shooting(client, game["id"])
    [target] = await _targets(client, game["id"], d)
    assert target["visible"]


async def test_sight_bubble(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path, d=2)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    await _place(session, d, [(12, 4), (13.5, 4)])
    await _to_shooting(client, game_id)
    response = await client.get(f"/games/{game_id}/shooting/bubble?unit_id={d['unit_id']}")
    assert response.status_code == 200, response.text
    bubble = response.json()
    assert bubble["range"] == 24
    # 2 models, each seen from its centre and 4 points round its base.
    assert len(bubble["regions"]) == 10
    centre = bubble["regions"][0]
    # Straight down (ray 45 of 180) from (12, 4): through the Medium ruin's
    # area (y 8-12), which hides what's past it.
    assert centre[45]["y"] == pytest.approx(12, abs=0.01)
    # Straight up: to the range, 24" plus the base.
    assert centre[135]["y"] == pytest.approx(4 - 24 - R32, abs=0.01)


async def test_sight_bubble_only_counts_assault_after_advancing(
    client: AsyncClient, session, tmp_path
):
    game, deployment = await _shooting_game(
        client, session, tmp_path, d_kwargs={"assault_range": 12}
    )
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _advance(client, session, game_id, d, a)
    bubble = (await client.get(f"/games/{game_id}/shooting/bubble?unit_id={d['unit_id']}")).json()
    assert bubble["range"] == 12


# --- how it moved ---


async def test_moved_less_than_3(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    assert (await _move(client, game_id, d, "normal", _shifted(d, dy=2))).status_code == 200
    await _to_shooting(client, game_id)
    [unit] = (await _shooting(client, game_id))["units"]
    assert (unit["remained_stationary"], unit["moved_less_than_3"], unit["advanced"]) == (
        False, True, False
    )
    assert unit["distance"] == pytest.approx(2)


async def test_moved_3_or_more(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    assert (await _move(client, game_id, d, "normal", _shifted(d, dy=3))).status_code == 200
    await _to_shooting(client, game_id)
    [unit] = (await _shooting(client, game_id))["units"]
    assert (unit["remained_stationary"], unit["moved_less_than_3"]) == (False, False)


async def test_normal_move_going_nowhere_is_remaining_stationary(
    client: AsyncClient, session, tmp_path
):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d = _unit_named(deployment, "D")
    assert (await _move(client, game_id, d, "normal", _shifted(d))).status_code == 200
    await _to_shooting(client, game_id)
    [unit] = (await _shooting(client, game_id))["units"]
    assert unit["remained_stationary"]


async def _advance(client, session, game_id, d, a):
    # D Advances 1"; A stands 18" off, in the open.
    await client.post(f"/games/{game_id}/movement/advance", json={"unit_id": d["unit_id"]})
    assert (await _move(client, game_id, d, "advance", _shifted(d, dy=1))).status_code == 200
    await _place(session, a, [(20, 22)])
    await _to_shooting(client, game_id)


async def test_advanced_unit_without_assault_weapons_cant_shoot(
    client: AsyncClient, session, tmp_path
):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _advance(client, session, game_id, d, a)
    [unit] = (await _shooting(client, game_id))["units"]
    assert (unit["advanced"], unit["can_shoot"]) == (True, False)
    assert unit["reason"] == "it Advanced, and has no Assault weapons"
    response = await _shoot(client, game_id, d, a, weapon_ids=[1])
    assert response.status_code == 400
    assert "no Assault weapons" in response.json()["detail"]


async def test_advanced_unit_shoots_only_assault_weapons(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(
        client, session, tmp_path, d=2, d_kwargs={"assault_range": 24}
    )
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _advance(client, session, game_id, d, a)
    [unit] = (await _shooting(client, game_id))["units"]
    assert (unit["advanced"], unit["can_shoot"]) == (True, True)

    [target] = await _targets(client, game_id, d)
    weapons = {w["name"]: w for w in target["weapons"]}
    gun, assault_gun = weapons["D gun"], weapons["D assault gun"]
    assert (gun["assault"], gun["unusable"], gun["in_range"]) == (False, True, 0)
    assert (assault_gun["assault"], assault_gun["unusable"], assault_gun["in_range"]) == (
        True, False, 2
    )
    # The plain gun can't be chosen.
    response = await _shoot(client, game_id, d, a, weapon_ids=[gun["id"], assault_gun["id"]])
    assert response.status_code == 400
    assert "only shoot Assault weapons" in response.json()["detail"]
    body = (await _shoot(client, game_id, d, a, weapon_ids=[assault_gun["id"]])).json()
    assert body["advanced"]
    assert [wr["name"] for wr in body["combat"]["weapon_results"]] == ["D assault gun"]
    assert len(body["combat"]["attack_rolls"]) == 2


async def test_unit_that_didnt_advance_shoots_everything(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(
        client, session, tmp_path, d_kwargs={"assault_range": 24}
    )
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    await _place(session, a, [(20, 22)])
    await _to_shooting(client, game_id)
    [target] = await _targets(client, game_id, d)
    assert [(w["unusable"], w["in_range"]) for w in target["weapons"]] == [(False, 1), (False, 1)]
    body = (await _shoot(client, game_id, d, a)).json()
    assert len(body["combat"]["attack_rolls"]) == 2


async def test_fell_back_cant_shoot(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    x = d["models"][0]["position"]["x"]
    await _place(session, a, [(x + 2 * R32 + 0.5, 4)])
    response = await _move(client, game_id, d, "fall_back", _shifted(d, dx=-3))
    assert response.status_code == 200, response.text
    await _to_shooting(client, game_id)
    [unit] = (await _shooting(client, game_id))["units"]
    assert (unit["can_shoot"], unit["reason"]) == (False, "it Fell Back this turn")


async def test_engaged_unit_cant_shoot(client: AsyncClient, session, tmp_path):
    game, deployment = await _shooting_game(client, session, tmp_path)
    game_id = game["id"]
    d, a = _unit_named(deployment, "D"), _unit_named(deployment, "A")
    x = d["models"][0]["position"]["x"]
    await _to_shooting(client, game_id)
    await _place(session, a, [(x + 2 * R32 + 0.5, 4)])
    [unit] = (await _shooting(client, game_id))["units"]
    assert unit["reason"] == "it's within Engagement Range of an enemy unit"
