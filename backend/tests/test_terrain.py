import json

import pytest
from httpx import AsyncClient

from app.models import (
    TerrainArea,
    TerrainAreaShape,
    TerrainAreaShapePoint,
    TerrainFeature,
    TerrainFeatureShape,
    TerrainFeatureShapePart,
    TerrainLayout,
)
from app.services.in_game.terrain import (
    Base,
    area_polygon,
    base_dimensions,
    base_terrain,
    is_convex,
    rectangle,
    within,
    wholly_within,
)
from app.seeds import data_files
from app.seeds import terrain_layouts as terrain_seed
from tests.test_games import _game_payload, _setup

# A 32mm base has a radius of 0.63"; 25.4mm is exactly 1".
R32 = 32 / 2 / 25.4


def _base(x, y, mm=32.0, height_mm=None, rotation=0):
    return Base(x=x, y=y, width_mm=mm, height_mm=height_mm or mm, rotation=rotation)


# --- base sizes ---


@pytest.mark.parametrize(
    "name,expected",
    [
        ("32mm", (32.0, 32.0)),
        ("28.5mm", (28.5, 28.5)),
        ("105 x 70mm", (105.0, 70.0)),
        ("Use model", None),
        ("Small flying base", None),
    ],
)
def test_base_dimensions(name, expected):
    assert base_dimensions(name) == expected


# --- a 6" x 4" area centred on (10, 10): x 7-13, y 8-12 ---

AREA = rectangle(10, 10, 6, 4, 0)


def test_base_in_the_middle_is_wholly_within():
    assert within(_base(10, 10), AREA)
    assert wholly_within(_base(10, 10), AREA)


@pytest.mark.parametrize(
    "x,expected_within,expected_wholly",
    [
        (13 - R32 - 0.01, True, True),  # just inside the right edge
        (13 - R32 + 0.01, True, False),  # just over it
        (13 + R32 - 0.01, True, False),  # centre outside, edge still over the area
        (13 + R32 + 0.01, False, False),  # clear of it
    ],
)
def test_base_near_an_edge(x, expected_within, expected_wholly):
    base = _base(x, 10)
    assert within(base, AREA) is expected_within
    assert wholly_within(base, AREA) is expected_wholly


def test_touching_an_edge_counts_as_within():
    assert within(_base(13 + R32, 10), AREA)


@pytest.mark.parametrize(
    "x,y",
    [(7 + R32 - 0.01, 10), (10, 8 + R32 - 0.01), (10, 12 - R32 + 0.01)],
)
def test_every_edge_bounds_wholly_within(x, y):
    assert not wholly_within(_base(x, y), AREA)


def test_corner_is_checked_as_a_corner_not_a_box():
    # Diagonally off the corner (13, 12): the base's bounding box overlaps the
    # area, but the base itself doesn't reach it.
    offset = R32 * 0.8
    assert not within(_base(13 + offset, 12 + offset), AREA)


# --- rotation ---


def test_rotated_area():
    # A 2" square turned 45 degrees is a diamond reaching 1.414" along each
    # axis; its inscribed circle has a radius of 1".
    diamond = rectangle(0, 0, 2, 2, 45)
    assert wholly_within(_base(0, 0), diamond)  # radius 0.63"
    assert not wholly_within(_base(0, 0, mm=53.34), diamond)  # radius 1.05"
    assert within(_base(2 ** 0.5 + 0.5, 0), diamond)  # 0.5" off its point
    assert not within(_base(2 ** 0.5 + 0.7, 0), diamond)
    # Unrotated, the same square's corner is at (1, 1): that base reaches it.
    assert within(_base(1 + 0.4, 1 + 0.4), rectangle(0, 0, 2, 2, 0))
    assert not within(_base(1 + 0.4, 1 + 0.4), diamond)


def test_oval_base_turns():
    # 105 x 70mm: semi-axes of 2.07" and 1.38", in a 5" x 3" area.
    area = rectangle(0, 0, 5, 3, 0)
    assert wholly_within(_base(0, 0, mm=105, height_mm=70), area)
    turned = _base(0, 0, mm=105, height_mm=70, rotation=90)
    assert within(turned, area)
    assert not wholly_within(turned, area)


