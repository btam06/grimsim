from __future__ import annotations

import math

from app.models import Game, Unit
from app.services.in_game import deployment
from app.services.in_game.deployment import BOARD, TOLERANCE, Base, Point

# The battlefield's regions, for missions: each player's deployment zone and
# territory, and No Man's Land - and whether a unit is within one, or wholly
# within it.
#
# - A player's territory is the half of the battlefield nearer their
#   deployment zone: the battlefield is halved by the line between the two
#   zones - across the centre, if they're at the top and bottom; down it, if
#   they're at the sides; or, if they're in opposite table quarters (Search
#   and Destroy), corner to corner through the two corners neither zone is
#   in.
# - No Man's Land is the battlefield outside both deployment zones.
# - A unit is within a region if any of its models is (any part of its base
#   over it, touching counts); wholly within it if every model's base is
#   wholly over it.

WIDTH, HEIGHT = BOARD[2]


def _zones(game: Game) -> dict[str, list[Point]] | None:
    layout = game.layout
    if layout is None or layout.deployment is None:
        return None
    return {side: layout.deployment.zone(side) for side in ("attacker", "defender")}


def side(game: Game, seat: int) -> str:
    return "attacker" if seat == game.attacker_seat else "defender"


def deployment_zone(game: Game, seat: int) -> list[Point] | None:
    zones = _zones(game)
    return zones[side(game, seat)] if zones else None


def _middle(polygon: list[Point]) -> Point:
    return (
        sum(p[0] for p in polygon) / len(polygon),
        sum(p[1] for p in polygon) / len(polygon),
    )


CORNERS = [(0.0, 0.0), (WIDTH, 0.0), (WIDTH, HEIGHT), (0.0, HEIGHT)]


def _in_a_zone(point: Point, zones: dict[str, list[Point]]) -> bool:
    # Inside a zone, or on its edge.
    return any(
        deployment._contains(point, zone)
        or any(
            deployment._segment_distance(point, p, q) <= TOLERANCE
            for p, q in deployment._edges(zone)
        )
        for zone in zones.values()
    )


def split(game: Game) -> str | None:
    # Which line halves the battlefield into territories: "vertical" (x = 30:
    # zones at the sides), "horizontal" (y = 22: zones at the top and
    # bottom), or - for zones in opposite table quarters - "diagonal": from
    # corner to corner through the two corners neither zone is in.
    zones = _zones(game)
    if zones is None:
        return None
    if not any(_in_a_zone(c, zones) for c in (CORNERS[0], CORNERS[2])) or not any(
        _in_a_zone(c, zones) for c in (CORNERS[1], CORNERS[3])
    ):
        return "diagonal"
    (ax, ay), (dx, dy) = _middle(zones["attacker"]), _middle(zones["defender"])
    return "vertical" if abs(ax - dx) >= abs(ay - dy) else "horizontal"


def split_line(game: Game) -> tuple[Point, Point] | None:
    # The line between the territories, end to end.
    kind = split(game)
    if kind == "vertical":
        return (WIDTH / 2, 0.0), (WIDTH / 2, HEIGHT)
    if kind == "horizontal":
        return (0.0, HEIGHT / 2), (WIDTH, HEIGHT / 2)
    if kind == "diagonal":
        zones = _zones(game)
        free = [c for c in CORNERS if not _in_a_zone(c, zones)]
        return free[0], free[1]
    return None


def _side_of(line: tuple[Point, Point], point: Point) -> float:
    (x0, y0), (x1, y1) = line
    return (x1 - x0) * (point[1] - y0) - (y1 - y0) * (point[0] - x0)


def territory(game: Game, seat: int) -> list[Point] | None:
    # The player's half of the battlefield: the side of the split line their
    # deployment zone's middle is on - the corners on that side, and the
    # line's ends.
    zones = _zones(game)
    line = split_line(game)
    if zones is None or line is None:
        return None
    middle = _middle(zones[side(game, seat)])
    sign = _side_of(line, middle) > 0
    points = list(line) + [
        c for c in CORNERS if c not in line and (_side_of(line, c) > 0) == sign
    ]
    # In order around it (each half is convex).
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return sorted(points, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))


# --- a base, and a unit, within a region ---


