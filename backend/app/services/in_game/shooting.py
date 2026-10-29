from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules.effects import ASSAULT
from app.models import (
    DetachmentRule,
    Effect,
    Game,
    GameFiringDeckUse,
    GameUnitMove,
    Unit,
    UnitModel,
    WeaponAbility,
)
from app.services import weapon_profiles
from app.services.in_game import actions, command_phase, deployment, embarked
from app.services.in_game import movement
from app.services.in_game.deployment import TOLERANCE, Base, Point, gap, outline
from app.services.in_game.terrain import area_polygon, convex_overlap, feature_polygons, within
from app.services.list_building import detachment_rules as detachment_rule_service
from app.services.list_building import enhancements
from app.services.list_building.enhancements import granted_weapons

# Shooting in the shooting phase. In their turn's shooting phase a player can
# shoot with each of their units once, at an enemy unit, using the combat
# calculator (app/services/combat.py) - with what the battlefield says:
#
# - How the unit moved this turn (see app/services/in_game/movement.py): it Advanced,
#   or Remained Stationary (didn't move, or none of its models went anywhere),
#   or moved less than 3" (its furthest-moved model). A unit that Fell Back,
#   or is within Engagement Range of an enemy, can't shoot; one that Advanced
#   can only shoot Assault weapons - unless an ability selected in the
#   Command phase lets it (see app/services/in_game/command_phase.py).
# - What each model can see: a line from some point of its base to some point
#   of a target model's base not passing through anything solid. Ruin walls
#   (green) are dense: always solid. Terrain areas with a ruin wall or an
#   obstacle in them are obscuring (13.10): solid too - unless one of the two
#   models is within that area. Obstacles (orange) are light and can be shot
#   through, and models don't block sight. A hidden model (13.09) - INFANTRY,
#   BEASTS or SWARM within a terrain area with a ruin wall, whose unit hasn't
#   made ranged attacks this turn or last - is only visible within 15".
# - Which weapons each model can fire: those with a visible target model
#   within range (base to base) - at half range if one is within half.
# - Targets must be unengaged (04.02), but for an engaged MONSTER/VEHICLE
#   unit: -1 to hit, and not with [BLAST] weapons (17.03).
# - An engaged unit shoots using close-quarters shooting (10.06), if it has
#   [CLOSE-QUARTERS] (Pistol) weapons or is a MONSTER/VEHICLE unit: its
#   non-MONSTER/VEHICLE models only fire those, and only at units their unit
#   is engaged with; its MONSTER/VEHICLE models fire any (at -1 to hit, but
#   close-quarters weapons at a unit they're engaged with), never [BLAST]
#   at an engaged unit. In other shooting, each non-MONSTER/VEHICLE model
#   fires either its close-quarters weapons or its other ranged weapons.
# - A target none of its models can see: indirect shooting (10.07), with
#   only its [INDIRECT FIRE] weapons.
# - Whether the target has the benefit of cover (13.08): every model in it is
#   INFANTRY/BEASTS/SWARM within a terrain area, or isn't fully visible to the
#   shooting unit's models because of terrain.
# - A TRANSPORT with Firing Deck N can also fire the ranged weapons of up to N
#   models embarked in it, as if it had them (measured from it). Its
#   firing-deck weapons are grouped by weapon (ids ("deck", weapon id)): each
#   one chosen is fired by the embarked models carrying it - the first N
#   models carrying any chosen one. Then, until the end of the turn, the
#   units embarked in it aren't eligible to shoot.

FIRING_DECK = re.compile(r"^Firing Deck (\d+)$")
DENSE = "ruin_wall"
COVER_KEYWORDS = {"INFANTRY", "BEAST", "BEASTS", "SWARM"}
# Points around each base sight lines are drawn between (and its centre).
SIGHT_POINTS = 8


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def is_shooting_phase(game: Game) -> bool:
    return game.status == "in_progress" and game.phase == "shooting"


def _this_turn(game: Game, record) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def firing_deck(unit: Unit) -> int:
    # How many embarked models' weapons the unit can fire (Firing Deck N), if
    # any.
    return max(
        (
            int(match.group(1))
            for m in unit.unit_models
            for a in m.model.abilities
            if (match := FIRING_DECK.match(a.name))
        ),
        default=0,
    )


def _deck_carrier(unit: Unit) -> UnitModel | None:
    # The model with Firing Deck (the deck's weapons are fired from it).
    return next(
        (m for m in unit.unit_models if any(FIRING_DECK.match(a.name) for a in m.model.abilities)),
        None,
    )


def deck_models(game: Game, transport: Unit) -> list[UnitModel]:
    # The models embarked in the transport (not destroyed), in unit order.
    player = deployment.owner(game, transport)
    return [
        m
        for unit in deployment.deployable_units(player)
        if getattr(embarked.transport(game, unit), "id", None) == transport.id
        for m in embarked.surviving_models(game, unit)
    ]


