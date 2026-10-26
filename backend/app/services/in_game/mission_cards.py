from __future__ import annotations

from collections.abc import Callable, Iterator

from app.services.in_game import actions, battle_shock, regions
from app.services.in_game.mission_context import Context

# Mission cards' scoring lines, in code (see app/data/missions.json for their
# text). Each card is a function of a Context (one scoring moment, for the
# player holding it) yielding the lines it scores then: (text, VP). "Or"
# lines score the best one met; "max" caps a line's VP at that moment.
#
# Actions, operation markers, marked units and the choices made for cards
# come from app/services/in_game/actions.py and mission_state.py. MANUAL
# lists anything a card has that's scored by hand instead (nothing, now).

Lines = Iterator[tuple[str, int]]
Card = Callable[[Context], Lines]

PRIMARIES: dict[str, Card] = {}
SECONDARIES: dict[str, Card] = {}
# Lines of the cards above (and whole cards) that are scored by hand: {card
# name: what}.
MANUAL: dict[str, str] = {}


def primary(name: str, manual: str | None = None):
    def register(card: Card) -> Card:
        PRIMARIES[name] = card
        if manual:
            MANUAL[name] = manual
        return card

    return register


def secondary(name: str):
    def register(card: Card) -> Card:
        SECONDARIES[name] = card
        return card

    return register


# --- lines many cards share ---


def _control_one(ctx: Context, points: int, exclude_homes: bool = False) -> Lines:
    # "You control one or more objectives (excluding your home objective)."
    held = ctx.controlled(exclude_home=not exclude_homes, exclude_homes=exclude_homes)
    if held:
        homes = "home objectives" if exclude_homes else "your home objective"
        yield (f"You control one or more objectives (excluding {homes})", points)


def _control_each(ctx: Context, points: int, exclude_home: bool = True) -> Lines:
    # "For each objective you control (excluding your home objective)."
    held = ctx.controlled(exclude_home=exclude_home)
    if held:
        what = " (excluding your home objective)" if exclude_home else ""
        yield (f"For each objective you control{what} ({len(held)})", points * len(held))


def _more_than_opponent(ctx: Context, points: int) -> Lines:
    if len(ctx.controlled()) > len(ctx.controlled(ctx.opponent)):
        yield ("You control more objectives than your opponent", points)


def _control_opponents_home(ctx: Context, points: int) -> Lines:
    if any(ctx.is_opponents_home(o) for o in ctx.controlled()):
        yield ("You control your opponent's home objective", points)


def _central(ctx: Context, points: int) -> Lines:
    if any(ctx.is_central(o) for o in ctx.controlled()):
        yield ("You control one or more central objectives", points)


def _enemy_destroyed(ctx: Context, points: int) -> Lines:
    if ctx.destroyed_units():
        yield ("One or more enemy units were destroyed this turn", points)


def _each_enemy_destroyed(ctx: Context, points: int, cap: int | None = None) -> Lines:
    count = len(ctx.destroyed_units())
    if count:
        total = points * count
        yield (f"For each enemy unit destroyed this turn ({count})", min(total, cap or total))


def _started_on_objectives_destroyed(ctx: Context) -> list:
    # The enemy units destroyed this turn that started it within range of one
    # or more objectives.
    started = ctx.started_on_objectives()
    return [d for d in ctx.destroyed_units() if started.get(d.unit_id)]


def _more_destroyed_than_previous(ctx: Context, points: int) -> Lines:
    if len(ctx.destroyed_units()) > ctx.friendly_units_destroyed_previous_turn():
        yield (
            "More enemy units were destroyed this turn than friendly units were destroyed "
            "in the previous turn",
            points,
        )


def _newly_controlled(ctx: Context) -> list:
    # Objectives (excluding the holder's home) they control now and didn't at
    # the start of the turn.
    before = ctx.controlled_at_start()
    return [o for o in ctx.controlled(exclude_home=True) if o.id not in before]


_LONE_MARKER = (
    "Only one of {whose} operation markers is on the battlefield, with one or more of your "
    "units within its terrain area and no enemy units"
)