# --- a layout's areas and features: kit shapes, placed ---

RECT_6X4 = TerrainAreaShape(name="Medium ruin", count=4, width=6, height=4)
RECT_6X4.points = []


def _wall_shape():
    # An L-shaped wall with its corner at its position: a 4" leg along x and a
    # 3" leg along y, 0.5" thick.
    shape = TerrainFeatureShape(name="Wall L", kind="ruin_wall", count=2)
    shape.parts = [
        TerrainFeatureShapePart(x=0, y=0, width=4, height=0.5),
        TerrainFeatureShapePart(x=0, y=0, width=0.5, height=3),
    ]
    return shape


def _layout(wall_rotation=0, wall_mirrored=False):
    # A 6" x 4" area centred on (10, 10), and the wall placed with its corner
    # at (7, 8): along the top and down the left side of the area.
    layout = TerrainLayout(name="Test")
    layout.areas = [TerrainArea(id=1, shape=RECT_6X4, x=10, y=10, rotation=0, mirrored=False)]
    layout.features = [
        TerrainFeature(
            id=2, shape=_wall_shape(), x=7, y=8, rotation=wall_rotation, mirrored=wall_mirrored
        )
    ]
    return layout


def test_base_terrain_reports_each_area_and_feature():
    areas, features = base_terrain(_layout(), _base(10, 10))
    assert [(a.id, a.within, a.wholly_within) for a in areas] == [(1, True, True)]
    # 1.37" from the wall's nearest part: not on it.
    assert [(f.id, f.within, f.wholly_within) for f in features] == [(2, False, False)]


def test_base_on_a_wall_is_within_it_but_not_wholly():
    # Centred on the wall's top leg: within it, but a 32mm base is wider than
    # the 0.5" wall.
    _, [wall] = base_terrain(_layout(), _base(9, 8.25))
    assert (wall.within, wall.wholly_within) == (True, False)


def test_small_base_wholly_within_a_wall():
    # A 10mm base (0.2" radius) fits on the 0.5" wall.
    _, [wall] = base_terrain(_layout(), _base(9, 8.25, mm=10))
    assert (wall.within, wall.wholly_within) == (True, True)


def test_rotated_feature_turns_about_its_position():
    # Turned 90 degrees clockwise about (7, 8), the 4" leg now runs down from
    # (7, 8) to (7, 12), to the left of x=7 (x 6.5-7).
    _, [wall] = base_terrain(_layout(wall_rotation=90), _base(6.75, 10, mm=10))
    assert (wall.within, wall.wholly_within) == (True, True)
    _, [wall] = base_terrain(_layout(wall_rotation=90), _base(9, 8.25, mm=10))
    assert not wall.within


def test_mirrored_feature_is_flipped_before_it_turns():
    # Flipped, the 4" leg runs left from (7, 8) to (3, 8) instead of right.
    _, [wall] = base_terrain(_layout(wall_mirrored=True), _base(5, 8.25, mm=10))
    assert (wall.within, wall.wholly_within) == (True, True)
    _, [wall] = base_terrain(_layout(wall_mirrored=True), _base(9, 8.25, mm=10))
    assert not wall.within


# --- polygonal terrain areas ---


def _triangle_area(rotation=0, mirrored=False):
    # A right triangle with its corner at its position: legs 6" along x and 6"
    # along y (before rotation), placed at (10, 10).
    shape = TerrainAreaShape(name="Triangle", count=1, width=6, height=6)
    shape.points = [
        TerrainAreaShapePoint(x=0, y=0),
        TerrainAreaShapePoint(x=6, y=0),
        TerrainAreaShapePoint(x=0, y=6),
    ]
    return TerrainArea(id=3, shape=shape, x=10, y=10, rotation=rotation, mirrored=mirrored)


def test_polygon_area_corners():
    assert area_polygon(_triangle_area()) == [(10, 10), (16, 10), (10, 16)]