def deck_weapons(
    game: Game, transport: Unit, weapon_ids: set[int] | None = None
) -> list[tuple[UnitModel, object]]:
    # The (embarked model, ranged weapon) pairs the transport's Firing Deck
    # fires (24.14): with `weapon_ids`, up to N models carrying one of those
    # weapons, each firing one of them; without, every embarked model's (to
    # show what it could). Not [ONE SHOT] weapons, nor models whose units have
    # already shot this phase.
    limit = firing_deck(transport)
    if not limit:
        return []
    pairs = []
    chosen = 0
    for unit_model in deck_models(game, transport):
        own_unit = deployment.find_unit(game, unit_model.unit_id)
        if unit_shot(game, own_unit) is not None:
            continue
        # (Their own weapons - not an enhancement's.)
        weapons = [
            w
            for w in unit_model.weapons
            if w.weapon_type != "melee"
            and w.range
            and not any(a.name == "One Shot" for a in w.abilities)
            and (weapon_ids is None or w.id in weapon_ids)
        ]
        if not weapons:
            continue
        if weapon_ids is not None:
            if chosen == limit:
                break
            chosen += 1
            weapons = weapons[:1]
        pairs += [(unit_model, w) for w in weapons]
    return pairs


def deck_id(unit_model: UnitModel, weapon) -> tuple:
    # A firing-deck weapon as the combat calculator fires it.
    return ("deck", unit_model.id, weapon.id)


def deck_closed(game: Game, unit: Unit) -> bool:
    # Whether the unit is in (or got out of) a transport that used its Firing
    # Deck this turn: it isn't eligible to shoot until the end of the turn.
    return any(
        u.unit_id == unit.id
        and u.battle_round == game.battle_round
        and u.turn_seat == game.turn_seat
        for u in game.firing_deck_uses
    )


def record_deck(game: Game, transport: Unit) -> None:
    # The transport used its Firing Deck: the units in it can't shoot this
    # turn.
    player = deployment.owner(game, transport)
    for unit in deployment.deployable_units(player):
        if getattr(embarked.transport(game, unit), "id", None) == transport.id:
            game.firing_deck_uses.append(
                GameFiringDeckUse(
                    unit_id=unit.id,
                    transport_unit_id=transport.id,
                    battle_round=game.battle_round,
                    turn_seat=game.turn_seat,
                )
            )


def unit_shot(game: Game, unit: Unit):
    # The unit's shooting this phase, if it has.
    return next(
        (s for s in game.unit_shots if s.unit_id == unit.id and _this_turn(game, s)), None
    )


# --- how the unit moved ---


@dataclass
class MoveStatus:
    advanced: bool = False
    fell_back: bool = False
    remained_stationary: bool = False
    moved_less_than_3: bool = False
    # How far its furthest-moved model went, if known.
    distance: float | None = None


def move_status(game: Game, unit: Unit) -> MoveStatus:
    # How the unit moved in this turn's movement phase.
    move: GameUnitMove | None = next(
        (
            m
            for m in game.unit_moves
            if m.unit_id == unit.id and m.completed and _this_turn(game, m)
        ),
        None,
    )
    if move is None:
        return MoveStatus(remained_stationary=True, moved_less_than_3=True, distance=0.0)
    distance = move.distance
    return MoveStatus(
        advanced=move.kind == "advance",
        fell_back=move.kind == "fall_back",
        # A Normal move that took no model anywhere.
        remained_stationary=(
            move.kind == "normal" and distance is not None and distance <= TOLERANCE
        ),
        moved_less_than_3=distance is not None and distance < 3,
        distance=distance,
    )


# --- line of sight ---


def _clip(a: Point, b: Point, polygon: list[Point]) -> tuple[float, float] | None:
    # Where the segment ab is inside a convex polygon, as (enter, leave)
    # fractions along it - None if it doesn't pass through the inside (just
    # touching an edge or corner doesn't count). Clipped to each edge's inside.
    area2 = sum(p[0] * q[1] - p[1] * q[0] for p, q in zip(polygon, polygon[1:] + polygon[:1]))
    sign = 1 if area2 > 0 else -1
    dx, dy = b[0] - a[0], b[1] - a[1]
    enter, leave = 0.0, 1.0
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        ex, ey = q[0] - p[0], q[1] - p[1]
        # Inside is where sign * cross(edge, point - p) >= 0, along the segment
        # start + t * direction.
        start = sign * (ex * (a[1] - p[1]) - ey * (a[0] - p[0]))
        rate = sign * (ex * dy - ey * dx)
        if abs(rate) < 1e-12:
            if start <= TOLERANCE:
                return None  # parallel, and outside (or on) this edge
            continue
        t = -start / rate
        if rate > 0:
            enter = max(enter, t)
        else:
            leave = min(leave, t)
        if leave - enter <= TOLERANCE:
            return None
    return (enter, leave) if leave - enter > TOLERANCE else None


def _blocks(a: Point, b: Point, polygon: list[Point]) -> bool:
    # Whether the segment ab passes through the inside of a convex polygon.
    return _clip(a, b, polygon) is not None


def _sight_points(base: Base) -> list[Point]:
    return [(base.x, base.y), *outline(base, SIGHT_POINTS)]