def _lone_marker_held(ctx: Context, seat: int) -> bool:
    # Only one of `seat`'s operation markers is on the battlefield, one or
    # more of the holder's units are within the same terrain area as it, and
    # no enemy units are within that terrain area.
    found = ctx.markers(seat)
    if len(found) != 1:
        return False
    area = ctx.marker_area(found[0])
    return (
        area is not None
        and bool(ctx.units_within_area(ctx.seat, area))
        and not ctx.units_within_area(ctx.opponent, area)
    )


def _unit_objectives(ctx: Context, unit) -> list:
    from app.services.in_game import mission_state

    return mission_state.unit_objectives(ctx.game, unit)


# --- primaries ---


@primary("Death Trap")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        new = [m for m in ctx.markers(source="Booby Trap") if ctx.placed_this_turn(m)]
        if new:
            yield (f"For each terrain area trapped this turn ({len(new)})", 2 * len(new))
            objective_areas = {a.id for o in ctx.objectives() for a in o.areas}
            on = [m for m in new if m.area_id in objective_areas]
            if on:
                yield (f"For each of those that is an objective ({len(on)})", 3 * len(on))
        trapped = {m.area_id for m in ctx.markers(source="Booby Trap")}
        started = ctx.started_in_areas()
        if any(started.get(d.unit_id, set()) & trapped for d in ctx.destroyed_units()):
            yield (
                "One or more enemy units that started the turn within a trapped terrain area "
                "were destroyed",
                3,
            )
    if ctx.command():
        yield from _control_one(ctx, 4)


@primary("Delaying Action")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        yield from _each_enemy_destroyed(ctx, 2)
    if ctx.command():
        yield from _control_one(ctx, 4, exclude_homes=True)
    if ctx.your_turn_end(range(2, 6)):
        held = ctx.controlled()
        if any(ctx.is_central(o) for o in held) and any(ctx.is_expansion(o) for o in held):
            yield ("You control one or more central and one or more expansion objectives", 3)


@primary("Locate and Deny")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        if _started_on_objectives_destroyed(ctx):
            yield (
                "One or more enemy units that started the turn within range of one or more "
                "objectives are destroyed",
                4,
            )
        if _lone_marker_held(ctx, ctx.seat):
            yield (_LONE_MARKER.format(whose="your"), 4)
    if ctx.command():
        yield from _control_one(ctx, 4)
    if ctx.battle_end and _lone_marker_held(ctx, ctx.seat):
        yield (_LONE_MARKER.format(whose="your"), 5)


@primary("Outmanoeuvre")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        yield from _control_opponents_home(ctx, 10)
    if ctx.your_turn_end({1}):
        yield from _control_each(ctx, 4)
    if ctx.command_only({2, 3}):
        yield from _control_each(ctx, 5)
    if ctx.your_turn_end(range(4, 6)):
        yield from _control_each(ctx, 6)


@primary("Smoke and Mirrors")
def _(ctx: Context) -> Lines:
    decoyed = {o for m in ctx.markers(source="Decoy") for o in ctx.marker_objectives(m)}
    if ctx.your_turn_end() and decoyed:
        yield (f"For each objective that is decoyed ({len(decoyed)})", 2 * len(decoyed))
        theirs = [o for o in decoyed if ctx.in_opponents_territory(ctx.objective(o))]
        if theirs:
            yield (
                f"For each of those within your opponent's territory ({len(theirs)})",
                2 * len(theirs),
            )
    if ctx.command():
        yield from _control_one(ctx, 4)
    if ctx.battle_end and len(decoyed) >= 4:
        yield ("Four or more objectives are decoyed", 10)


@primary("Extract Relic")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        if ctx.completed_actions("Sensor Sweep"):
            yield ("A friendly unit performed a sensor sweep this turn", 4)
        if _started_on_objectives_destroyed(ctx):
            yield (
                "One or more enemy units that started the turn within range of one or more "
                "objectives are destroyed",
                3,
            )
        if _lone_marker_held(ctx, ctx.opponent):
            yield (_LONE_MARKER.format(whose="your opponent's"), 4)
    if ctx.command():
        yield from _control_one(ctx, 4)
    if ctx.battle_end and _lone_marker_held(ctx, ctx.opponent):
        yield (_LONE_MARKER.format(whose="your opponent's"), 5)


