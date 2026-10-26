from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException

from app.models import (
    Game,
    GameCardChoice,
    GameMarkedUnit,
    GameMissionPrompt,
    GameOperationMarker,
    Unit,
)
from app.services.in_game import deployment, regions
from app.services.in_game.terrain import area_polygon

# What primary missions keep track of on the battlefield (see
# app/services/in_game/mission_cards.py for how they score it):
#
# - Operation markers: each player's, within range of an objective or
#   within a terrain area - placed by actions (Decoy, Maintain Control...),
#   at the start of the battle (Locate and Deny) or by consecration; removed
#   by sensor sweeps, or by an enemy unit ending a move on their objective
#   (Surveil the Foe).
# - Marked units: condemned (Punishment), surveilled (Surveil the Foe),
#   consecration units (Consecrate).
# - Prompts: choices those missions need from a player at their moment -
#   the game waits until they're made. Secondary cards with a choice when
#   drawn (in the Command phase) prompt for it then: Beacon's unit and Burden
#   of Trust's guards (its holder - Burden of Trust again at the start of
#   each of their turns), A Tempting Target's objective (their opponent);
#   the choices are kept per card (GameCardChoice). Cards with a WHEN DRAWN
#   option to redraw prompt for that too (see `may_redraw`).

LOCATE_AND_DENY = "Locate and Deny"
CONSECRATE = "Consecrate"
PUNISHMENT = "Punishment"
SURVEIL_THE_FOE = "Surveil the Foe"
BEACON = "Beacon"
BURDEN_OF_TRUST = "Burden of Trust"
TEMPTING_TARGET = "A Tempting Target"
# WHEN DRAWN: cards that can be discarded and a new one drawn (if there's
# nothing for them to target); cards that can be shuffled back and a new one
# drawn in the first battle round; cards that can be if the other is held.
REDRAW_DISCARD = {"A Grievous Blow", "Bring It Down"}
REDRAW_FIRST_ROUND = {"Behind Enemy Lines", "Forward Position"}
REDRAW_IF_HOLDING = {"Cleanse": "Plunder", "Plunder": "Cleanse"}
BIG_UNIT = 13
BIG_MODEL_WOUNDS = 10
LOCATE_AND_DENY_MARKERS = 5
MAX_CONDEMNED = 3


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _when(game: Game) -> dict:
    return {"battle_round": game.battle_round, "turn_seat": game.turn_seat}


def has_primary(game: Game, seat: int, name: str) -> bool:
    player = next(p for p in game.players if p.seat == seat)
    return player.primary_mission is not None and player.primary_mission.name == name


def _other(game: Game, seat: int) -> int:
    return next(p.seat for p in game.players if p.seat != seat)


# --- operation markers ---


def markers(game: Game, seat: int | None = None) -> list[GameOperationMarker]:
    # The operation markers on the battlefield (one player's, if `seat`).
    return [
        m
        for m in game.operation_markers
        if m.removed_round is None and (seat is None or m.seat == seat)
    ]


def place_marker(
    game: Game,
    seat: int,
    source: str,
    objective_id: int | None = None,
    area_id: int | None = None,
) -> GameOperationMarker:
    marker = GameOperationMarker(
        seat=seat,
        source=source,
        objective_id=objective_id,
        area_id=area_id,
        placed_round=game.battle_round,
        placed_turn_seat=game.turn_seat,
    )
    game.operation_markers.append(marker)
    return marker


def remove_marker(game: Game, marker: GameOperationMarker) -> None:
    marker.removed_round = game.battle_round
    marker.removed_turn_seat = game.turn_seat


def marker_objectives(game: Game, marker: GameOperationMarker) -> set[int]:
    # The objectives a marker is within range of: the one it was placed on,
    # or those whose terrain areas include the area it's in.
    if marker.objective_id is not None:
        return {marker.objective_id}
    layout = game.layout
    if layout is None or marker.area_id is None:
        return set()
    return {o.id for o in layout.objectives if marker.area_id in {a.id for a in o.areas}}


def marker_area(game: Game, marker: GameOperationMarker) -> int | None:
    # The terrain area a marker is within: the one it was placed in, or its
    # objective's (the first, for an objective of two).
    if marker.area_id is not None:
        return marker.area_id
    objective = next(o for o in game.layout.objectives if o.id == marker.objective_id)
    return objective.areas[0].id if objective.areas else None