def dense_terrain(game: Game) -> list[list[Point]]:
    # Each part of every dense terrain feature (ruin walls) on the battlefield.
    layout = game.layout
    if layout is None:
        return []
    return [
        polygon
        for feature in layout.features
        if feature.shape.kind == DENSE
        for polygon in feature_polygons(feature)
    ]


# Terrain areas this close together count as touching: sight can't pass
# through the gap between them (see _bridges).
AREA_GAP = 1.0
# The bridges between each layout's areas, worked out once: {the areas'
# corners: [(first area index, second area index, polygon)]}.
_BRIDGES: dict[tuple, list[tuple[int, int, list[Point]]]] = {}


def _segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    along = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2 if length2 else 0.0
    t = max(0.0, min(1.0, along))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _polygon_distance(p: Point, polygon: list[Point]) -> float:
    return min(_segment_distance(p, a, b) for a, b in zip(polygon, polygon[1:] + polygon[:1]))


def _edge_points(polygon: list[Point], step: float = 0.2) -> list[Point]:
    # Points along a polygon's edges, about `step` apart (its corners too).
    found = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        count = max(1, math.ceil(math.dist(a, b) / step))
        found += [(a[0] + (b[0] - a[0]) * i / count, a[1] + (b[1] - a[1]) * i / count)
                  for i in range(count)]
    return found


def _hull(points: list[Point]) -> list[Point]:
    # The convex hull (monotone chain), corners in order.
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _widened(polygon: list[Point], by: float) -> list[Point]:
    # Each corner pushed `by` further from the centre (so a bridge along a
    # seam has some width).
    cx = sum(p[0] for p in polygon) / len(polygon)
    cy = sum(p[1] for p in polygon) / len(polygon)
    out = []
    for x, y in polygon:
        d = math.hypot(x - cx, y - cy) or 1.0
        out.append((x + (x - cx) / d * by, y + (y - cy) / d * by))
    return out


def _bridges(areas: list[list[Point]]) -> list[tuple[int, int, list[Point]]]:
    # Between each two terrain areas within AREA_GAP of each other: the gap
    # between them, as a solid convex shape - the hull of each one's edge
    # points within AREA_GAP of the other.
    key = tuple(tuple(round(c, 3) for p in a for c in p) for a in areas)
    if key in _BRIDGES:
        return _BRIDGES[key]
    edges = [_edge_points(a) for a in areas]
    found = []
    for i in range(len(areas)):
        for j in range(i + 1, len(areas)):
            near = [p for p in edges[i] if _polygon_distance(p, areas[j]) <= AREA_GAP]
            near += [p for p in edges[j] if _polygon_distance(p, areas[i]) <= AREA_GAP]
            if len(near) < 2:
                continue
            hull = _hull(near)
            if len(hull) < 3:
                # Along a straight seam: give it some width.
                (ax, ay), (bx, by) = hull[0], hull[-1]
                length = math.hypot(bx - ax, by - ay) or 1.0
                nx, ny = -(by - ay) / length * 0.05, (bx - ax) / length * 0.05
                hull = [
                    (ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)
                ]
            found.append((i, j, _widened(hull, 0.05)))
    _BRIDGES[key] = found
    return found


def obscuring_areas(game: Game, bases: list[Base]) -> list[list[Point]]:
    # The battlefield's terrain areas that block sight between two units:
    # those none of their models (`bases`) is touching - and the gaps between
    # any two of those that are next to each other (within AREA_GAP), which
    # count as touching, so sight can't slip between them.
    t = terrain(game)
    solid = [
        obscures and not any(within(base, area) for base in bases)
        for area, obscures in zip(t.areas, t.obscuring)
    ]
    bridges = [
        polygon
        for i, j, polygon in t.bridges
        if solid[i] and solid[j] and not any(within(base, polygon) for base in bases)
    ]
    return [area for area, blocks in zip(t.areas, solid) if blocks] + bridges


@dataclass
class _Terrain:
    # A layout's terrain, for sight: its ruin walls' parts, its terrain areas
    # (each with whether it's obscuring - has a ruin wall or obstacle in it -
    # and whether it has a ruin wall, for Hidden), and the gaps between
    # neighbouring areas (see _bridges).
    dense: list[list[Point]]
    areas: list[list[Point]]
    obscuring: list[bool]
    has_dense: list[bool]
    bridges: list[tuple[int, int, list[Point]]]


def terrain(game: Game) -> _Terrain:
    layout = game.layout
    if layout is None:
        return _Terrain([], [], [], [], [])
    areas = [area_polygon(a) for a in layout.areas]
    features = [
        (feature.shape.kind, polygon)
        for feature in layout.features
        for polygon in feature_polygons(feature)
    ]

    def has(area, kinds) -> bool:
        return any(
            kind in kinds and convex_overlap(part, area, touching=False) for kind, part in features
        )

    return _Terrain(
        dense=[polygon for kind, polygon in features if kind == DENSE],
        areas=areas,
        obscuring=[has(a, {DENSE, "obstacle"}) for a in areas],
        has_dense=[has(a, {DENSE}) for a in areas],
        bridges=_bridges(areas),
    )