@primary("Sabotage")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        saboteurs = [ctx.unit(a.unit_id) for a in ctx.completed_actions("Sabotage")]
        if saboteurs:
            yield (
                f"For each friendly unit that committed sabotage this turn ({len(saboteurs)})",
                3 * len(saboteurs),
            )
            theirs = [o for o in ctx.objectives() if ctx.in_opponents_territory(o)]
            deep = [
                u
                for u in saboteurs
                if any(o in theirs for o in _unit_objectives(ctx, u))
            ]
            if deep:
                yield (
                    f"For each of those within range of objectives in your opponent's "
                    f"territory ({len(deep)})",
                    2 * len(deep),
                )
    if ctx.command():
        yield from _control_one(ctx, 4)


@primary("Secure Asset")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        if ctx.completed_actions("Secure Asset"):
            yield ("A friendly unit secured the asset this turn", 4)
        started = ctx.started_on_objectives()
        central = {o.id for o in ctx.objectives() if ctx.is_central(o)}
        if any(started.get(d.unit_id, set()) & central for d in ctx.destroyed_units()):
            yield (
                "One or more enemy units that started the turn within range of one or more "
                "central objectives are destroyed",
                2,
            )
    if ctx.command():
        yield from _control_one(ctx, 4)
        if len(ctx.controlled()) >= 3:
            yield ("You control three or more objectives", 4)


@primary("Vanguard Operation")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        if ctx.completed_actions("Vanguard Operation"):
            yield ("A friendly unit performed a vanguard operation this turn", 4)
        yield from _enemy_destroyed(ctx, 2)
    if ctx.command():
        yield from _control_one(ctx, 4)
    if ctx.battle_end:
        yield from _control_opponents_home(ctx, 10)


@primary("Vital Link")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        central = [o for o in ctx.controlled() if ctx.is_central(o)]
        if central:
            yield ("You control one or more central objectives", 2)
            ids = {o.id for o in central}
            near = [m for m in ctx.markers() if ctx.marker_objectives(m) & ids]
            if near:
                yield (
                    f"For each of your operation markers within range of one of those "
                    f"objectives ({len(near)})",
                    len(near),
                )
    if ctx.command():
        yield from _control_one(ctx, 4)
        if any(ctx.is_central(o) for o in ctx.controlled(exclude_home=True)):
            yield ("One or more of those objectives is a central objective", 4)
    if ctx.battle_end:
        yield from _control_opponents_home(ctx, 10)


@primary("Consecrate")
def _(ctx: Context) -> Lines:
    consecrated = {o for m in ctx.markers(source="Consecrate") for o in ctx.marker_objectives(m)}
    if ctx.your_turn_end():
        if len(consecrated) >= 3:
            yield ("Three or more objectives are consecrated", 6)
        elif consecrated:
            yield ("One or two objectives are consecrated", 3)
    if ctx.command():
        yield from _control_one(ctx, 4)
        yield from _more_than_opponent(ctx, 4)
    if ctx.battle_end and any(ctx.is_opponents_home(ctx.objective(o)) for o in consecrated):
        yield ("Your opponent's home objective is consecrated", 5)


@primary("Destroyer's Wrath")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        yield from _enemy_destroyed(ctx, 3)
    if ctx.command():
        yield from _control_one(ctx, 4)
        yield from _more_than_opponent(ctx, 6)
    if ctx.your_turn_end(range(2, 6)):
        yield from _more_destroyed_than_previous(ctx, 4)


@primary("Meatgrinder")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        yield from _enemy_destroyed(ctx, 3)
    if ctx.command():
        yield from _control_one(ctx, 4)
    if ctx.your_turn_end(range(2, 6)):
        yield from _more_destroyed_than_previous(ctx, 5)
        yield from _control_opponents_home(ctx, 5)


@primary("Punishment")
def _(ctx: Context) -> Lines:
    if ctx.any_turn_end():
        condemned = {m.unit_id for m in ctx.marked("condemned")}
        if any(d.unit_id in condemned for d in ctx.destroyed_units()):
            yield ("One or more condemned enemy units left the battlefield this turn", 5)
    if ctx.command():
        yield from _control_one(ctx, 4)
        yield from _more_than_opponent(ctx, 5)
    if ctx.battle_end:
        yield from _control_opponents_home(ctx, 8)