def test_mirrored_polygon_area():
    # Flipped: its corners at (10, 10), (4, 10) and (10, 16).
    assert sorted(area_polygon(_triangle_area(mirrored=True))) == [(4, 10), (10, 10), (10, 16)]


def test_base_in_a_polygon_area():
    triangle = area_polygon(_triangle_area())
    # Near the right angle: wholly within.
    assert wholly_within(_base(11.5, 11.5), triangle)
    # Beyond the hypotenuse (x + y = 26), but its edge reaches over it.
    assert within(_base(13.4, 13.4), triangle)
    assert not wholly_within(_base(13.4, 13.4), triangle)
    assert not within(_base(14, 14), triangle)


def test_rotated_polygon_area():
    # Turned 90 degrees clockwise about (10, 10): the triangle now runs from
    # (10, 10) down to (10, 16) and left to (4, 10).
    triangle = area_polygon(_triangle_area(rotation=90))
    assert wholly_within(_base(8.5, 11.5), triangle)
    assert not within(_base(11.5, 11.5), triangle)


@pytest.mark.parametrize(
    "points,expected",
    [
        ([(0, 0), (4, 0), (4, 2), (0, 2)], True),
        ([(0, 0), (4, 0), (0, 2)], True),
        ([(0, 0), (4, 0), (2, 1), (4, 2), (0, 2)], False),  # a notch
        ([(0, 0), (4, 0)], False),
    ],
)
def test_is_convex(points, expected):
    assert is_convex(points) is expected


# --- seeding, the API, and games ---

KIT = {
    "area_shapes": [
        {"name": "Medium ruin", "count": 2, "width": 6, "height": 4},
        {"name": "Triangle", "count": 1, "points": [[0, 0], [6, 0], [0, 4]]},
    ],
    "feature_shapes": [
        {
            "name": "Wall L",
            "kind": "ruin_wall",
            "count": 1,
            "parts": [
                {"x": 0, "y": 0, "width": 4, "height": 0.5},
                {"x": 0, "y": 0, "width": 0.5, "height": 3},
            ],
        }
    ],
    "deployments": [
        {
            "name": "Strips",
            "attacker_zone": [[0, 32], [60, 32], [60, 44], [0, 44]],
            "defender_zone": [[0, 0], [60, 0], [60, 12], [0, 12]],
        }
    ],
}


def _layout_file(tmp_path, attacker="Disposition 1", defender="Disposition 2", **overrides):
    layout = {
        "name": "Test Layout",
        "attacker_disposition": attacker,
        "defender_disposition": defender,
        "areas": [
            {"shape": "Medium ruin", "x": 10, "y": 10, "rotation": 0},
            {"shape": "Triangle", "x": 30, "y": 20, "rotation": 15, "mirrored": True},
        ],
        "features": [{"shape": "Wall L", "x": 7, "y": 8, "rotation": 0}],
        "deployment": "Strips",
        # The Medium ruin's area (x 7-13, y 8-12) is an objective.
        "objectives": [{"kind": "centre", "x": 10, "y": 10, "areas": [0]}],
    }
    layout.update(overrides)
    path = tmp_path / "terrain_layouts.json"
    path.write_text(json.dumps({**KIT, "layouts": [layout]}))
    return path


async def _seeded(client, session, tmp_path, **kwargs):
    ids = await _setup(client)
    await terrain_seed.seed(session, _layout_file(tmp_path, **kwargs))
    layouts = (await client.get("/terrain-layouts")).json()
    return ids, layouts


async def test_seeded_layout_is_listed(client: AsyncClient, session, tmp_path):
    ids, [layout] = await _seeded(client, session, tmp_path)
    assert layout["name"] == "Test Layout"
    assert layout["attacker_disposition_id"] == ids["disposition1"]
    medium, triangle = layout["areas"]
    assert (medium["shape_name"], medium["width"], medium["height"]) == ("Medium ruin", 6, 4)
    assert medium["points"] == []
    # The flipped triangle's points come out flipped.
    assert triangle["mirrored"] is True
    assert sorted((p["x"], p["y"]) for p in triangle["points"]) == [(-6, 0), (0, 0), (0, 4)]
    [wall] = layout["features"]
    assert (wall["shape_name"], wall["kind"], len(wall["parts"])) == ("Wall L", "ruin_wall", 2)
    # Seeding again adds nothing.
    await terrain_seed.seed(session, _layout_file(tmp_path))
    assert len((await client.get("/terrain-layouts")).json()) == 1


