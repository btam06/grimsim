from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from fastapi import HTTPException

from app.models import Game, GameModelPosition, GamePlayer, Unit, UnitModel
from app.services.in_game.terrain import (
    MM_PER_INCH,
    Base,
    Point,
    _contains_origin,
    _distance_to_segment,
    _rotate,
    _to_unit_circle,
    base_dimensions,
    feature_polygons,
    wholly_within,
)

# Deploying the armies, before the first battle round. The attacker sets up a
# unit first, then the players take turns; once one has none left, the other
# sets up the rest of theirs. Each unit is set up wholly within its owner's
# deployment zone - or, if every model in it has Infiltrators, anywhere more
# than 9" from the enemy's zone and from every enemy model. Its models mustn't
# overlap any other model, and must be in coherency: each within 9" of every
# other model in the unit, and within 2" of at least one other - nor any
# terrain feature (ruin walls and obstacles; terrain
# areas are fine).
#
# Distances between models are between the nearest points of their bases.
# Positions are in inches on the board (see app/models/terrain.py).

BOARD = [(0.0, 0.0), (60.0, 0.0), (60.0, 44.0), (0.0, 44.0)]
COHERENCY_RANGE = 2.0
UNIT_SPAN = 9.0
INFILTRATORS_RANGE = 9.0
INFILTRATORS = "Infiltrators"
# Positions come from dragging on screen: allow a hair either way at a limit.
TOLERANCE = 1e-6
# Bases without measurements: flying bases are their usual ovals; anything
# else (e.g. "Use model") is shown and checked as a 32mm base.
FLYING_BASES_MM = {"Small flying base": (60.0, 35.0), "Large flying base": (120.0, 92.0)}
PLACEHOLDER_BASE_MM = (32.0, 32.0)
# An oval base is checked as this many points around its edge.
OUTLINE_POINTS = 48
# A new unit's formation: models in rows, this far apart.
FORMATION_GAP = 0.5
# How far (and in what steps) a model in a new formation is moved to stop it
# overlapping another.
NUDGE_STEP = 0.25
NUDGE_LIMIT = 12.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


# --- the armies ---


def base_mm(unit_model: UnitModel) -> tuple[float, float, bool]:
    # A model's base as (width, height) in mm, and whether that's measured
    # (not a placeholder).
    base_size = unit_model.model.base_size
    if base_size is not None:
        if dimensions := base_dimensions(base_size.name):
            return *dimensions, True
        if base_size.name in FLYING_BASES_MM:
            return *FLYING_BASES_MM[base_size.name], True
    return *PLACEHOLDER_BASE_MM, False


def base_at(unit_model: UnitModel, x: float, y: float, rotation: float = 0) -> Base:
    width, height, _ = base_mm(unit_model)
    return Base(x=x, y=y, width_mm=width, height_mm=height, rotation=rotation)


def deployable_units(player: GamePlayer) -> list[Unit]:
    # The player's list's units that have models, in list order.
    return sorted((u for u in player.army_list.units if u.unit_models), key=lambda u: u.id)


def unit_models(unit: Unit) -> list[UnitModel]:
    return sorted(unit.unit_models, key=lambda m: m.id)


def is_infiltrator(unit: Unit) -> bool:
    # Every model in it has Infiltrators.
    return all(
        any(a.name == INFILTRATORS for a in m.model.abilities) for m in unit.unit_models
    )


def positions(game: Game) -> dict[int, GameModelPosition]:
    # Each deployed model's position, by unit model id.
    return {p.unit_model_id: p for p in game.model_positions}


def is_deployed(unit: Unit, placed: dict[int, GameModelPosition]) -> bool:
    # Whether it's on the battlefield: a unit's set up all at once, and its
    # destroyed models are taken off (see app/services/in_game/casualties.py) - so
    # while any of its models are there, it is.
    return any(m.id in placed for m in unit.unit_models)


def models_on_battlefield(game: Game, unit: Unit) -> list[UnitModel]:
    # The unit's models still on the battlefield (not destroyed).
    placed = positions(game)
    return [m for m in unit_models(unit) if m.id in placed]


def _attacker(game: Game) -> GamePlayer:
    return next(p for p in game.players if p.seat == game.attacker_seat)


