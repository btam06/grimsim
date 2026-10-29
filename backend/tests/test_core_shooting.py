from httpx import AsyncClient

from app.routers.games import _load_game
from app.services.in_game import deployment, shooting
from tests.test_deployment import R32, _unit_named
from tests.test_movement import _battle
from tests.test_shooting import _place, _shoot, _targets, _to_shooting

# The Core Rules' shooting: engaged targets (17.03), close-quarters shooting
# (10.06) and indirect shooting (10.07). Games on the test layout, the
# defender (seat 2) shooting first; each gun is 1 attack that hits on a 2+.

PISTOL = ("Pistol", "pistol")
INDIRECT = ("Indirect Fire", None)
BLAST = ("Blast", "blast")


async def _game(client, session, tmp_path, d_kwargs=None, a_kwargs=None, e_kwargs=None):
    units = {
        1: [("A", 1, {"weapon_range": 24, **(a_kwargs or {})}),
            ("E", 1, {"weapon_range": 24, **(e_kwargs or {})})],
        2: [("D", 1, {"weapon_range": 24, **(d_kwargs or {})}), ("F", 1, {"weapon_range": 24})],
    }
    spots = {"A": (20, 38), "E": (40, 38), "D": (20, 4), "F": (40, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    await _to_shooting(client, game["id"])
    return game["id"], {u["name"]: u for u in deployment_["units"]}


def _target(targets, unit):
    return next(t for t in targets if t["unit_id"] == unit["unit_id"])


async def test_engaged_units_cant_be_shot_unless_monsters_or_vehicles(
    client: AsyncClient, session, tmp_path
):
    game_id, u = await _game(client, session, tmp_path, e_kwargs={"keywords": ("VEHICLE",)})
    # A engaged with F; E (a VEHICLE) engaged with F too, away from D.
    await _place(session, u["A"], [(40 - 2 * R32 - 1, 4)])
    await _place(session, u["E"], [(40 + 2 * R32 + 1, 4)])
    targets = await _targets(client, game_id, u["D"])
    assert not any(w["in_range"] for w in _target(targets, u["A"])["weapons"])
    assert any(w["in_range"] for w in _target(targets, u["E"])["weapons"])


async def test_close_quarters_shooting_with_a_pistol(client: AsyncClient, session, tmp_path):
    game_id, u = await _game(client, session, tmp_path, d_kwargs={"gun_abilities": (PISTOL,)})
    # D engaged with A: it can shoot A with its pistol - but not E, away.
    await _place(session, u["A"], [(20, 4 + 2 * R32 + 1)])
    targets = await _targets(client, game_id, u["D"])
    assert any(w["in_range"] for w in _target(targets, u["A"])["weapons"])
    assert not any(w["in_range"] for w in _target(targets, u["E"])["weapons"])
    response = await _shoot(client, game_id, u["D"], u["A"])
    assert response.status_code == 200, response.text


async def test_indirect_fire_at_an_unseen_target(client: AsyncClient, session, tmp_path):
    # The test layout's ruin wall is an L at (7, 8): x 7-11 along y 8-8.5. D
    # below it, A right behind it - out of sight.
    game_id, u = await _game(client, session, tmp_path, d_kwargs={"gun_abilities": (INDIRECT,)})
    await _place(session, u["D"], [(9, 4)])
    await _place(session, u["A"], [(9, 9.4)])
    await _place(session, u["E"], [(40, 30)])
    game = await _load_game(session, game_id)
    d_, a_ = (deployment.find_unit(game, u[n]["unit_id"]) for n in "DA")
    reach = shooting.reach(game, d_, a_)
    assert not reach.visible and reach.indirect
    target = _target(await _targets(client, game_id, u["D"]), u["A"])
    assert target["indirect"] and not target["visible"]
    response = await _shoot(client, game_id, u["D"], u["A"])
    assert response.status_code == 200, response.text


async def test_hidden_infantry_are_only_seen_within_15(client: AsyncClient, session, tmp_path):
    # The test layout's Medium ruin area (x 7-13, y 8-12) has a ruin wall in
    # it. A (INFANTRY) in it, below the wall; D shooting from 20" away, then
    # from within 15".
    game_id, u = await _game(client, session, tmp_path, a_kwargs={"keywords": ("INFANTRY",)})
    await _place(session, u["A"], [(11.5, 10.5)])
    await _place(session, u["E"], [(40, 30)])
    await _place(session, u["D"], [(11.5, 31)])
    game = await _load_game(session, game_id)
    d_, a_ = (deployment.find_unit(game, u[n]["unit_id"]) for n in "DA")
    assert not shooting.reach(game, d_, a_).visible
    await _place(session, u["D"], [(11.5, 24)])
    session.expire_all()
    game = await _load_game(session, game_id)
    d_, a_ = (deployment.find_unit(game, u[n]["unit_id"]) for n in "DA")
    reach = shooting.reach(game, d_, a_)
    # Seen - and it has the benefit of cover (INFANTRY within a terrain area).
    assert reach.visible and reach.in_cover


def test_terrain_areas_without_features_dont_obscure():
    from app.services.in_game.deployment import Base

    area = [(10, 10), (14, 10), (14, 14), (10, 14)]
    sight = object.__new__(shooting.Sight)
    sight.terrain = shooting._Terrain([], [area], [False], [False], [])
    viewer, target = Base(12, 4, 32, 32), Base(12, 20, 32, 32)
    assert sight.sees(viewer, target)
    sight.terrain = shooting._Terrain([], [area], [True], [False], [])
    assert not sight.sees(viewer, target)
    # Not from within it.
    assert sight.sees(Base(12, 12, 32, 32), target)
