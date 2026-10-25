from __future__ import annotations

import heapq
import math

from app.models import Game, Unit
from app.services.in_game import deployment
from app.services.in_game.deployment import TOLERANCE, Base, Point

# How far a model moves: the shortest way its base can go from where it
# started to where it ends. INFANTRY, BEAST and SWARM units move through any
# terrain, and anything moves through light terrain (obstacles) - a straight
# line. Everything else has to go round dense terrain (ruin walls): its route
# is the shortest one that keeps its base off them, found on the walls'
# corners (a visibility graph), each wall grown by the base's half-width.
#
# An oval base is kept off walls by half its narrow side (it can turn to slip
# through a gap). A wall a base already touches where it starts or ends
# doesn't count - a model standing against one can still move away from it.

THROUGH_ANY_TERRAIN = {"INFANTRY", "BEAST", "SWARM"}
# Abilities that let a unit move through terrain (and roll for it - see
# app/services/in_game/movement.py).
SUPER_HEAVY_WALKER = "Super-heavy Walker"
# Round each grown wall corner: this many segments, each just outside the
# true rounded corner (so a route never clips it).
CORNER_SEGMENTS = 2


def moves_through_terrain(unit: Unit) -> bool:
    # Whether the unit moves through any terrain (INFANTRY, BEAST, SWARM, or
    # a Super-heavy Walker).
    return is_super_heavy_walker(unit) or any(
        k.name in THROUGH_ANY_TERRAIN for m in unit.unit_models for k in m.model.keywords
    )


def is_super_heavy_walker(unit: Unit) -> bool:
    return any(
        a.name == SUPER_HEAVY_WALKER for m in unit.unit_models for a in m.model.faction_abilities
    )


def blocking_terrain(game: Game, unit: Unit) -> list[list[Point]]:
    # What the unit has to go round: nothing, or dense terrain (each part of
    # each ruin wall).
    # (Imported here: shooting imports movement, which uses this module.)
    from app.services.in_game.shooting import dense_terrain

    return [] if moves_through_terrain(unit) else dense_terrain(game)


def clearance(base: Base) -> float:
    # How far its centre has to keep from a wall: half its narrow side.
    return min(base.semi_axes)


def _grow(polygon: list[Point], by: float) -> list[Point]:
    # A convex polygon grown outward by `by`, its corners rounded (as a few
    # short segments just outside the true round corner).
    area2 = sum(p[0] * q[1] - p[1] * q[0] for p, q in zip(polygon, polygon[1:] + polygon[:1]))
    sign = 1 if area2 > 0 else -1
    n = len(polygon)
    grown = []
    for i, corner in enumerate(polygon):
        before, after = polygon[i - 1], polygon[(i + 1) % n]
        # Outward normals of the edges meeting here.
        normals = []
        for p, q in ((before, corner), (corner, after)):
            ex, ey = q[0] - p[0], q[1] - p[1]
            length = math.hypot(ex, ey) or 1
            normals.append((sign * ey / length, -sign * ex / length))
        start = math.atan2(normals[0][1], normals[0][0])
        end = math.atan2(normals[1][1], normals[1][0])
        sweep = math.remainder(end - start, 2 * math.pi)
        radius = by / math.cos(abs(sweep) / (2 * CORNER_SEGMENTS)) if sweep else by
        for k in range(CORNER_SEGMENTS + 1):
            angle = start + sweep * k / CORNER_SEGMENTS
            grown.append(
                (corner[0] + radius * math.cos(angle), corner[1] + radius * math.sin(angle))
            )
    return grown


def _contains(point: Point, polygon: list[Point]) -> bool:
    return deployment._contains(point, polygon)


