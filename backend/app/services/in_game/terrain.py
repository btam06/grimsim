from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TerrainArea, TerrainFeature, TerrainLayout

# Where a model's base is relative to the battlefield's terrain: whether it's
# within (any part of it over) or wholly within (all of it over) a terrain area
# or terrain feature. Positions are in inches on the board (see
# app/models/terrain.py); bases are sized in mm, as on the datasheet - round,
# oval, or a box (a model with no base whose hull is measured as a
# rectangle, e.g. a Skorpius's 155 x 90mm).

MM_PER_INCH = 25.4
# Touching counts as within: allow for floating-point error at the edge.
EPSILON = 1e-9

Point = tuple[float, float]


@dataclass(frozen=True)
class Base:
    # A model's base, centred on (x, y) inches: round (width_mm == height_mm)
    # or oval - or a rectangle, if `box` - its width along the direction it
    # faces, turned `rotation` degrees clockwise.
    x: float
    y: float
    width_mm: float
    height_mm: float
    rotation: float = 0
    box: bool = False

    @property
    def semi_axes(self) -> tuple[float, float]:
        # Half its width and height, in inches.
        return self.width_mm / 2 / MM_PER_INCH, self.height_mm / 2 / MM_PER_INCH


_ROUND = re.compile(r"^(\d+(?:\.\d+)?)mm$")
_OVAL = re.compile(r"^(\d+(?:\.\d+)?) x (\d+(?:\.\d+)?)mm$")
_BOX = re.compile(r"^(\d+(?:\.\d+)?) x (\d+(?:\.\d+)?)mm box$")


def base_dimensions(base_size: str) -> tuple[float, float] | None:
    # A base size's (width, height) in mm, from its name (see
    # app/seeds/base_sizes.py): "32mm" is round, "105 x 70mm" oval. None for
    # one without measurements (e.g. "Use model", "Small flying base").
    if match := _ROUND.match(base_size):
        diameter = float(match[1])
        return diameter, diameter
    if match := _OVAL.match(base_size) or _BOX.match(base_size):
        return float(match[1]), float(match[2])
    return None


def is_box(base_size: str) -> bool:
    # Whether a base size is a box - a rectangle, e.g. "155 x 90mm box".
    return bool(_BOX.match(base_size))


def base_corners(base: Base) -> list[Point]:
    # A box base's corners, in order round it.
    return rectangle(
        base.x, base.y, base.width_mm / MM_PER_INCH, base.height_mm / MM_PER_INCH, base.rotation
    )


def convex_overlap(first: list[Point], second: list[Point], touching: bool) -> bool:
    # Whether two convex polygons overlap - or, if `touching`, touch - by the
    # separating axis test: they don't if, along the normal of some edge of
    # either, their shadows are apart.
    for polygon in (first, second):
        for p, q in zip(polygon, polygon[1:] + polygon[:1]):
            nx, ny = q[1] - p[1], p[0] - q[0]
            length = math.hypot(nx, ny)
            if length == 0:
                continue
            nx, ny = nx / length, ny / length
            a = [x * nx + y * ny for x, y in first]
            b = [x * nx + y * ny for x, y in second]
            gap = max(min(b) - max(a), min(a) - max(b))
            if gap > EPSILON if touching else gap > -EPSILON:
                return False
    return True


def _inside_convex(point: Point, polygon: list[Point]) -> bool:
    # Whether a point is inside a convex polygon (or on an edge).
    return _contains_origin([(x - point[0], y - point[1]) for x, y in polygon])


def _rotate(x: float, y: float, degrees: float) -> Point:
    # Turns a point about the origin, clockwise on screen (y points down).
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    return x * cos - y * sin, x * sin + y * cos


def rectangle(x: float, y: float, width: float, height: float, rotation: float) -> list[Point]:
    # The corners of a rectangle centred on (x, y), turned about its centre.
    corners = [
        (-width / 2, -height / 2),
        (width / 2, -height / 2),
        (width / 2, height / 2),
        (-width / 2, height / 2),
    ]
    return [(x + dx, y + dy) for dx, dy in (_rotate(cx, cy, rotation) for cx, cy in corners)]


def area_shape_points(area: TerrainArea) -> list[Point]:
    # Its kit shape's corners relative to its position, before it's turned:
    # the shape's polygon, or its rectangle centred there - flipped if it's
    # mirrored (x negated, kept in order around it).
    shape = area.shape
    if shape.points:
        points = [(p.x, p.y) for p in shape.points]
    else:
        w, h = shape.width / 2, shape.height / 2
        points = [(-w, -h), (w, -h), (w, h), (-w, h)]
    if area.mirrored:
        points = [(-x, y) for x, y in reversed(points)]
    return points


def area_polygon(area: TerrainArea) -> list[Point]:
    # Its corners on the board: its shape's, turned and placed.
    return [
        (area.x + dx, area.y + dy)
        for dx, dy in (_rotate(x, y, area.rotation) for x, y in area_shape_points(area))
    ]


def is_convex(points: list[Point]) -> bool:
    # Whether a polygon's corners, in order, make a convex shape (at least 3,
    # turning the same way at every corner).
    if len(points) < 3:
        return False
    signs = set()
    for a, b, c in zip(points, points[1:] + points[:1], points[2:] + points[:2]):
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) > EPSILON:
            signs.add(cross > 0)
    return len(signs) == 1