def objectives_with_markers(game: Game, seat: int | None = None, source: str | None = None):
    # The objectives with operation markers within range (one player's; from
    # one source).
    return {
        objective_id
        for m in markers(game, seat)
        if source is None or m.source == source
        for objective_id in marker_objectives(game, m)
    }


# --- marked units ---


def marked(game: Game, kind: str, seat: int | None = None) -> list[GameMarkedUnit]:
    # The units marked `kind` now (by `seat`'s mission). Surveilled units are
    # only this turn's.
    found = [
        m
        for m in game.marked_units
        if m.kind == kind and not m.ended and (seat is None or m.seat == seat)
    ]
    if kind == "surveilled":
        found = [
            m
            for m in found
            if m.battle_round == game.battle_round and m.turn_seat == game.turn_seat
        ]
    return found


def mark(game: Game, seat: int, kind: str, unit_id: int) -> None:
    game.marked_units.append(GameMarkedUnit(**_when(game), seat=seat, kind=kind, unit_id=unit_id))


def unit_destroyed_by(game: Game, destroyer: Unit | None) -> None:
    # A unit destroyed an enemy unit: for Consecrate, it becomes a
    # consecration unit (if it isn't already).
    if destroyer is None:
        return
    seat = deployment.owner(game, destroyer).seat
    if not has_primary(game, seat, CONSECRATE):
        return
    if any(m.unit_id == destroyer.id for m in marked(game, "consecration", seat)):
        return
    mark(game, seat, "consecration", destroyer.id)


# --- where units are ---


def _within_objective(game: Game, unit: Unit, objective) -> bool:
    return any(regions.unit_within(game, unit, area_polygon(a)) for a in objective.areas)


def unit_objectives(game: Game, unit: Unit) -> list:
    # The objectives the unit is within range of.
    layout = game.layout
    return [o for o in (layout.objectives if layout else []) if _within_objective(game, unit, o)]


def unit_areas(game: Game, unit: Unit) -> list:
    layout = game.layout
    return [
        a
        for a in (layout.areas if layout else [])
        if regions.unit_within(game, unit, area_polygon(a))
    ]


def area_within(game: Game, area, polygon) -> bool:
    # Whether any part of a terrain area is within a region (its corners -
    # areas and regions are convex, or nearly).
    return polygon is not None and any(regions.point_in(p, polygon) for p in area_polygon(area))


def after_move(game: Game, unit: Unit) -> None:
    # A unit ended a move: its opponent's Teleport Homer tokens within 1" are
    # removed (see app/services/in_game/teleport_homer.py); actions waiting to complete whose unit is now
    # within Engagement Range fail (see app/services/in_game/actions.py); and
    # for Surveil the Foe, if it's within range of an objective with any of
    # its opponent's operation markers within range, those markers are
    # removed.
    # (Imported here: actions imports this module.)
    from app.services.in_game import actions, teleport_homer

    actions.check_started(game)
    teleport_homer.after_move(game, unit)
    seat = deployment.owner(game, unit).seat
    if not has_primary(game, seat, SURVEIL_THE_FOE):
        return
    on = {o.id for o in unit_objectives(game, unit)}
    for marker in markers(game, _other(game, seat)):
        if marker_objectives(game, marker) & on:
            remove_marker(game, marker)


# --- prompts ---


def pending(game: Game) -> list[GameMissionPrompt]:
    return [p for p in game.mission_prompts if not p.answered]


def _prompt(game: Game, seat: int, kind: str, action_id: int | None = None) -> None:
    game.mission_prompts.append(
        GameMissionPrompt(**_when(game), seat=seat, kind=kind, action_id=action_id)
    )


def _prompted(game: Game, seat: int, kind: str) -> bool:
    return any(
        p.seat == seat
        and p.kind == kind
        and p.battle_round == game.battle_round
        and p.turn_seat == game.turn_seat
        for p in game.mission_prompts
    )


def start_of_battle(game: Game) -> None:
    # Locate and Deny: its player places their operation markers.
    for player in game.players:
        if has_primary(game, player.seat, LOCATE_AND_DENY) and not _prompted(
            game, player.seat, "place_markers"
        ):
            _prompt(game, player.seat, "place_markers")