def _defender(game: Game) -> GamePlayer:
    return next(p for p in game.players if p.seat != game.attacker_seat)


def can_deploy(game: Game) -> bool:
    # Whether the game has deployment zones and anything to set up in them.
    layout = game.layout
    return (
        layout is not None
        and layout.deployment is not None
        and any(deployable_units(p) for p in game.players)
    )


def deploying_seat(game: Game) -> int | None:
    # Whose turn it is to set up a unit: the attacker's first, then turn
    # about by how many each has set up - or whoever has any left. None
    # outside deployment, or once everything is set up.
    if game.status != "deployment":
        return None
    placed = positions(game)
    counts = {}
    for player in (_attacker(game), _defender(game)):
        units = deployable_units(player)
        done = sum(1 for u in units if is_deployed(u, placed))
        counts[player.seat] = (done, len(units) - done)
    attacker, defender = game.attacker_seat, _defender(game).seat
    (attacker_done, attacker_left), (defender_done, defender_left) = (
        counts[attacker],
        counts[defender],
    )
    if not attacker_left and not defender_left:
        return None
    if not defender_left:
        return attacker
    if not attacker_left:
        return defender
    return attacker if attacker_done <= defender_done else defender


def owner(game: Game, unit: Unit) -> GamePlayer:
    # The player whose list the unit is in.
    for player in game.players:
        if any(u.id == unit.id for u in player.army_list.units):
            return player
    raise _bad_request("that unit isn't in either player's list")


def find_unit(game: Game, unit_id: int) -> Unit:
    for player in game.players:
        for unit in deployable_units(player):
            if unit.id == unit_id:
                return unit
    raise HTTPException(status_code=404, detail="unit not found in this game's lists")


def _side(game: Game, player: GamePlayer) -> str:
    return "attacker" if player.seat == game.attacker_seat else "defender"


def _other_side(side: str) -> str:
    return "defender" if side == "attacker" else "attacker"


# --- geometry ---


def _contains(point: Point, polygon: list[Point]) -> bool:
    # Whether a point is inside a polygon (convex or not), by counting the
    # edges a ray from it crosses.
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _segment_distance(point: Point, p: Point, q: Point) -> float:
    # The distance from a point to the segment pq.
    return _distance_to_segment(
        (p[0] - point[0], p[1] - point[1]), (q[0] - point[0], q[1] - point[1])
    )


def _edges(polygon: list[Point]):
    return zip(polygon, polygon[1:] + polygon[:1])


def _is_round(base: Base) -> bool:
    return base.width_mm == base.height_mm


def _radius(base: Base) -> float:
    return base.width_mm / 2 / MM_PER_INCH


def outline(base: Base, points: int = OUTLINE_POINTS) -> list[Point]:
    # Points around the edge of a base.
    a, b = base.semi_axes
    result = []
    for i in range(points):
        angle = 2 * math.pi * i / points
        dx, dy = _rotate(a * math.cos(angle), b * math.sin(angle), base.rotation)
        result.append((base.x + dx, base.y + dy))
    return result


def wholly_inside(base: Base, polygon: list[Point]) -> bool:
    # Whether all of a base is over a polygon, convex or not (touching an edge
    # counts as inside). Scaled so the base is a unit circle (edges stay
    # straight): its centre must be inside, and no edge nearer it than 1.
    shape = [_to_unit_circle(p, base) for p in polygon]
    return _contains((0.0, 0.0), shape) and all(
        _distance_to_segment(p, q) >= 1 - TOLERANCE for p, q in _edges(shape)
    )


def _inside_base(point: Point, base: Base) -> bool:
    # Whether a point is strictly inside a base (not on its edge).
    x, y = _to_unit_circle(point, base)
    return math.hypot(x, y) < 1 - TOLERANCE


def overlaps(first: Base, second: Base) -> bool:
    # Whether two bases overlap (touching doesn't count).
    if _is_round(first) and _is_round(second):
        apart = math.hypot(first.x - second.x, first.y - second.y)
        return apart < _radius(first) + _radius(second) - TOLERANCE
    if _inside_base((second.x, second.y), first) or _inside_base((first.x, first.y), second):
        return True
    return any(_inside_base(p, second) for p in outline(first)) or any(
        _inside_base(p, first) for p in outline(second)
    )