class Sight:
    # Line of sight on a battlefield, between two models' bases: through no
    # ruin wall, and no obscuring terrain area neither of them is within (nor
    # the gap between two such areas next to each other).

    def __init__(self, game: Game):
        self.terrain = terrain(game)

    def walls(self, a: Base, b: Base) -> list[list[Point]]:
        t = self.terrain
        solid = [
            obscures and not within(a, area) and not within(b, area)
            for area, obscures in zip(t.areas, t.obscuring)
        ]
        bridges = [
            polygon
            for i, j, polygon in t.bridges
            if solid[i] and solid[j] and not within(a, polygon) and not within(b, polygon)
        ]
        return t.dense + [area for area, s in zip(t.areas, solid) if s] + bridges

    def sees(self, a: Base, b: Base) -> bool:
        return can_see(a, b, self.walls(a, b))

    def fully_sees(self, a: Base, b: Base) -> bool:
        # Whether every point round the target model's base can be seen from
        # some point of the observer's (13.08 - not fully visible: cover).
        walls = self.walls(a, b)
        sources = _sight_points(a)
        return all(
            any(not any(_blocks(v, p, w) for w in walls) for v in sources)
            for p in _sight_points(b)
        )

    def in_area(self, base: Base, dense_only: bool = False) -> bool:
        # Whether the base is within a terrain area (one with a ruin wall).
        return any(
            within(base, area)
            for area, dense in zip(self.terrain.areas, self.terrain.has_dense)
            if dense or not dense_only
        )


DETECTION_RANGE = 15.0


def hidden_models(game: Game, unit: Unit, sight: Sight) -> set[int]:
    # The unit's hidden models (13.09): INFANTRY/BEASTS/SWARM models within a
    # terrain area with a ruin wall in it, if the unit hasn't made ranged
    # attacks this turn or the previous one.
    if _shot_recently(game, unit):
        return set()
    bases = _bases(game, unit)
    return {
        m.id
        for m in unit.unit_models
        if m.id in bases
        and enhancements.model_keywords(unit, m) & COVER_KEYWORDS
        and sight.in_area(bases[m.id], dense_only=True)
    }


def _turn_index(battle_round: int, turn_seat: int, first_seat: int | None) -> int:
    return battle_round * 2 + (0 if turn_seat == first_seat else 1)


def _shot_recently(game: Game, unit: Unit) -> bool:
    # Whether the unit made ranged attacks this turn or the previous one.
    now = _turn_index(game.battle_round, game.turn_seat, game.first_seat)
    return any(
        s.unit_id == unit.id
        and now - _turn_index(s.battle_round, s.turn_seat, game.first_seat) <= 1
        for s in game.unit_shots
    )


def can_see(viewer: Base, target: Base, walls: list[list[Point]]) -> bool:
    # Whether a line can be drawn from some point of one base to some point of
    # the other without passing through any of `walls` (solid convex shapes).
    # Only those whose extent overlaps the two bases' are looked at.
    sources, targets = _sight_points(viewer), _sight_points(target)
    xs = [p[0] for p in sources + targets]
    ys = [p[1] for p in sources + targets]
    near = [
        wall
        for wall in walls
        if max(p[0] for p in wall) >= min(xs)
        and min(p[0] for p in wall) <= max(xs)
        and max(p[1] for p in wall) >= min(ys)
        and min(p[1] for p in wall) <= max(ys)
    ]
    if not near:
        return True
    return any(
        not any(_blocks(a, b, wall) for wall in near) for a in sources for b in targets
    )


# --- weapons ---


def ranged_weapons(unit_model: UnitModel) -> list:
    # The ranged weapons a model has: its own, and any its enhancement gives
    # it (whose ids are ("enhancement", id) - see app/services/list_building/enhancements.py).
    return [
        w
        for w in list(unit_model.weapons) + granted_weapons(unit_model)
        if w.weapon_type != "melee" and w.range
    ]


async def assault_ability_ids(session: AsyncSession) -> set[int]:
    # The weapon abilities that give a weapon Assault.
    query = (
        select(WeaponAbility.id).join(WeaponAbility.effects).where(Effect.keyword == ASSAULT)
    )
    return set((await session.execute(query)).scalars())


def assault_weapons(
    unit: Unit, detachment_rules: list[DetachmentRule], assault_ids: set[int]
) -> set:
    # The unit's ranged weapons with Assault: their own abilities, or granted
    # to its ranged weapons by an enhancement, upgrade or detachment rule (as
    # the calculator sees them - see app/services/combat.py). `unit` must be
    # loaded as the calculator loads it.
    found = set()
    for unit_model in unit.unit_models:
        granted = [
            ability
            for ability, only in enhancements.granted_weapon_abilities(unit, unit_model)
            + detachment_rule_service.granted_weapon_abilities(
                detachment_rules, unit, unit_model
            )
            if only in (None, "ranged")
        ]
        for weapon in ranged_weapons(unit_model):
            if any(a.id in assault_ids for a in list(weapon.abilities) + granted):
                found.add(weapon.id)
    return found