def start_of_turn(game: Game) -> None:
    # Punishment: the player whose turn it is condemns enemy units anew.
    seat = game.turn_seat
    if not has_primary(game, seat, PUNISHMENT) or _prompted(game, seat, "condemn"):
        return
    for record in marked(game, "condemned", seat):
        record.ended = True
    if condemn_options(game, seat)[0]:
        _prompt(game, seat, "condemn")


def end_of_turn(game: Game) -> None:
    # Consecrate: the player whose turn it is can consecrate objectives with
    # their consecration units.
    seat = game.turn_seat
    if (
        has_primary(game, seat, CONSECRATE)
        and not _prompted(game, seat, "consecrate")
        and any(consecrate_options(game, seat).values())
    ):
        _prompt(game, seat, "consecrate")


def prompt_sensor_sweep(game: Game, seat: int, action_id: int) -> None:
    # A sensor sweep completed: its player removes an operation marker.
    if markers(game):
        _prompt(game, seat, "remove_marker", action_id)


# --- secondary cards' choices when drawn ---


def active_card(game: Game, seat: int, name: str):
    # The player's active secondary card of that name, if they hold it.
    player = next(p for p in game.players if p.seat == seat)
    return next(
        (c for c in player.secondaries if c.status == "active" and c.mission.name == name), None
    )


def card_choices(game: Game, seat: int, name: str, kind: str) -> list[GameCardChoice]:
    # The choices made for the player's active card of that name.
    card = active_card(game, seat, name)
    if card is None:
        return []
    return [c for c in game.card_choices if c.game_secondary_id == card.id and c.kind == kind]


def may_redraw(game: Game, seat: int, card) -> str | None:
    # How the player can redraw a card they've just drawn, if they can:
    # "discard" (A Grievous Blow with no enemy unit of starting strength 13+
    # on the battlefield; Bring It Down with no enemy model of W 10+) or
    # "shuffle" back (Behind Enemy Lines and Forward Position in the first
    # battle round; Cleanse while holding Plunder, and Plunder while holding
    # Cleanse).
    from app.services.in_game import battle_shock

    name = card.mission.name
    enemy = beacon_options(game, _other(game, seat))
    if name == "A Grievous Blow":
        if not any(battle_shock.starting_strength(u) >= BIG_UNIT for u in enemy):
            return "discard"
    elif name == "Bring It Down":
        placed = deployment.positions(game)
        big = [
            m for u in enemy for m in u.unit_models
            if m.id in placed and m.wounds >= BIG_MODEL_WOUNDS
        ]
        if not big:
            return "discard"
    elif name in REDRAW_FIRST_ROUND:
        if game.battle_round == 1:
            return "shuffle"
    elif name in REDRAW_IF_HOLDING:
        if active_card(game, seat, REDRAW_IF_HOLDING[name]):
            return "shuffle"
    return None


def redraw_offers(game: Game, seat: int) -> dict[int, str]:
    # The player's cards they can redraw now: {card id: "discard" or
    # "shuffle"}.
    player = next(p for p in game.players if p.seat == seat)
    active = {c.id: c for c in player.secondaries if c.status == "active"}
    return {
        c.game_secondary_id: "discard"
        if active[c.game_secondary_id].mission.name in REDRAW_DISCARD
        else "shuffle"
        for c in game.card_choices
        if c.kind == "redraw_offer" and c.game_secondary_id in active
    }


def close_redraw(game: Game, prompt) -> None:
    # The player's decided which cards to redraw: their offers are done.
    offered = redraw_offers(game, prompt.seat)
    for choice in [
        c for c in game.card_choices if c.kind == "redraw_offer" and c.game_secondary_id in offered
    ]:
        game.card_choices.remove(choice)
    prompt.answered = True


def lapse_stale_prompts(game: Game) -> None:
    # Choices for cards no longer held (redrawn) lapse.
    for other in pending(game):
        holder = _other(game, other.seat) if other.kind == "tempting_target" else other.seat
        card = {"beacon": BEACON, "guards": BURDEN_OF_TRUST, "tempting_target": TEMPTING_TARGET}
        if other.kind in card and active_card(game, holder, card[other.kind]) is None:
            other.answered = True