async def test_layout_has_its_deployment_zones(client: AsyncClient, session, tmp_path):
    _, [layout] = await _seeded(client, session, tmp_path)
    deployment = layout["deployment"]
    assert deployment["name"] == "Strips"
    # Corners in the file's order.
    assert [(p["x"], p["y"]) for p in deployment["attacker_zone"]] == [
        (0, 32), (60, 32), (60, 44), (0, 44)
    ]
    assert [(p["x"], p["y"]) for p in deployment["defender_zone"]] == [
        (0, 0), (60, 0), (60, 12), (0, 12)
    ]
    # And on its own endpoint.
    one = (await client.get(f"/terrain-layouts/{layout['id']}")).json()
    assert one["deployment"] == deployment


async def test_layout_without_a_deployment(client: AsyncClient, session, tmp_path):
    _, [layout] = await _seeded(client, session, tmp_path, deployment=None)
    assert layout["deployment"] is None


async def test_seeded_layout_gains_a_deployment_added_later(
    client: AsyncClient, session, tmp_path
):
    await _seeded(client, session, tmp_path, deployment=None)
    await terrain_seed.seed(session, _layout_file(tmp_path))
    [layout] = (await client.get("/terrain-layouts")).json()
    assert layout["deployment"]["name"] == "Strips"


async def test_seed_rejects_an_unknown_deployment(client: AsyncClient, session, tmp_path):
    await _setup(client)
    with pytest.raises(ValueError, match="unknown deployment"):
        await terrain_seed.seed(session, _layout_file(tmp_path, deployment="Nope"))


def test_deployment_zone_needs_three_corners():
    with pytest.raises(ValueError, match="at least 3 corners"):
        terrain_seed.deployment(
            {"name": "Bad", "attacker_zone": [[0, 0], [1, 0]], "defender_zone": [[0, 0], [1, 0], [1, 1]]}
        )


async def test_layout_has_its_objectives(client: AsyncClient, session, tmp_path):
    _, [layout] = await _seeded(client, session, tmp_path)
    [objective] = layout["objectives"]
    medium = layout["areas"][0]
    assert (objective["kind"], objective["x"], objective["y"]) == ("centre", 10, 10)
    assert objective["area_ids"] == [medium["id"]]


async def test_seeded_layout_gains_objectives_added_later(
    client: AsyncClient, session, tmp_path
):
    await _seeded(client, session, tmp_path, objectives=[])
    await terrain_seed.seed(session, _layout_file(tmp_path))
    [layout] = (await client.get("/terrain-layouts")).json()
    assert [o["kind"] for o in layout["objectives"]] == ["centre"]


@pytest.mark.parametrize(
    "objective,message",
    [
        ({"kind": "nope", "x": 0, "y": 0, "areas": [0]}, "unknown kind"),
        ({"kind": "centre", "x": 0, "y": 0, "areas": [5]}, "without its terrain areas"),
        ({"kind": "centre", "x": 0, "y": 0, "areas": []}, "without its terrain areas"),
    ],
)
async def test_seed_rejects_a_bad_objective(
    client: AsyncClient, session, tmp_path, objective, message
):
    await _setup(client)
    with pytest.raises(ValueError, match=message):
        await terrain_seed.seed(session, _layout_file(tmp_path, objectives=[objective]))


async def test_seed_rejects_an_unknown_disposition(client: AsyncClient, session, tmp_path):
    with pytest.raises(ValueError, match="unknown disposition"):
        await terrain_seed.seed(session, _layout_file(tmp_path, attacker="Nope"))