@dataclass
class WeaponReach:
    # A weapon the unit has, against a target: how many of the unit's models
    # carrying it could fire it (a visible target model within range), and
    # whether any could at half range.
    id: object
    name: str
    range: int
    carried_by: int = 0
    in_range: int = 0
    half_range: bool = False
    assault: bool = False
    # It can't be fired at all this phase (the unit Advanced and it isn't
    # Assault) - then it's never in range.
    unusable: bool = False
    # Chosen to start with: for melee, each model's first weapon (a model with
    # several usually fights with one of them).
    default: bool = False
    # For melee: its Attacks characteristic, and whether it's an [EXTRA
    # ATTACKS] weapon (always used, as well as one other).
    attacks: str = ""
    extra_attacks: bool = False


@dataclass
class TargetReach:
    # What the unit can do to an enemy unit: whether any of its models can see
    # it, whether it's in cover, each weapon's reach, and which weapons each
    # model can fire ({unit model id: {weapon id: half range}}) - and how far
    # its nearest visible model is from the nearest of the unit's (None if it
    # can't see any).
    unit: Unit
    visible: bool
    in_cover: bool
    weapons: list[WeaponReach]
    firing: dict[int, dict] = field(default_factory=dict)
    distance: float | None = None
    # Indirect shooting (10.07): none of its models can see the target, so
    # only its [INDIRECT FIRE] weapons can shoot it (with their penalties) -
    # `spotted` if the unit remained stationary and a friendly unit can see
    # the target.
    indirect: bool = False
    spotted: bool = False


def _bases(game: Game, unit: Unit) -> dict[int, Base]:
    placed = deployment.positions(game)
    return {
        m.id: deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    }


def in_cover(
    game: Game, unit: Unit, shooters: list[Base] | None = None, sight: Sight | None = None
) -> bool:
    # The benefit of cover (13.08): every model in the unit is
    # INFANTRY/BEASTS/SWARM within a terrain area, or isn't fully visible to
    # any of the shooting models (`shooters`) because of terrain.
    if game.layout is None:
        return False
    sight = sight or Sight(game)
    bases = _bases(game, unit)
    if not bases:
        return False

    def covered(unit_model) -> bool:
        base = bases[unit_model.id]
        if enhancements.model_keywords(unit, unit_model) & COVER_KEYWORDS and sight.in_area(base):
            return True
        return bool(shooters) and not any(sight.fully_sees(s, base) for s in shooters)

    return all(covered(m) for m in unit.unit_models if m.id in bases)


# Lone Operative: a unit with it can only be targeted by ranged attacks
# from models within 12" of it.
LONE_OPERATIVE = "Lone Operative"
LONE_OPERATIVE_RANGE = 12.0


def leading(unit: Unit) -> bool:
    # Whether a CHARACTER is leading the unit: it has CHARACTER models and
    # others.
    characters = ["CHARACTER" in {k.name for k in m.model.keywords} for m in unit.unit_models]
    return any(characters) and not all(characters)


def lone_operative(game: Game, unit: Unit) -> bool:
    # Whether the unit has Lone Operative now: one of its models has it, or
    # an ability that gives it while near friendly units with some keywords
    # (datasheet_abilities CONDITIONAL_LONE_OPERATIVE - e.g. Leader of
    # Astartes: within 3" of a friendly ADEPTUS ASTARTES INFANTRY unit) - for
    # some, only while it isn't leading a unit (e.g. Enginseer).
    from app.seeds import datasheet_abilities as datasheet_ability_seeds

    names = {a.name for m in unit.unit_models for a in m.model.abilities}
    if LONE_OPERATIVE in names:
        return True
    conditional = datasheet_ability_seeds.CONDITIONAL_LONE_OPERATIVE
    found = [conditional[n] for n in names if n in conditional]
    if not found:
        return False
    own = list(_bases(game, unit).values())
    player = deployment.owner(game, unit)
    placed = deployment.positions(game)
    for distance, keywords, *unless_leading in found:
        if unless_leading and unless_leading[0] and leading(unit):
            continue
        for other in deployment.deployable_units(player):
            if other.id == unit.id or not deployment.is_deployed(other, placed):
                continue
            models = deployment.models_on_battlefield(game, other)
            if not all(
                set(keywords) <= enhancements.model_keywords(other, m) for m in models
            ):
                continue
            others = list(_bases(game, other).values())
            if any(gap(a, b) <= distance + TOLERANCE for a in own for b in others):
                return True
    return False


CLOSE_QUARTERS = {"Pistol", "Close-Quarters"}
BIG = {"MONSTER", "VEHICLE"}


def close_quarters(weapon) -> bool:
    # A [CLOSE-QUARTERS] (or [PISTOL] - the same, 24.27) weapon.
    return any(a.name in CLOSE_QUARTERS for a in getattr(weapon, "abilities", []))


def _blast(weapon) -> bool:
    return any(a.name.startswith("Blast") for a in getattr(weapon, "abilities", []))


def _big(unit: Unit, unit_model: UnitModel | None = None) -> bool:
    # A MONSTER/VEHICLE model (or, without one, unit: all of its models).
    models = [unit_model] if unit_model is not None else unit.unit_models
    return all(enhancements.model_keywords(unit, m) & BIG for m in models)