def overlaps_polygon(base: Base, polygon: list[Point]) -> bool:
    # Whether a base overlaps a convex polygon (touching doesn't count).
    # Scaled so the base is a unit circle: its centre is inside, or an edge
    # passes nearer it than 1.
    shape = [_to_unit_circle(p, base) for p in polygon]
    return _contains_origin(shape) or any(
        _distance_to_segment(p, q) < 1 - TOLERANCE for p, q in _edges(shape)
    )


FEATURE_KIND_NAMES = {"ruin_wall": "a ruin wall", "obstacle": "an obstacle"}


def _features(game: Game) -> list[tuple[str, list[Point]]]:
    # Each part of the battlefield's terrain features: what it is, and its
    # corners on the board.
    layout = game.layout
    if layout is None:
        return []
    return [
        (FEATURE_KIND_NAMES.get(feature.shape.kind, "terrain"), polygon)
        for feature in layout.features
        for polygon in feature_polygons(feature)
    ]


def _feature_overlapped(base: Base, features: list[tuple[str, list[Point]]]) -> str | None:
    # What terrain feature the base overlaps, if any.
    return next((kind for kind, polygon in features if overlaps_polygon(base, polygon)), None)


def gap(first: Base, second: Base) -> float:
    # The distance between the nearest points of two bases; 0 if they touch
    # or overlap.
    if _is_round(first) and _is_round(second):
        apart = math.hypot(first.x - second.x, first.y - second.y)
        return max(0.0, apart - _radius(first) - _radius(second))
    if overlaps(first, second):
        return 0.0
    second_outline = outline(second)
    return min(
        _segment_distance(p, q, r) for p in outline(first) for q, r in _edges(second_outline)
    )


def distance_to_polygon(base: Base, polygon: list[Point]) -> float:
    # The distance from a base to the nearest point of a polygon (convex or
    # not); 0 if it touches or is over it.
    if _is_round(base):
        centre = (base.x, base.y)
        if _contains(centre, polygon):
            return 0.0
        nearest = min(_segment_distance(centre, p, q) for p, q in _edges(polygon))
        return max(0.0, nearest - _radius(base))
    shape = [_to_unit_circle(p, base) for p in polygon]
    if _contains((0.0, 0.0), shape) or any(
        _distance_to_segment(p, q) <= 1 + TOLERANCE for p, q in _edges(shape)
    ):
        return 0.0
    return min(_segment_distance(o, p, q) for o in outline(base) for p, q in _edges(polygon))


# --- checking a unit's placement ---


@dataclass
class Placement:
    # Whether a unit could be set up as placed: what's wrong with the unit as
    # a whole, and with each model (by unit model id).
    problems: list[str]
    models: dict[int, list[str]]

    @property
    def valid(self) -> bool:
        return not self.problems


def placed_bases(game: Game, exclude: Unit) -> list[tuple[GamePlayer, UnitModel, Base]]:
    # Every deployed model but those in `exclude`: its owner, and its base.
    placed = positions(game)
    result = []
    for player in game.players:
        for unit in player.army_list.units:
            if unit.id == exclude.id:
                continue
            for unit_model in unit.unit_models:
                if (position := placed.get(unit_model.id)) is not None:
                    base = base_at(unit_model, position.x, position.y, position.rotation)
                    result.append((player, unit_model, base))
    return result


def _models_phrase(count: int) -> str:
    return "1 other model" if count == 1 else f"{count} other models"


def unit_bases(
    unit: Unit,
    placement: dict[int, tuple[float, float, float]],
    models: list[UnitModel] | None = None,
) -> tuple[list[UnitModel], dict[int, Base]]:
    # The unit's models (or just `models` - e.g. those not destroyed), and each
    # one's base at `placement` ((x, y, rotation) by unit model id - every one
    # of them, and only those).
    models = unit_models(unit) if models is None else models
    if set(placement) != {m.id for m in models}:
        raise _bad_request("place every model in the unit (and only those)")
    return models, {m.id: base_at(m, *placement[m.id]) for m in models}