@primary("Unstoppable Force")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        yield from _enemy_destroyed(ctx, 3)
    if ctx.command():
        yield from _control_each(ctx, 4)
    if ctx.your_turn_end(range(2, 6)) and _newly_controlled(ctx):
        yield (
            "You control one or more objectives you did not control at the start of the "
            "turn (excluding your home objective)",
            3,
        )
    if ctx.battle_end:
        yield from _central(ctx, 5)


@primary("Gather Intel")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end({1}):
        yield from _central(ctx, 6)
    if ctx.command():
        yield from _control_one(ctx, 4)
    if ctx.your_turn_end(range(2, 6)):
        done = ctx.completed_actions("Extract Intelligence")
        if done:
            yield (
                f"For each friendly unit that completed Extract Intelligence this turn "
                f"({len(done)})",
                7 * len(done),
            )
    if ctx.battle_end:
        mine = ctx.markers()
        if len(mine) >= 3:
            yield ("Three or more of your operation markers are on the battlefield", 5)
        if any(
            ctx.is_opponents_home(ctx.objective(o)) for m in mine for o in ctx.marker_objectives(m)
        ):
            yield (
                "One of your operation markers is within range of your opponent's home objective",
                5,
            )


@primary("Reconnaissance Sweep")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        quarters = {
            q
            for unit in ctx.units()
            if not regions.unit_within_distance_of_point(ctx.game, unit, regions.CENTRE, 6)
            and (q := regions.unit_quarter(ctx.game, unit)) is not None
        }
        if len(quarters) >= 4:
            yield ("Four friendly units are wholly within four different table quarters", 6)
        elif len(quarters) >= 3:
            yield ("Three friendly units are wholly within three different table quarters", 3)
        yield from _each_enemy_destroyed(ctx, 1)
    if ctx.command():
        yield from _control_one(ctx, 3)


@primary("Search and Scour")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        yield from _central(ctx, 3)
        started = ctx.started_in_areas()
        if any(started.get(d.unit_id) for d in ctx.destroyed_units()):
            yield (
                "One or more enemy units that started the turn within a terrain area are "
                "destroyed",
                2,
            )
    if ctx.command():
        yield from _control_each(ctx, 4)
    if ctx.battle_end:
        territory = regions.territory(ctx.game, ctx.seat)
        if not any(
            regions.unit_wholly_within(ctx.game, u, territory)
            for u in ctx.units(ctx.opponent, scoring=False)
        ):
            yield ("No enemy units are wholly within your territory", 5)


@primary("Surveil the Foe")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        marked_objectives = {
            o for m in ctx.markers() + ctx.markers(ctx.opponent) for o in ctx.marker_objectives(m)
        }
        surveilled = [ctx.unit(m.unit_id) for m in ctx.marked("surveilled")]
        exposed = [
            u
            for u in surveilled
            if not any(o.id in marked_objectives for o in _unit_objectives(ctx, u))
        ]
        if exposed:
            yield ("One or more enemy units were surveilled this turn", 4)
    if ctx.command():
        yield from _control_one(ctx, 4)
        yield from _more_than_opponent(ctx, 4)
    if ctx.your_turn_end(range(2, 6)) and not ctx.markers(ctx.opponent):
        yield ("None of your opponent's operation markers are on the battlefield", 5)


@primary("Triangulation")
def _(ctx: Context) -> Lines:
    if ctx.command():
        yield from _control_one(ctx, 4)
    if ctx.your_turn_end(range(2, 6)):
        count = len(
            {o for m in ctx.markers(source="Triangulate") for o in ctx.marker_objectives(m)}
        )
        if count >= 3:
            yield ("Three or more objectives are triangulated", 10)
        elif count == 2:
            yield ("Two objectives are triangulated", 6)
        elif count == 1:
            yield ("One objective is triangulated", 3)
    if ctx.battle_end and len(ctx.controlled()) >= 4:
        yield ("You control four or more objectives", 10)