def engaged_with(game: Game, unit: Unit, other: Unit) -> bool:
    # Whether the two units are engaged with each other.
    from app.services.in_game.charging import distance

    return distance(game, unit, other) <= movement.ENGAGEMENT_RANGE + TOLERANCE


def _weapon_allowed(
    game: Game, unit: Unit, unit_model: UnitModel, weapon, target: Unit
) -> bool:
    # Whether the model can fire the weapon at the target at all, by who's
    # engaged (see above).
    big = _big(unit, unit_model)
    if movement.in_engagement_range(game, unit):
        if _blast(weapon) and movement.in_engagement_range(game, target):
            return False
        if big:
            return True
        return close_quarters(weapon) and engaged_with(game, unit, target)
    if movement.in_engagement_range(game, target):
        return _big(target) and not _blast(weapon)
    return True


def reach(game: Game, unit: Unit, target: Unit, assault: set | None = None) -> TargetReach:
    # `assault` is the unit's Assault weapons (see assault_weapons): if it
    # Advanced, only those can fire. A target with Lone Operative is only in
    # range of models within 12" of it.
    assault = assault or set()
    # How close a model has to be to target it: Lone Operative's 12", or a
    # psychic ability's (e.g. Psychic Veil: 18") - the closer.
    from app.services.in_game import psychic

    limits = [LONE_OPERATIVE_RANGE] if lone_operative(game, target) else []
    if (veil := psychic.targeted_within(game, target)) is not None:
        limits.append(veil)
    target_limit = min(limits, default=None)
    advanced = move_status(game, unit).advanced
    shooters = _bases(game, unit)
    target_bases = _bases(game, target)
    targets = list(target_bases.values())
    sight = Sight(game)
    hidden = hidden_models(game, target, sight)

    def sees(base: Base) -> list[Base]:
        # The target models the base can see: hidden ones only within 15".
        return [
            t
            for i, t in target_bases.items()
            if sight.sees(base, t)
            and (i not in hidden or gap(base, t) <= DETECTION_RANGE + TOLERANCE)
        ]
    reaches: dict[object, WeaponReach] = {}
    firing: dict[int, dict] = {}
    visible = False
    closest = None
    # Each model's nearest target model, seen or not (for indirect fire).
    unseen: dict[int, float] = {}
    for unit_model in deployment.unit_models(unit):
        base = shooters.get(unit_model.id)
        weapons = ranged_weapons(unit_model)
        if base is None or not weapons:
            continue
        unseen[unit_model.id] = min((gap(base, t) for t in targets), default=math.inf)
        # How far it is from each target model it can see.
        gaps = [gap(base, t) for t in sees(base)]
        visible = visible or bool(gaps)
        nearest = min(gaps, default=None)
        if nearest is not None:
            closest = nearest if closest is None else min(closest, nearest)
        for weapon in weapons:
            entry = reaches.setdefault(
                weapon.id,
                WeaponReach(
                    id=weapon.id,
                    name=weapon.name,
                    range=weapon.range,
                    assault=weapon.id in assault,
                    unusable=advanced and weapon.id not in assault,
                ),
            )
            entry.carried_by += 1
            if entry.unusable or not _weapon_allowed(game, unit, unit_model, weapon, target):
                continue
            limit = min(weapon.range, target_limit) if target_limit else weapon.range
            if nearest is not None and nearest <= limit + TOLERANCE:
                half = nearest <= weapon.range / 2 + TOLERANCE
                entry.in_range += 1
                entry.half_range = entry.half_range or half
                firing.setdefault(unit_model.id, {})[weapon.id] = half
    # Its Firing Deck: the embarked models' weapons, fired from the model with
    # it.
    carrier = _deck_carrier(unit)
    base = shooters.get(carrier.id) if carrier is not None else None
    if base is not None:
        gaps = [gap(base, t) for t in sees(base)]
        nearest = min(gaps, default=None)
        for embarked_model, weapon in deck_weapons(game, unit):
            entry = reaches.setdefault(
                ("deck", weapon.id),
                WeaponReach(
                    id=("deck", weapon.id),
                    name=f"{weapon.name} (Firing Deck)",
                    range=weapon.range,
                    assault=weapon.id in assault,
                    unusable=advanced and weapon.id not in assault,
                ),
            )
            entry.carried_by += 1
            if entry.unusable:
                continue
            limit = min(weapon.range, target_limit) if target_limit else weapon.range
            if nearest is not None and nearest <= limit + TOLERANCE:
                half = nearest <= weapon.range / 2 + TOLERANCE
                entry.in_range += 1
                entry.half_range = entry.half_range or half
                firing.setdefault(carrier.id, {})[deck_id(embarked_model, weapon)] = half
    # No model can see it: indirect shooting - only [INDIRECT FIRE] weapons,
    # each model's within range of the target (seen or not).
    indirect = False
    if not visible:
        firing = {}
        for entry in reaches.values():
            entry.in_range, entry.half_range = 0, False
        for unit_model in deployment.unit_models(unit):
            nearest = unseen.get(unit_model.id)
            if nearest is None:
                continue
            for weapon in ranged_weapons(unit_model):
                entry = reaches[weapon.id]
                if (
                    entry.unusable
                    or not _indirect(weapon)
                    or not _weapon_allowed(game, unit, unit_model, weapon, target)
                ):
                    continue
                limit = min(weapon.range, target_limit) if target_limit else weapon.range
                if nearest <= limit + TOLERANCE:
                    half = nearest <= weapon.range / 2 + TOLERANCE
                    entry.in_range += 1
                    entry.half_range = entry.half_range or half
                    firing.setdefault(unit_model.id, {})[weapon.id] = half
                    indirect = True
    # (Soul Sight: ranged attacks that target it ignore cover this phase.)
    from app.services.in_game import psychic

    return TargetReach(
        unit=target,
        visible=visible,
        in_cover=in_cover(game, target, list(shooters.values()), sight)
        and not psychic.soul_sighted(game, target),
        weapons=list(reaches.values()),
        firing=firing,
        distance=closest,
        indirect=indirect,
        spotted=indirect and move_status(game, unit).remained_stationary
        and _seen_by_friends(game, unit, target),
    )