def feature_shape_parts(feature: TerrainFeature) -> list[tuple[float, float, float, float]]:
    # Its kit shape's parts as (x, y, width, height) relative to its position,
    # before it's turned - flipped if it's mirrored (x negated).
    parts = [(p.x, p.y, p.width, p.height) for p in feature.shape.parts]
    if feature.mirrored:
        parts = [(-(x + w), y, w, h) for x, y, w, h in parts]
    return parts


def feature_polygons(feature: TerrainFeature) -> list[list[Point]]:
    # Each of a feature's parts on the board: its corners relative to the
    # feature's position, turned with the feature about that point.
    polygons = []
    for px, py, pw, ph in feature_shape_parts(feature):
        corners = [(px, py), (px + pw, py), (px + pw, py + ph), (px, py + ph)]
        polygons.append(
            [
                (feature.x + dx, feature.y + dy)
                for dx, dy in (_rotate(cx, cy, feature.rotation) for cx, cy in corners)
            ]
        )
    return polygons


def _to_unit_circle(point: Point, base: Base) -> Point:
    # A point in the space where the base is a circle of radius 1 at the
    # origin: moved to its centre, turned back by its rotation, and scaled by
    # its semi-axes.
    a, b = base.semi_axes
    x, y = _rotate(point[0] - base.x, point[1] - base.y, -base.rotation)
    return x / a, y / b


def _distance_to_segment(p: Point, q: Point) -> float:
    # The distance from the origin to the segment pq.
    dx, dy = q[0] - p[0], q[1] - p[1]
    length_squared = dx * dx + dy * dy
    t = 0.0 if length_squared == 0 else max(0.0, min(1.0, -(p[0] * dx + p[1] * dy) / length_squared))
    return math.hypot(p[0] + t * dx, p[1] + t * dy)


def _contains_origin(polygon: list[Point]) -> bool:
    # Whether a convex polygon contains the origin (or has it on an edge).
    signs = set()
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        cross = p[0] * q[1] - p[1] * q[0]
        if abs(cross) > EPSILON:
            signs.add(cross > 0)
    return len(signs) <= 1


def within(base: Base, polygon: list[Point]) -> bool:
    # Whether any part of the base is over a convex polygon (touching counts).
    # Scaled so the base is a unit circle, the polygon stays convex: the base
    # reaches it if the circle's centre is inside it or within 1 of an edge.
    if base.box:
        return convex_overlap(base_corners(base), polygon, touching=True)
    shape = [_to_unit_circle(p, base) for p in polygon]
    if _contains_origin(shape):
        return True
    return any(
        _distance_to_segment(p, q) <= 1 + EPSILON for p, q in zip(shape, shape[1:] + shape[:1])
    )


def wholly_within(base: Base, polygon: list[Point]) -> bool:
    # Whether all of the base is over a convex polygon: for every edge, the
    # base's furthest point in the direction out through that edge (its
    # support) mustn't pass it. (A box: all its corners inside.)
    if base.box:
        return all(_inside_convex(c, polygon) for c in base_corners(base))
    a, b = base.semi_axes
    u = _rotate(1, 0, base.rotation)  # the base's width axis
    v = _rotate(0, 1, base.rotation)  # its height axis
    # Which way round the corners go decides which side of an edge is out: a
    # positive signed area means anticlockwise (taking y as up), whose
    # outward normals are on each edge's right.
    area2 = sum(p[0] * q[1] - p[1] * q[0] for p, q in zip(polygon, polygon[1:] + polygon[:1]))
    anticlockwise = area2 > 0
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        ex, ey = q[0] - p[0], q[1] - p[1]
        length = math.hypot(ex, ey)
        if length == 0:
            continue
        # The edge's outward normal.
        nx, ny = (ey / length, -ex / length) if anticlockwise else (-ey / length, ex / length)
        support = (
            base.x * nx
            + base.y * ny
            + math.hypot(a * (u[0] * nx + u[1] * ny), b * (v[0] * nx + v[1] * ny))
        )
        if support > p[0] * nx + p[1] * ny + EPSILON:
            return False
    return True


@dataclass
class TerrainPosition:
    # Where a base is relative to one terrain area or feature.
    id: int
    within: bool
    wholly_within: bool


def base_terrain(
    layout: TerrainLayout, base: Base
) -> tuple[list[TerrainPosition], list[TerrainPosition]]:
    # Where a base is relative to each of a layout's terrain areas and terrain
    # features, as (areas, features). A feature counts as within if any of its
    # parts is, and as wholly within if all of the base is over one part (a
    # base too big for any one part - e.g. straddling an L's corner - isn't).
    areas = [
        TerrainPosition(
            id=area.id,
            within=within(base, polygon := area_polygon(area)),
            wholly_within=wholly_within(base, polygon),
        )
        for area in layout.areas
    ]
    features = []
    for feature in layout.features:
        polygons = feature_polygons(feature)
        features.append(
            TerrainPosition(
                id=feature.id,
                within=any(within(base, polygon) for polygon in polygons),
                wholly_within=any(wholly_within(base, polygon) for polygon in polygons),
            )
        )
    return areas, features


async def pick_layout(
    session: AsyncSession, attacker_disposition_id: int | None, defender_disposition_id: int | None
) -> TerrainLayout | None:
    # A terrain layout for the attacker's and defender's dispositions, at
    # random if there are several; None if neither has one or none fits.
    if attacker_disposition_id is None or defender_disposition_id is None:
        return None
    layouts = list(
        (
            await session.execute(
                select(TerrainLayout).where(
                    TerrainLayout.attacker_disposition_id == attacker_disposition_id,
                    TerrainLayout.defender_disposition_id == defender_disposition_id,
                )
            )
        ).scalars()
    )
    return random.choice(layouts) if layouts else None