def base_within(base: Base, polygon: list[Point]) -> bool:
    # Whether any part of the base is over the polygon (convex or not).
    return deployment.distance_to_polygon(base, polygon) <= TOLERANCE


def base_wholly_within(base: Base, polygon: list[Point]) -> bool:
    return deployment.wholly_inside(base, polygon)


def base_within_no_mans_land(game: Game, base: Base) -> bool:
    # Whether any part of the base is outside both deployment zones (and on
    # the battlefield).
    zones = _zones(game)
    if zones is None:
        return False
    return base_within(base, BOARD) and not any(
        base_wholly_within(base, zone) for zone in zones.values()
    )


def base_wholly_within_no_mans_land(game: Game, base: Base) -> bool:
    # Whether all of the base is outside both deployment zones (touching one
    # counts as within it) and on the battlefield.
    zones = _zones(game)
    if zones is None:
        return False
    return base_wholly_within(base, BOARD) and not any(
        base_within(base, zone) for zone in zones.values()
    )


def _bases(game: Game, unit: Unit) -> list[Base]:
    placed = deployment.positions(game)
    return [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in deployment.models_on_battlefield(game, unit)
    ]


def unit_within(game: Game, unit: Unit, polygon: list[Point]) -> bool:
    # Whether any of the unit's models is within the polygon.
    return any(base_within(b, polygon) for b in _bases(game, unit))


def unit_wholly_within(game: Game, unit: Unit, polygon: list[Point]) -> bool:
    # Whether every one of the unit's models (on the battlefield) is wholly
    # within the polygon.
    bases = _bases(game, unit)
    return bool(bases) and all(base_wholly_within(b, polygon) for b in bases)


def unit_within_no_mans_land(game: Game, unit: Unit) -> bool:
    return any(base_within_no_mans_land(game, b) for b in _bases(game, unit))


def unit_wholly_within_no_mans_land(game: Game, unit: Unit) -> bool:
    bases = _bases(game, unit)
    return bool(bases) and all(base_wholly_within_no_mans_land(game, b) for b in bases)


# --- the centre, table quarters and battlefield edges ---

CENTRE: Point = (WIDTH / 2, HEIGHT / 2)
QUARTERS: list[list[Point]] = [
    [(x0, y0), (x0 + WIDTH / 2, y0), (x0 + WIDTH / 2, y0 + HEIGHT / 2), (x0, y0 + HEIGHT / 2)]
    for y0 in (0.0, HEIGHT / 2)
    for x0 in (0.0, WIDTH / 2)
]
# Each battlefield edge, and the one opposite it.
EDGES = ("left", "right", "top", "bottom")
OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


def base_distance_to_point(base: Base, point: Point) -> float:
    # How far the nearest part of the base is from a point (0 if it's over
    # it).
    if deployment._inside_base(point, base):
        return 0.0
    return min(math.dist(p, point) for p in deployment.outline(base))


def unit_within_distance_of_point(game: Game, unit: Unit, point: Point, distance: float) -> bool:
    # Whether any of the unit's models is within `distance` of the point.
    return any(
        base_distance_to_point(b, point) <= distance + TOLERANCE for b in _bases(game, unit)
    )


def _base_edge_distance(base: Base, edge: str) -> float:
    points = deployment.outline(base)
    if edge == "left":
        return min(p[0] for p in points)
    if edge == "right":
        return WIDTH - max(p[0] for p in points)
    if edge == "top":
        return min(p[1] for p in points)
    return HEIGHT - max(p[1] for p in points)


def unit_edges_within(game: Game, unit: Unit, distance: float) -> set[str]:
    # The battlefield edges one of the unit's models is within `distance` of.
    return {
        edge
        for edge in EDGES
        for b in _bases(game, unit)
        if _base_edge_distance(b, edge) <= distance + TOLERANCE
    }


def unit_quarter(game: Game, unit: Unit) -> int | None:
    # The table quarter the unit is wholly within, if any (0-3).
    return next(
        (i for i, quarter in enumerate(QUARTERS) if unit_wholly_within(game, unit, quarter)),
        None,
    )


def point_in(point: Point, polygon: list[Point] | None) -> bool:
    return polygon is not None and deployment._contains(point, polygon)


def point_in_no_mans_land(game: Game, point: Point) -> bool:
    zones = _zones(game)
    return zones is not None and not any(point_in(point, z) for z in zones.values())