def cards_drawn(game: Game, seat: int, drawn=()) -> None:
    # The player has drawn their secondary cards (in a Command phase): the
    # choices their cards need now - whether to redraw those just drawn that
    # can be (see `may_redraw`), and what their cards select when drawn.
    other = _other(game, seat)
    redrawable = [c for c in drawn if may_redraw(game, seat, c)]
    for card in redrawable:
        _choose(game, card, "redraw_offer")
    if redrawable and not any(p.kind == "redraw" and p.seat == seat for p in pending(game)):
        _prompt(game, seat, "redraw")
    if (
        active_card(game, seat, BEACON)
        and not card_choices(game, seat, BEACON, "beacon")
        and not _prompted(game, seat, "beacon")
        and beacon_candidates(game, seat)
    ):
        _prompt(game, seat, "beacon")
    burden = active_card(game, seat, BURDEN_OF_TRUST)
    if burden and not _prompted(game, seat, "guards"):
        # The last ones guarded until now.
        for choice in [c for c in game.card_choices if c.game_secondary_id == burden.id]:
            game.card_choices.remove(choice)
        if beacon_options(game, seat):
            _prompt(game, seat, "guards")
    if (
        active_card(game, seat, TEMPTING_TARGET)
        and not card_choices(game, seat, TEMPTING_TARGET, "tempting_target")
        and not _prompted(game, other, "tempting_target")
        and tempting_options(game, seat)
    ):
        _prompt(game, other, "tempting_target")


def beacon_options(game: Game, seat: int) -> list[Unit]:
    # The player's units on the battlefield (for Beacon, and to guard
    # objectives for Burden of Trust).
    player = next(p for p in game.players if p.seat == seat)
    placed = deployment.positions(game)
    return [u for u in deployment.deployable_units(player) if deployment.is_deployed(u, placed)]


def beacon_candidates(game: Game, seat: int) -> list[Unit]:
    # What can be a Beacon unit: one of the player's units on the
    # battlefield, or embarked in a transport that's on it.
    from app.services.in_game import embarked

    return beacon_options(game, seat) + [u for u, _ in embarked.embarked_units(game, seat)]


def tempting_options(game: Game, holder: int) -> list:
    # The objectives that could be the holder's tempting target: not a home
    # objective, and within No Man's Land.
    from app.services.in_game import objectives

    layout = game.layout
    return [
        o
        for o in (layout.objectives if layout else [])
        if o.kind not in objectives.HOME_KINDS.values()
        and regions.point_in_no_mans_land(game, (o.x, o.y))
    ]


def _choose(game: Game, card, kind: str, unit_id=None, objective_id=None) -> None:
    game.card_choices.append(
        GameCardChoice(
            **_when(game),
            game_secondary_id=card.id,
            kind=kind,
            unit_id=unit_id,
            objective_id=objective_id,
        )
    )


# --- each prompt's options ---


def place_marker_options(game: Game, seat: int) -> tuple[list, int]:
    # Locate and Deny: the terrain areas not within the player's deployment
    # zone, and how many to pick (five, or all of them if there are fewer).
    zone = regions.deployment_zone(game, seat)
    layout = game.layout
    areas = [a for a in (layout.areas if layout else []) if not area_within(game, a, zone)]
    return areas, min(LOCATE_AND_DENY_MARKERS, len(areas))


def consecrate_options(game: Game, seat: int) -> dict[int, list]:
    # Each consecration unit's objectives it could consecrate: within range
    # of it, not the player's home objective, and not consecrated yet.
    from app.services.in_game import objectives

    consecrated = objectives_with_markers(game, seat, CONSECRATE)
    found = {}
    placed = deployment.positions(game)
    for record in marked(game, "consecration", seat):
        unit = deployment.find_unit(game, record.unit_id)
        if not deployment.is_deployed(unit, placed):
            continue
        found[unit.id] = [
            o
            for o in unit_objectives(game, unit)
            if not objectives.is_home(game, o, seat) and o.id not in consecrated
        ]
    return found


def condemn_options(game: Game, seat: int) -> tuple[list[Unit], bool]:
    # Punishment: the enemy units that could be condemned - those within
    # range of objectives and/or that destroyed friendly units last turn -
    # and whether those were found (if not, any one enemy unit will do).
    from app.services.in_game import turn_record

    enemy = next(p for p in game.players if p.seat != seat)
    placed = deployment.positions(game)
    units = [u for u in deployment.deployable_units(enemy) if deployment.is_deployed(u, placed)]
    previous = turn_record.previous_turn(game, game.battle_round, seat)
    killers = set()
    if previous:
        killers = {
            d.destroyed_by_unit_id
            for d in turn_record.units_destroyed(game, *previous)
            if turn_record.owner_seat(game, d.unit_id) == seat
        }
    eligible = [u for u in units if unit_objectives(game, u) or u.id in killers]
    return (eligible, True) if eligible else (units, False)