def _box(polygon: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


class Obstacles:
    # The walls a base of one size has to go round, grown by its clearance,
    # near enough to matter (within `reach` of `around`).
    def __init__(self, walls: list[list[Point]], by: float, around: list[Point], reach: float):
        near = []
        for wall in walls:
            x0, y0, x1, y1 = _box(wall)
            if any(
                x0 - reach <= px <= x1 + reach and y0 - reach <= py <= y1 + reach
                for px, py in around
            ):
                near.append(_grow(wall, by))
        self.polygons = near
        self.boxes = [_box(p) for p in near]
        # Route corners: every grown corner that isn't inside another wall or
        # off the battlefield.
        self.corners = [
            c
            for i, polygon in enumerate(near)
            for c in polygon
            if 0 <= c[0] <= 60 and 0 <= c[1] <= 44
            and not any(_contains(c, other) for j, other in enumerate(near) if j != i)
        ]

    def clear(self, a: Point, b: Point, ignore: set[int]) -> bool:
        # Whether a straight line from a to b keeps off every wall (but those
        # in `ignore`).
        from app.services.in_game.shooting import _blocks

        lx, ly, hx, hy = min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])
        for i, (polygon, (x0, y0, x1, y1)) in enumerate(zip(self.polygons, self.boxes)):
            if i in ignore or x1 < lx or x0 > hx or y1 < ly or y0 > hy:
                continue
            if _blocks(a, b, polygon):
                return False
        return True

    def route(self, a: Point, b: Point, cap: float) -> float | None:
        # The length of the shortest route from a to b round the walls, or None
        # if there's none of at most `cap`.
        found = self.way(a, b, cap)
        return found[0] if found else None

    def _ignore(self, *points: Point) -> set[int]:
        # The walls a base at any of `points` already touches: they don't
        # block it (it can move away from them).
        return {i for i, p in enumerate(self.polygons) if any(_contains(q, p) for q in points)}

    def way(self, a: Point, b: Point, cap: float) -> tuple[float, list[Point]] | None:
        # The shortest route from a to b round the walls - its length, and the
        # points it goes through (a, any corners, b) - or None if there's none
        # of at most `cap` (A* over the corners).
        ignore = self._ignore(a, b)
        straight = math.dist(a, b)
        if self.clear(a, b, ignore):
            return straight, [a, b]
        if straight > cap:
            return None
        nodes = [a, *self.corners, b]
        goal = len(nodes) - 1
        best = {0: 0.0}
        came_from: dict[int, int] = {}
        queue = [(straight, 0.0, 0)]
        while queue:
            _, so_far, here = heapq.heappop(queue)
            if here == goal:
                points = [nodes[goal]]
                while here in came_from:
                    here = came_from[here]
                    points.append(nodes[here])
                return so_far, points[::-1]
            if so_far > best.get(here, math.inf) + TOLERANCE:
                continue
            for there in range(1, len(nodes)):
                if there == here:
                    continue
                step = math.dist(nodes[here], nodes[there])
                total = so_far + step
                if total + math.dist(nodes[there], b) > cap + TOLERANCE:
                    continue
                if total >= best.get(there, math.inf) - TOLERANCE:
                    continue
                if not self.clear(nodes[here], nodes[there], ignore):
                    continue
                best[there] = total
                came_from[there] = here
                heapq.heappush(queue, (total + math.dist(nodes[there], b), total, there))
        return None

    def reach(self, a: Point, distance: float, rays: int) -> list[list[Point]]:
        # Where a base's centre at `a` can get within `distance`, going round
        # the walls: from `a`, and from each corner it can get to with some of
        # the distance left, the ground it can see within what's left (rays
        # stopped by the walls) - together, the area it can reach.
        ignore = self._ignore(a)
        nodes = [a, *self.corners]
        best = {0: 0.0}
        queue = [(0.0, 0)]
        settled = []
        while queue:
            so_far, here = heapq.heappop(queue)
            if so_far > best.get(here, math.inf) + TOLERANCE:
                continue
            settled.append((here, so_far))
            for there in range(1, len(nodes)):
                total = so_far + math.dist(nodes[here], nodes[there])
                if there == here or total >= min(distance, best.get(there, math.inf)):
                    continue
                if not self.clear(nodes[here], nodes[there], ignore):
                    continue
                best[there] = total
                heapq.heappush(queue, (total, there))
        return [
            self._visible(nodes[here], distance - so_far, rays, ignore)
            for here, so_far in settled
            if distance - so_far > 0.05
        ]

    def _visible(self, origin: Point, radius: float, rays: int, ignore: set[int]) -> list[Point]:
        # How far a straight line gets from `origin` in each direction, up to
        # `radius`, before a wall: a star-shaped polygon.
        from app.services.in_game.shooting import _clip

        points = []
        for i in range(rays):
            angle = 2 * math.pi * i / rays
            end = (origin[0] + radius * math.cos(angle), origin[1] + radius * math.sin(angle))
            stop = 1.0
            lx, ly = min(origin[0], end[0]), min(origin[1], end[1])
            hx, hy = max(origin[0], end[0]), max(origin[1], end[1])
            for j, (polygon, (x0, y0, x1, y1)) in enumerate(zip(self.polygons, self.boxes)):
                if j in ignore or x1 < lx or x0 > hx or y1 < ly or y0 > hy:
                    continue
                inside = _clip(origin, end, polygon)
                if inside is not None:
                    stop = min(stop, inside[0])
            points.append(
                (origin[0] + (end[0] - origin[0]) * stop, origin[1] + (end[1] - origin[1]) * stop)
            )
        return points