def physical_problems(
    game: Game,
    models: list[UnitModel],
    bases: dict[int, Base],
    others: list[tuple[GamePlayer, UnitModel, Base]],
) -> dict[int, list[str]]:
    # What's wrong with a unit's models where they are, wherever they're being
    # put (set up or moved): off the battlefield, overlapping another model
    # (`others`, or one in the unit) or a terrain feature, or out of
    # coherency. By unit model id.
    features = _features(game)
    problems: dict[int, list[str]] = {m.id: [] for m in models}
    for model in models:
        base = bases[model.id]
        found = problems[model.id]
        if not wholly_within(base, BOARD):
            found.append("is off the battlefield")
        for _, other_model, other in others:
            if overlaps(base, other):
                found.append(f"overlaps {other_model.model.name}")
                break
        if any(o.id != model.id and overlaps(base, bases[o.id]) for o in models):
            found.append("overlaps another model in its unit")
        if feature := _feature_overlapped(base, features):
            found.append(f"overlaps {feature}")

    # Coherency.
    if len(models) > 1:
        for model in models:
            gaps = [gap(bases[model.id], bases[o.id]) for o in models if o.id != model.id]
            if not any(g <= COHERENCY_RANGE + TOLERANCE for g in gaps):
                problems[model.id].append('isn\'t within 2" of another model in its unit')
            far = sum(1 for g in gaps if g > UNIT_SPAN + TOLERANCE)
            if far:
                problems[model.id].append(f'is more than 9" from {_models_phrase(far)} in its unit')
    return problems


def summarise(models: list[UnitModel], problems: dict[int, list[str]]) -> Placement:
    # The unit's problems: each model's, by model name ("(x3)" if several
    # models have the same one).
    names = {m.id: m.model.name for m in models}
    counted = Counter((names[i], p) for i, found in problems.items() for p in found)
    summary = [
        f"{name} {problem}" + (f" (x{count})" if count > 1 else "")
        for (name, problem), count in counted.items()
    ]
    return Placement(summary, {i: found for i, found in problems.items() if found})


def check_placement(
    game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]
) -> Placement:
    # Whether the unit could be set up with its models at `placement` ((x, y,
    # rotation) by unit model id - every model in it).
    layout = game.layout
    if layout is None or layout.deployment is None:
        raise _bad_request("this game's battlefield has no deployment zones")
    models, bases = unit_bases(unit, placement)

    player = owner(game, unit)
    side = _side(game, player)
    own_zone = layout.deployment.zone(side)
    enemy_zone = layout.deployment.zone(_other_side(side))
    infiltrator = is_infiltrator(unit)
    others = placed_bases(game, unit)
    enemies = [base for p, _, base in others if p.seat != player.seat]

    problems = physical_problems(game, models, bases, others)
    for model in models:
        base = bases[model.id]
        if not wholly_within(base, BOARD) or wholly_inside(base, own_zone):
            continue
        found = []
        if not infiltrator:
            found.append(f"isn't wholly within the {side}'s deployment zone")
        else:
            if distance_to_polygon(base, enemy_zone) <= INFILTRATORS_RANGE + TOLERANCE:
                found.append('is within 9" of the enemy deployment zone')
            if any(gap(base, e) <= INFILTRATORS_RANGE + TOLERANCE for e in enemies):
                found.append('is within 9" of an enemy model')
        problems[model.id] = found + problems[model.id]
    return summarise(models, problems)


# --- a new unit's formation ---


def _grid(count: int) -> tuple[int, int]:
    # Rows and columns for `count` models: about square (within 9" of each
    # other), and at least 2 rows from 3 models, to keep it compact. A short
    # last row is centred under the rest: a lone model there sits between two
    # above it if there's an even number of columns, so with an odd number it
    # gets a column more.
    if count <= 2:
        return 1, count
    rows = max(2, round(math.sqrt(count)))
    columns = math.ceil(count / rows)
    if count % columns == 1 and columns % 2 == 1:
        columns += 1
    return math.ceil(count / columns), columns