@dataclass
class Answer:
    area_ids: list[int] = field(default_factory=list)
    unit_ids: list[int] = field(default_factory=list)
    marker_id: int | None = None
    objective_id: int | None = None
    consecrations: dict[int, int] = field(default_factory=dict)  # unit id: objective id
    guards: dict[int, int] = field(default_factory=dict)  # objective id: unit id


def answer(game: Game, prompt_id: int, given: Answer) -> None:
    prompt = next((p for p in pending(game) if p.id == prompt_id), None)
    if prompt is None:
        raise _bad_request("no such choice waiting to be made")
    seat = prompt.seat
    if prompt.kind == "place_markers":
        areas, count = place_marker_options(game, seat)
        ids = {a.id for a in areas}
        picked = list(dict.fromkeys(given.area_ids))
        if len(picked) != count or not set(picked) <= ids:
            raise _bad_request(
                f"pick {count} different terrain areas not within your deployment zone"
            )
        for area_id in picked:
            place_marker(game, seat, LOCATE_AND_DENY, area_id=area_id)
    elif prompt.kind == "consecrate":
        options = consecrate_options(game, seat)
        chosen = set()
        for unit_id, objective_id in given.consecrations.items():
            allowed = {o.id for o in options.get(unit_id, [])}
            if objective_id not in allowed or objective_id in chosen:
                raise _bad_request("that unit can't consecrate that objective")
            chosen.add(objective_id)
        for unit_id, objective_id in given.consecrations.items():
            place_marker(game, seat, CONSECRATE, objective_id=objective_id)
            for record in marked(game, "consecration", seat):
                if record.unit_id == unit_id:
                    record.ended = True
    elif prompt.kind == "condemn":
        units, eligible = condemn_options(game, seat)
        ids = {u.id for u in units}
        picked = list(dict.fromkeys(given.unit_ids))
        most = MAX_CONDEMNED if eligible else 1
        if not 1 <= len(picked) <= most or not set(picked) <= ids:
            what = f"1 to {most} of those enemy units" if eligible else "one enemy unit"
            raise _bad_request(f"condemn {what}")
        for unit_id in picked:
            mark(game, seat, "condemned", unit_id)
    elif prompt.kind == "remove_marker":
        marker = next((m for m in markers(game) if m.id == given.marker_id), None)
        if marker is None:
            raise _bad_request("pick an operation marker on the battlefield")
        remove_marker(game, marker)
    elif prompt.kind == "beacon":
        card = active_card(game, seat, BEACON)
        if card is not None:
            unit_id = given.unit_ids[0] if given.unit_ids else None
            if unit_id not in {u.id for u in beacon_candidates(game, seat)}:
                raise _bad_request(
                    "pick one of your units on the battlefield (or embarked in a transport "
                    "there) as your beacon"
                )
            _choose(game, card, "beacon", unit_id=unit_id)
    elif prompt.kind == "guards":
        card = active_card(game, seat, BURDEN_OF_TRUST)
        if card is not None:
            units = {u.id for u in beacon_options(game, seat)}
            objective_ids = {o.id for o in (game.layout.objectives if game.layout else [])}
            for objective_id, unit_id in given.guards.items():
                if objective_id not in objective_ids or unit_id not in units:
                    raise _bad_request("each guard is one of your units on the battlefield")
            for objective_id, unit_id in given.guards.items():
                _choose(game, card, "guard", unit_id=unit_id, objective_id=objective_id)
    elif prompt.kind == "tempting_target":
        holder = _other(game, seat)
        card = active_card(game, holder, TEMPTING_TARGET)
        if card is not None:
            if given.objective_id not in {o.id for o in tempting_options(game, holder)}:
                raise _bad_request(
                    "pick an objective within No Man's Land (not a home objective)"
                )
            _choose(game, card, "tempting_target", objective_id=given.objective_id)
    prompt.answered = True