class Pather:
    # Works out how far a unit's models move, going round what they have to:
    # one set of grown walls per base size, built the first time it's needed.
    # It remembers the way each move went (`ways`, by start and end).
    def __init__(self, game: Game, unit: Unit, around: list[Point], reach: float):
        self.walls = blocking_terrain(game, unit)
        self.around = around
        self.reach_limit = reach
        self._obstacles: dict[float, Obstacles] = {}
        self.ways: dict[tuple[Point, Point], list[Point]] = {}

    def obstacles(self, base: Base) -> Obstacles:
        by = round(clearance(base), 4)
        if by not in self._obstacles:
            self._obstacles[by] = Obstacles(self.walls, by, self.around, self.reach_limit + by)
        return self._obstacles[by]

    def distance(self, start: Base, end: Base, cap: float) -> float | None:
        # How far the base moves from start to end: a straight line if nothing
        # is in the way, otherwise round it - None if that's more than `cap`.
        a, b = (start.x, start.y), (end.x, end.y)
        if not self.walls:
            self.ways[(a, b)] = [a, b]
            return math.dist(a, b)
        found = self.obstacles(start).way(a, b, cap)
        if found is None:
            return None
        self.ways[(a, b)] = found[1]
        return found[0]

    def way(self, start: Base, end: Base) -> list[Point] | None:
        # The way it went from start to end, if worked out (see distance).
        return self.ways.get(((start.x, start.y), (end.x, end.y)))

    def bends(self, starts: dict[int, Base], ends: dict[int, Base]) -> dict[int, list[Point]]:
        # Each model's way from its start to its end where it isn't straight
        # (it goes round a wall), by unit model id.
        found = {}
        for i, end in ends.items():
            if i in starts and (way := self.way(starts[i], end)) and len(way) > 2:
                found[i] = way
        return found

    def reach(self, start: Base, distance: float, rays: int = 72) -> list[list[Point]]:
        # Where the base's centre can get within `distance` of `start`, going
        # round what it has to: a list of polygons, together the area.
        a = (start.x, start.y)
        if not self.walls:
            return [
                [
                    (a[0] + distance * math.cos(2 * math.pi * i / rays),
                     a[1] + distance * math.sin(2 * math.pi * i / rays))
                    for i in range(rays)
                ]
            ]
        return self.obstacles(start).reach(a, distance, rays)


def for_unit(game: Game, unit: Unit, starts: dict[int, Base], reach: float) -> Pather:
    # A Pather for the unit's models setting off from `starts`, moving up to
    # `reach`.
    return Pather(game, unit, [(b.x, b.y) for b in starts.values()], reach)


def too_far(pather: Pather, start: Base, end: Base, limit: float) -> str | None:
    # What's wrong if a model can't get from start to end within `limit`
    # (going round what it has to) - None if it can.
    straight = math.dist((start.x, start.y), (end.x, end.y))
    moved = pather.distance(start, end, cap=2 * limit + 1)
    if moved is None:
        return f'can\'t get there within {limit:g}" going round dense terrain'
    if moved <= limit + TOLERANCE:
        return None
    going_round = " going round dense terrain" if moved > straight + 0.01 else ""
    return f'would move {moved:.1f}"{going_round} (it can move {limit:g}")'