@primary("Battlefield Dominance")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end({1, 2}):
        yield from _more_than_opponent(ctx, 2)
    if ctx.command():
        yield from _control_each(ctx, 3, exclude_home=False)
        others = ctx.controlled(exclude_home=True)
        if others and any(ctx.is_home(o) for o in ctx.controlled()):
            yield (
                f"For each of those (excluding your home) while you control your home "
                f"objective ({len(others)})",
                2 * len(others),
            )


@primary("Determined Acquisition")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        new = _newly_controlled(ctx)
        if new:
            yield (
                f"For each objective you control that you did not control at the start of "
                f"the turn ({len(new)})",
                2 * len(new),
            )
    if ctx.command():
        yield from _control_each(ctx, 3, exclude_home=False)
        theirs = [o for o in ctx.controlled() if ctx.in_opponents_territory(o)]
        if theirs:
            yield (
                f"For each of those within your opponent's territory ({len(theirs)})",
                3 * len(theirs),
            )


@primary("Immovable Object")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        yield from _central(ctx, 3)
    if ctx.command_only({2, 3, 4}):
        yield from _control_each(ctx, 5)
    if ctx.your_turn_end({5}):
        yield from _control_each(ctx, 5)


@primary("Inescapable Dominion")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end() and len(ctx.controlled()) >= 3:
        yield ("You control three or more objectives", 4)
    if ctx.command():
        if len(ctx.controlled()) >= 2:
            yield ("You control two or more objectives", 5)
        yield from _more_than_opponent(ctx, 4)
    if ctx.battle_end:
        yield from _control_opponents_home(ctx, 5)


@primary("Purge and Secure")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end():
        by_holders_on_objectives = [
            d
            for d in ctx.destroyed_units()
            if d.destroyed_by_unit_id
            and ctx._owner(d.destroyed_by_unit_id) == ctx.seat
            and d.on_objective is not None
        ]
        if by_holders_on_objectives:
            yield (
                "One or more enemy units were destroyed this turn by a friendly unit within "
                "range of one or more objectives",
                3,
            )
        elif _started_on_objectives_destroyed(ctx):
            yield (
                "One or more enemy units that started the turn within range of one or more "
                "objectives were destroyed this turn",
                3,
            )
    if ctx.command():
        yield from _control_each(ctx, 4)
    if ctx.your_turn_end(range(2, 6)) and _newly_controlled(ctx):
        yield (
            "You control one or more objectives you did not control at the start of the "
            "turn (excluding your home objective)",
            3,
        )


# --- secondaries ---


@secondary("A Grievous Blow")
def _(ctx: Context) -> Lines:
    if not ctx.any_turn_end():
        return
    big = [
        d
        for d in ctx.destroyed_units()
        if battle_shock.starting_strength(ctx.unit(d.unit_id)) >= 13
    ]
    if not big:
        return
    if ctx.mode == "fixed":
        yield (
            f"For each enemy unit with a starting strength of 13+ destroyed ({len(big)})",
            4 * len(big),
        )
    else:
        yield ("One or more enemy units with a starting strength of 13+ were destroyed", 5)


@secondary("Assassination")
def _(ctx: Context) -> Lines:
    if not ctx.any_turn_end():
        return
    characters = [
        d
        for d in ctx.destroyed_models()
        if "CHARACTER" in {k.name for k in ctx.unit_model(d.unit_model_id).model.keywords}
    ]
    if ctx.mode == "fixed":
        if characters:
            yield (
                f"For each enemy CHARACTER model destroyed ({len(characters)})",
                3 * len(characters),
            )
            tough = [d for d in characters if ctx.unit_model(d.unit_model_id).wounds >= 4]
            if tough:
                yield (f"For each of those with W 4+ ({len(tough)})", len(tough))
        return
    all_characters = [
        m
        for u in ctx.army(ctx.opponent)
        for m in u.unit_models
        if "CHARACTER" in {k.name for k in m.model.keywords}
    ]
    if characters:
        yield ("One or more enemy CHARACTER models were destroyed this turn", 5)
    elif all_characters and all(
        m.id in {d.unit_model_id for d in ctx.game.models_destroyed} for m in all_characters
    ):
        yield ("All enemy CHARACTER models have been destroyed during the battle", 5)