def set_up_this_turn(game: Game, unit: Unit) -> bool:
    # Whether the unit was set up on the battlefield this turn: it arrived
    # from Reserves, or disembarked (e.g. for [HEAVY]).
    from app.services.in_game.reinforcements import ARRIVED

    arrived = any(
        m.unit_id == unit.id and m.kind == ARRIVED and _this_turn(game, m)
        for m in game.unit_moves
    )
    return arrived or any(
        d.unit_id == unit.id and _this_turn(game, d) for d in game.disembarkations
    )


def _indirect(weapon) -> bool:
    from app.services.combat import INDIRECT_FIRE

    return any(a.name == INDIRECT_FIRE for a in getattr(weapon, "abilities", []))


def _seen_by_friends(game: Game, unit: Unit, target: Unit) -> bool:
    # Whether another of the unit's player's units on the battlefield can see
    # the target (for indirect fire: unmodified 4+ hits).
    player = deployment.owner(game, unit)
    targets = list(_bases(game, target).values())
    sight = Sight(game)
    for other in deployment.deployable_units(player):
        if other.id == unit.id:
            continue
        bases = list(_bases(game, other).values())
        if any(sight.sees(b, t) for b in bases for t in targets):
            return True
    return False


# --- where it can shoot (to show it) ---

# Rays cast from each viewpoint of a model's base, evenly round.
BUBBLE_RAYS = 180
# Viewpoints round each base's edge (plus its centre).
BUBBLE_VIEWPOINTS = 4


@dataclass
class _Obstacle:
    # Something solid to sight, as seen from one viewpoint: its corners, and
    # the angles it covers (centre and half-width, radians). A dense one
    # (a wall) stops a sight line where it enters; a terrain area, where it
    # leaves - a target on the area itself could be seen.
    polygon: list[Point]
    dense: bool
    angle: float
    half_width: float


def _obstacles(origin: Point, reach: float, walls, areas) -> list[_Obstacle]:
    # The walls and areas within `reach` of `origin`, with the angles they
    # cover from it.
    found = []
    for polygon, dense in [(w, True) for w in walls] + [(a, False) for a in areas]:
        nearest = min(math.hypot(p[0] - origin[0], p[1] - origin[1]) for p in polygon)
        if nearest > reach + max(
            math.hypot(p[0] - q[0], p[1] - q[1]) for p in polygon for q in polygon
        ):
            continue
        angles = [math.atan2(p[1] - origin[1], p[0] - origin[0]) for p in polygon]
        # Relative to the first corner's angle, unwrapped.
        first = angles[0]
        relative = [math.remainder(a - first, 2 * math.pi) for a in angles]
        low, high = min(relative), max(relative)
        found.append(
            _Obstacle(polygon, dense, first + (low + high) / 2, (high - low) / 2 + 1e-6)
        )
    return found


def _visible_region(origin: Point, reach: float, obstacles: list[_Obstacle]) -> list[Point]:
    # How far a sight line gets from `origin` in each direction, up to
    # `reach`: a star-shaped polygon round it.
    points = []
    for i in range(BUBBLE_RAYS):
        angle = 2 * math.pi * i / BUBBLE_RAYS
        end = (origin[0] + reach * math.cos(angle), origin[1] + reach * math.sin(angle))
        stop = 1.0
        for obstacle in obstacles:
            if abs(math.remainder(angle - obstacle.angle, 2 * math.pi)) > obstacle.half_width:
                continue
            inside = _clip(origin, end, obstacle.polygon)
            if inside is not None:
                stop = min(stop, inside[0] if obstacle.dense else inside[1])
        points.append(
            (origin[0] + (end[0] - origin[0]) * stop, origin[1] + (end[1] - origin[1]) * stop)
        )
    return points


@dataclass
class Bubble:
    # Where the unit's guns reach: its longest-ranged weapon it can fire this
    # phase, and the regions it can see within that range (one per viewpoint
    # of each model - together, the bubble).
    range: int | None
    regions: list[list[Point]]