def formation(game: Game, unit: Unit, x: float, y: float) -> dict[int, tuple[float, float, float]]:
    # Where to start a unit's models when it's set down at (x, y): in even rows
    # centred there (a short last row centred under the others), kept on the
    # battlefield - and, if (x, y) is in its owner's deployment zone, within
    # that zone's extent - then any model overlapping another or a terrain
    # feature moved to the nearest free spot. A starting point: the player then arranges them.
    models = unit_models(unit)
    sizes = {m.id: base_mm(m)[:2] for m in models}
    # Spaced by the widest and tallest bases (ovals start facing across).
    cell_x = max(w for w, _ in sizes.values()) / MM_PER_INCH + FORMATION_GAP
    cell_y = max(h for _, h in sizes.values()) / MM_PER_INCH + FORMATION_GAP
    rows, columns = _grid(len(models))
    offsets = {}
    for i, model in enumerate(models):
        row, column = divmod(i, columns)
        in_row = min(columns, len(models) - row * columns)
        shift = (columns - in_row) / 2
        offsets[model.id] = (
            (column + shift - (columns - 1) / 2) * cell_x,
            (row - (rows - 1) / 2) * cell_y,
        )

    # Keep it on the battlefield (and in the zone's extent, if set down in it).
    bounds = (0.0, 0.0, 60.0, 44.0)
    layout = game.layout
    zone = None
    if layout is not None and layout.deployment is not None:
        own_zone = layout.deployment.zone(_side(game, owner(game, unit)))
        if _contains((x, y), own_zone):
            zone = own_zone
            bounds = (
                min(p[0] for p in zone),
                min(p[1] for p in zone),
                max(p[0] for p in zone),
                max(p[1] for p in zone),
            )
    half = {
        m.id: (sizes[m.id][0] / 2 / MM_PER_INCH, sizes[m.id][1] / 2 / MM_PER_INCH)
        for m in models
    }
    left = min(offsets[i][0] - half[i][0] for i in offsets)
    right = max(offsets[i][0] + half[i][0] for i in offsets)
    top = min(offsets[i][1] - half[i][1] for i in offsets)
    bottom = max(offsets[i][1] + half[i][1] for i in offsets)
    x = min(max(x, bounds[0] - left), bounds[2] - right)
    y = min(max(y, bounds[1] - top), bounds[3] - bottom)

    taken = [base for _, _, base in placed_bases(game, unit)]
    features = _features(game)
    result = {}

    def free(base: Base, in_zone: bool) -> bool:
        return (
            wholly_within(base, BOARD)
            and (not in_zone or zone is None or wholly_inside(base, zone))
            and not any(overlaps(base, other) for other in taken)
            and _feature_overlapped(base, features) is None
        )

    for model in models:
        start = (x + offsets[model.id][0], y + offsets[model.id][1])
        spot = start
        if not free(base_at(model, *start), in_zone=False):
            spot = _nearest_free(model, start, free) or start
        taken.append(base_at(model, *spot))
        result[model.id] = (round(spot[0], 3), round(spot[1], 3), 0.0)
    return result


def _nearest_free(model: UnitModel, start: Point, free) -> Point | None:
    # The nearest spot to `start` where the model fits: in rings outward,
    # preferring its owner's deployment zone.
    for in_zone in (True, False):
        radius = NUDGE_STEP
        while radius <= NUDGE_LIMIT:
            steps = max(8, int(2 * math.pi * radius / NUDGE_STEP))
            for i in range(steps):
                angle = 2 * math.pi * i / steps
                spot = (start[0] + radius * math.cos(angle), start[1] + radius * math.sin(angle))
                if free(base_at(model, *spot), in_zone):
                    return spot
            radius += NUDGE_STEP
    return None


# --- deploying ---


def check_turn(game: Game, unit: Unit) -> None:
    # That it's the unit's owner's turn to deploy, and it isn't yet.
    if game.status != "deployment":
        raise _bad_request("the game isn't in deployment")
    player = owner(game, unit)
    if is_deployed(unit, positions(game)):
        raise _bad_request("that unit is already deployed")
    if deploying_seat(game) != player.seat:
        raise _bad_request("it isn't that player's turn to deploy")


def deploy(game: Game, unit: Unit, placement: dict[int, tuple[float, float, float]]) -> None:
    # Sets the unit up as placed, if it can be.
    check_turn(game, unit)
    result = check_placement(game, unit, placement)
    if not result.valid:
        raise _bad_request("can't deploy it there: " + "; ".join(result.problems))
    for unit_model_id, (x, y, rotation) in placement.items():
        game.model_positions.append(
            GameModelPosition(unit_model_id=unit_model_id, x=x, y=y, rotation=rotation)
        )