@secondary("Behind Enemy Lines")
def _(ctx: Context) -> Lines:
    if not ctx.your_turn_end():
        return
    zone = regions.deployment_zone(ctx.game, ctx.opponent)
    inside = [u for u in ctx.units() if regions.unit_wholly_within(ctx.game, u, zone)]
    if inside:
        yield (
            f"For each friendly unit wholly within your opponent's deployment zone "
            f"({len(inside)}, max 5VP)",
            min(5, 3 * len(inside)),
        )


@secondary("Bring It Down")
def _(ctx: Context) -> Lines:
    if not ctx.any_turn_end():
        return
    big = [
        d for d in ctx.destroyed_models() if ctx.unit_model(d.unit_model_id).wounds >= 10
    ]
    if not big:
        return
    if ctx.mode == "fixed":
        yield (f"For each enemy model with W 10+ destroyed ({len(big)})", 4 * len(big))
    else:
        yield ("One or more enemy models with W 10+ were destroyed", 5)


@secondary("Centre Ground")
def _(ctx: Context) -> Lines:
    if not ctx.your_turn_end():
        return
    game, centre = ctx.game, regions.CENTRE
    if not any(regions.unit_within_distance_of_point(game, u, centre, 3) for u in ctx.units()):
        return
    enemies = ctx.units(ctx.opponent, scoring=False)
    if not any(regions.unit_within_distance_of_point(game, u, centre, 6) for u in enemies):
        yield ("Friendly units within 3\" of the centre, and no enemy units within 6\"", 5)
    elif not any(regions.unit_within_distance_of_point(game, u, centre, 3) for u in enemies):
        yield ("Friendly units within 3\" of the centre, and no enemy units within 3\"", 3)


@secondary("Defend Stronghold")
def _(ctx: Context) -> Lines:
    if not ctx.opponent_turn_or_fifth_round_end(range(2, 6)):
        return
    if any(ctx.is_home(o) for o in ctx.controlled()):
        yield ("You control your home objective", 3)
    zone = regions.deployment_zone(ctx.game, ctx.seat)
    if not any(
        regions.unit_within(ctx.game, u, zone) for u in ctx.units(ctx.opponent, scoring=False)
    ):
        yield ("No enemy units are within your deployment zone", 2)


def _more_in_no_mans_land(ctx: Context) -> bool:
    def count(seat: int) -> int:
        return sum(
            1 for u in ctx.units(seat) if regions.unit_wholly_within_no_mans_land(ctx.game, u)
        )

    return count(ctx.seat) > count(ctx.opponent)


@secondary("Display of Might")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end() and _more_in_no_mans_land(ctx):
        yield ("More friendly units than enemy units wholly within No Man's Land", 2)
    if ctx.opponent_turn_end() and _more_in_no_mans_land(ctx):
        yield ("More friendly units than enemy units wholly within No Man's Land", 5)


@secondary("Engage on All Fronts")
def _(ctx: Context) -> Lines:
    if not ctx.your_turn_end():
        return
    quarters = {
        q
        for u in ctx.units()
        if not regions.unit_within_distance_of_point(ctx.game, u, regions.CENTRE, 6)
        and (q := regions.unit_quarter(ctx.game, u)) is not None
    }
    fixed = ctx.mode == "fixed"
    if len(quarters) >= 4:
        yield ("You have a presence in four table quarters", 4 if fixed else 5)
    elif len(quarters) == 3:
        yield ("You have a presence in three table quarters", 2 if fixed else 3)


@secondary("Forward Position")
def _(ctx: Context) -> Lines:
    if not ctx.your_turn_end():
        return
    held = ctx.controlled()
    expansions = [o for o in ctx.objectives() if ctx.is_expansion(o)]
    if any(ctx.is_opponents_home(o) for o in held) or (
        expansions and all(o in held for o in expansions)
    ):
        yield ("You control your opponent's home objective and/or each expansion objective", 5)


@secondary("No Prisoners")
def _(ctx: Context) -> Lines:
    if ctx.any_turn_end():
        yield from _each_enemy_destroyed(ctx, 2, cap=5)