async def test_seed_rejects_an_unknown_shape(client: AsyncClient, session, tmp_path):
    await _setup(client)
    path = _layout_file(tmp_path, features=[{"shape": "Nope", "x": 0, "y": 0}])
    with pytest.raises(ValueError, match="unknown feature shape"):
        await terrain_seed.seed(session, path)


async def test_seed_rejects_more_of_a_shape_than_the_kit_has(
    client: AsyncClient, session, tmp_path
):
    # The kit has one Wall L.
    await _setup(client)
    path = _layout_file(
        tmp_path,
        features=[{"shape": "Wall L", "x": 7, "y": 8}, {"shape": "Wall L", "x": 20, "y": 8}],
    )
    with pytest.raises(ValueError, match="kit has 1"):
        await terrain_seed.seed(session, path)


async def test_layout_can_leave_out_some_of_the_kit(client: AsyncClient, session, tmp_path):
    await _setup(client)
    await terrain_seed.seed(session, _layout_file(tmp_path, features=[]))
    [layout] = (await client.get("/terrain-layouts")).json()
    assert layout["features"] == []


async def test_seed_rejects_a_concave_area_shape(client: AsyncClient, session, tmp_path):
    await _setup(client)
    path = tmp_path / "terrain_layouts.json"
    path.write_text(
        json.dumps(
            {
                "area_shapes": [
                    {"name": "Notched", "count": 1,
                     "points": [[0, 0], [4, 0], [2, 1], [4, 2], [0, 2]]}
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="convex"):
        await terrain_seed.seed(session, path)


async def test_base_position_endpoint(client: AsyncClient, session, tmp_path):
    _, [layout] = await _seeded(client, session, tmp_path)
    base_size = (await client.post("/base-sizes", json={"name": "32mm"})).json()
    url = f"/terrain-layouts/{layout['id']}/base-position"

    response = await client.post(url, json={"x": 10, "y": 10, "base_size_id": base_size["id"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(a["within"], a["wholly_within"]) for a in body["areas"]] == [
        (True, True),
        (False, False),
    ]
    assert [(f["within"], f["wholly_within"]) for f in body["features"]] == [(False, False)]

    # Or sized in mm: a 10mm base on the wall.
    body = (await client.post(url, json={"x": 9, "y": 8.25, "width_mm": 10})).json()
    assert [(f["within"], f["wholly_within"]) for f in body["features"]] == [(True, True)]


@pytest.mark.parametrize(
    "payload",
    [
        {"x": 0, "y": 0},  # no size
        {"x": 0, "y": 0, "base_size_id": 1, "width_mm": 32},  # both
        {"x": 0, "y": 0, "height_mm": 20},  # height without width
    ],
)
async def test_base_position_needs_one_size(client: AsyncClient, session, tmp_path, payload):
    _, [layout] = await _seeded(client, session, tmp_path)
    response = await client.post(f"/terrain-layouts/{layout['id']}/base-position", json=payload)
    assert response.status_code == 422


async def test_base_position_rejects_a_base_without_measurements(
    client: AsyncClient, session, tmp_path
):
    _, [layout] = await _seeded(client, session, tmp_path)
    use_model = (await client.post("/base-sizes", json={"name": "Use model"})).json()
    response = await client.post(
        f"/terrain-layouts/{layout['id']}/base-position",
        json={"x": 0, "y": 0, "base_size_id": use_model["id"]},
    )
    assert response.status_code == 400


async def test_unknown_layout_is_404(client: AsyncClient):
    assert (await client.get("/terrain-layouts/9999")).status_code == 404


@pytest.mark.parametrize("attacker,expected", [(1, True), (2, False)])
async def test_game_gets_a_layout_for_the_attacker_and_defender_dispositions(
    client: AsyncClient, session, tmp_path, attacker, expected
):
    # The layout is for Disposition 1 attacking Disposition 2: only a game with
    # seat 1 (Disposition 1) as the attacker fits it.
    ids, [layout] = await _seeded(client, session, tmp_path)
    response = await client.post("/games", json=_game_payload(ids, attacker=attacker))
    assert response.status_code == 201, response.text
    game = response.json()
    if expected:
        assert game["terrain_layout_id"] == layout["id"]
        assert game["terrain_layout_name"] == "Test Layout"
    else:
        assert game["terrain_layout_id"] is None
    # It's kept: reading the game again gives the same layout.
    again = (await client.get(f"/games/{game['id']}")).json()
    assert again["terrain_layout_id"] == game["terrain_layout_id"]
    assert (await client.delete(f"/games/{game['id']}")).status_code == 204


# --- the local layouts data file (app/data/terrain_layouts.json), if present ---

LOCAL = terrain_seed.load(data_files.DATA_DIR / "terrain_layouts.json")


@pytest.mark.skipif(not LOCAL["layouts"], reason="no local terrain layouts data")
def test_local_kit_shapes_are_valid():
    for entry in LOCAL["area_shapes"]:
        terrain_seed.area_shape(entry)  # raises if it isn't convex
    for entry in LOCAL["feature_shapes"]:
        terrain_seed.feature_shape(entry)  # raises on an unknown kind


@pytest.mark.skipif(not LOCAL["deployments"], reason="no local deployments data")
@pytest.mark.parametrize("entry", LOCAL["deployments"], ids=lambda e: e["name"])
def test_local_deployment_zones_are_on_the_board(entry):
    found = terrain_seed.deployment(entry)  # raises on too few corners
    for side in ("attacker", "defender"):
        for x, y in found.zone(side):
            assert 0 <= x <= 60 and 0 <= y <= 44, (entry["name"], side, x, y)


@pytest.mark.skipif(not LOCAL["layouts"], reason="no local terrain layouts data")
@pytest.mark.parametrize("entry", LOCAL["layouts"], ids=lambda e: e["name"])
def test_local_layouts_objectives(entry):
    # Every objective is terrain areas of the layout; each side has a home.
    from app.models.terrain import OBJECTIVE_KINDS

    kinds = [o["kind"] for o in entry.get("objectives", [])]
    assert set(kinds) <= set(OBJECTIVE_KINDS)
    if kinds:
        assert "attacker_home" in kinds and "defender_home" in kinds
    for objective in entry.get("objectives", []):
        assert objective["areas"]
        assert all(0 <= i < len(entry["areas"]) for i in objective["areas"])


@pytest.mark.skipif(not LOCAL["layouts"], reason="no local terrain layouts data")
def test_local_layouts_name_known_deployments():
    names = {e["name"] for e in LOCAL["deployments"]}
    for entry in LOCAL["layouts"]:
        if entry.get("deployment"):
            assert entry["deployment"] in names, entry["name"]


@pytest.mark.skipif(not LOCAL["layouts"], reason="no local terrain layouts data")
@pytest.mark.parametrize("entry", LOCAL["layouts"], ids=lambda e: e["name"])
def test_local_layouts_place_the_kit_on_the_board(entry):
    from collections import Counter

    from app.services.in_game.terrain import feature_polygons

    area_shapes = {e["name"]: terrain_seed.area_shape(e) for e in LOCAL["area_shapes"]}
    feature_shapes = {e["name"]: terrain_seed.feature_shape(e) for e in LOCAL["feature_shapes"]}
    # Only shapes from the kit, each at most as many times as it has.
    for placed, shapes in ((entry["areas"], area_shapes), (entry["features"], feature_shapes)):
        for name, used in Counter(p["shape"] for p in placed).items():
            assert used <= shapes[name].count, (entry["name"], name, used)
    polygons = [
        area_polygon(
            TerrainArea(shape=area_shapes[a["shape"]], x=a["x"], y=a["y"],
                        rotation=a.get("rotation", 0), mirrored=a.get("mirrored", False))
        )
        for a in entry["areas"]
    ]
    for f in entry["features"]:
        polygons += feature_polygons(
            TerrainFeature(shape=feature_shapes[f["shape"]], x=f["x"], y=f["y"],
                           rotation=f.get("rotation", 0), mirrored=f.get("mirrored", False))
        )
    for polygon in polygons:
        for x, y in polygon:
            assert -0.1 <= x <= 60.1 and -0.1 <= y <= 44.1, (entry["name"], x, y)