def sight_bubble(
    game: Game, unit: Unit, assault: set | None = None, max_range: float | None = None
) -> Bubble:
    # Where the unit's models could shoot something: within its longest range
    # (base to base), and not hidden by ruin walls or by terrain areas it isn't
    # touching (see reach). Seen from each model's centre and points round its
    # base. If it Advanced, only its Assault weapons count (`assault`); no
    # further than `max_range`, if given (e.g. Fire Overwatch's 24").
    assault = assault or set()
    advanced = move_status(game, unit).advanced
    bases = _bases(game, unit)
    walls = dense_terrain(game)
    areas = obscuring_areas(game, list(bases.values()))
    regions = []
    longest = None
    for unit_model in deployment.unit_models(unit):
        base = bases.get(unit_model.id)
        ranges = [
            w.range
            for w in ranged_weapons(unit_model)
            if not advanced or w.id in assault
        ]
        if base is None or not ranges:
            continue
        weapon_range = max(ranges) if max_range is None else min(max(ranges), max_range)
        longest = max(longest or 0, weapon_range)
        radius = max(base.semi_axes)
        viewpoints = [((base.x, base.y), weapon_range + radius)] + [
            (p, weapon_range) for p in outline(base, BUBBLE_VIEWPOINTS)
        ]
        for origin, reach_ in viewpoints:
            regions.append(
                _visible_region(origin, reach_, _obstacles(origin, reach_, walls, areas))
            )
    return Bubble(range=longest, regions=regions)


# --- who can shoot ---


def shooting_units(game: Game) -> list[Unit]:
    # The units the player whose turn it is has on the battlefield.
    return movement.movable_units(game)


def enemy_units(game: Game, unit: Unit) -> list[Unit]:
    seat = deployment.owner(game, unit).seat
    placed = deployment.positions(game)
    return [
        u
        for player in game.players
        if player.seat != seat
        for u in deployment.deployable_units(player)
        if deployment.is_deployed(u, placed)
    ]


def cant_shoot_reason(game: Game, unit: Unit, assault: set | None = None) -> str | None:
    # Why the unit can't shoot now, or None if it can. `assault` is its
    # Assault weapons (see assault_weapons).
    if not is_shooting_phase(game):
        return "units can only shoot in the shooting phase"
    if deployment.owner(game, unit).seat != game.turn_seat:
        return "only the player whose turn it is can shoot with their units"
    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if unit_shot(game, unit) is not None:
        return "it has already shot this phase"
    if deck_closed(game, unit):
        return "its transport fired its weapons with Firing Deck this turn"
    if (reason := actions.blocks(game, unit, "shoot")) is not None:
        return reason
    if move_status(game, unit).fell_back and not command_phase.eligible_after(
        game, unit, "fell_back", "shoot"
    ):
        return "it Fell Back this turn"
    if movement.in_engagement_range(game, unit):
        # Close-quarters shooting: not after Advancing, and only with
        # close-quarters weapons or as a MONSTER/VEHICLE unit.
        if move_status(game, unit).advanced:
            return "it's engaged, and it Advanced this turn"
        models = deployment.models_on_battlefield(game, unit)
        if not _big(unit) and not any(
            close_quarters(w) for m in models for w in ranged_weapons(m)
        ):
            return "it's engaged, and has no [CLOSE-QUARTERS] weapons"
    if not any(
        ranged_weapons(m) for m in deployment.models_on_battlefield(game, unit)
    ) and not deck_weapons(game, unit):
        return "it has no ranged weapons"
    if move_status(game, unit).advanced and not assault:
        return "it Advanced, and has no Assault weapons"
    return None


def check_shot(
    game: Game, unit: Unit, target: Unit, weapon_ids: set, assault: set | None = None
) -> TargetReach:
    # That the unit can shoot the target with those weapons (each in range of
    # it for at least one model, and Assault if it Advanced); what it can do
    # to it.
    if (reason := cant_shoot_reason(game, unit, assault)) is not None:
        raise _bad_request(f"it can't shoot: {reason}")
    if target.id not in {u.id for u in enemy_units(game, unit)}:
        raise _bad_request("the target must be an enemy unit on the battlefield")
    result = reach(game, unit, target, assault)
    if not result.visible and not result.indirect:
        raise _bad_request("none of its models can see the target")
    if not weapon_ids:
        raise _bad_request("choose at least one weapon to shoot with")
    if (conflict := weapon_profiles.unit_conflict(unit, weapon_ids)) is not None:
        raise _bad_request(conflict)
    # Each non-MONSTER/VEHICLE model fires either its close-quarters weapons
    # or its other ranged weapons, not both (24.07).
    for unit_model in deployment.models_on_battlefield(game, unit):
        if _big(unit, unit_model):
            continue
        chosen = [w for w in ranged_weapons(unit_model) if w.id in weapon_ids]
        if {close_quarters(w) for w in chosen} == {True, False}:
            raise _bad_request(
                "a model fires either its [CLOSE-QUARTERS] weapons or its other ranged "
                "weapons, not both"
            )
    if any(w.unusable for w in result.weapons if w.id in weapon_ids):
        raise _bad_request("it Advanced: it can only shoot Assault weapons")
    usable = {w.id for w in result.weapons if w.in_range}
    if not weapon_ids <= usable:
        raise _bad_request("one or more of those weapons can't reach the target")
    return result