@secondary("Outflank")
def _(ctx: Context) -> Lines:
    if not ctx.your_turn_end():
        return
    territory = regions.territory(ctx.game, ctx.seat)
    near = [(u, regions.unit_edges_within(ctx.game, u, 6)) for u in ctx.units()]
    near = [(u, edges) for u, edges in near if edges]
    outside = [
        (u, edges) for u, edges in near if not regions.unit_wholly_within(ctx.game, u, territory)
    ]
    for u, edges in outside:
        for v, other_edges in near:
            if v.id != u.id and {regions.OPPOSITE[e] for e in edges} & other_edges:
                yield ("Two friendly units within 6\" of opposite battlefield edges", 5)
                return
    if outside:
        yield ("A friendly unit within 6\" of a battlefield edge, not within your territory", 3)


@secondary("Overwhelming Force")
def _(ctx: Context) -> Lines:
    if not ctx.any_turn_end():
        return
    started = _started_on_objectives_destroyed(ctx)
    if started:
        yield (
            f"For each enemy unit that started the turn within range of objectives and is "
            f"destroyed ({len(started)}, max 5VP)",
            min(5, 3 * len(started)),
        )


@secondary("Secure No Man's Land")
def _(ctx: Context) -> Lines:
    if not ctx.your_turn_end():
        return
    held = [o for o in ctx.controlled(exclude_home=True) if ctx.in_no_mans_land(o)]
    if len(held) >= 2:
        yield ("You control two or more objectives within No Man's Land", 5)


@secondary("Cleanse")
def _(ctx: Context) -> Lines:
    if not ctx.your_turn_end():
        return
    cleansed = {
        a.objective_id
        for a in actions.completed(ctx.game, ctx.seat, "Cleanse", ctx.battle_round, ctx.turn_seat)
    }
    if len(cleansed) >= 2:
        yield ("Two or more objectives were cleansed by your army this turn", 5)
    elif cleansed:
        yield ("One objective was cleansed by your army this turn", 2)


@secondary("Plunder")
def _(ctx: Context) -> Lines:
    if ctx.your_turn_end() and actions.completed(
        ctx.game, ctx.seat, "Plunder", ctx.battle_round, ctx.turn_seat
    ):
        yield ("A terrain area was plundered this turn", 5)


@secondary("Beacon")
def _(ctx: Context) -> Lines:
    if not ctx.opponent_turn_or_fifth_round_end():
        return
    from app.services.in_game import mission_state

    choices = mission_state.card_choices(ctx.game, ctx.seat, "Beacon", "beacon")
    if not choices:
        return
    unit = ctx.unit(choices[0].unit_id)
    if unit not in ctx.units(ctx.seat, scoring=False):
        return
    if not regions.unit_within(ctx.game, unit, regions.territory(ctx.game, ctx.seat)):
        yield ("Your beacon unit is on the battlefield and not within your territory", 5)
    elif not regions.unit_within(ctx.game, unit, regions.deployment_zone(ctx.game, ctx.seat)):
        yield ("Your beacon unit is on the battlefield and not within your deployment zone", 3)


@secondary("Burden of Trust")
def _(ctx: Context) -> Lines:
    if not ctx.opponent_turn_or_fifth_round_end():
        return
    from app.services.in_game import mission_state

    # Guarded: its guard is within range of it, and the holder controls it.
    held = {o.id for o in ctx.controlled()}
    on_battlefield = {u.id for u in ctx.units(ctx.seat, scoring=False)}
    guarded = set()
    for c in mission_state.card_choices(ctx.game, ctx.seat, "Burden of Trust", "guard"):
        if c.objective_id not in held or c.unit_id not in on_battlefield:
            continue
        within = mission_state.unit_objectives(ctx.game, ctx.unit(c.unit_id))
        if any(o.id == c.objective_id for o in within):
            guarded.add(c.objective_id)
    if guarded:
        yield (
            f"For each objective guarded by your army ({len(guarded)}, max 5VP)",
            min(5, 2 * len(guarded)),
        )


@secondary("A Tempting Target")
def _(ctx: Context) -> Lines:
    if not ctx.your_turn_end():
        return
    from app.services.in_game import mission_state

    choices = mission_state.card_choices(
        ctx.game, ctx.seat, "A Tempting Target", "tempting_target"
    )
    if choices and choices[0].objective_id in {o.id for o in ctx.controlled()}:
        yield ("You control your tempting target", 5)
