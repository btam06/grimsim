from __future__ import annotations

from fastapi import HTTPException

from app.models import (
    Game,
    GameBattleFormation,
    GameDisembarkation,
    GameModelPosition,
    GameUnitMove,
    GameUnitTransit,
    Unit,
)
from app.services.in_game import deployment, regions
from app.services.in_game.deployment import TOLERANCE, Base, Placement, gap

# Units embarked in transports. A unit declared embarked in one of its
# player's TRANSPORT units at the start of the battle (see
# app/services/in_game/battle_formations.py) starts the battle inside it:
# not on the battlefield, but there while its transport is (e.g. as a
# Beacon unit). In its player's movement phase it can disembark (18.04) -
# unless its transport Advanced or Fell Back this phase - set up (on the
# battlefield, not overlapping, in coherency - as when deploying), not
# engaged, in one of three modes, the first that applies:
# - rapid: its transport made a Normal (or ingress) move this phase - every
#   model wholly within 3" of it (after an ingress move, more than 8" from
#   enemy models, and not in the enemy deployment zone in the first two
#   battle rounds unless it Deep Struck). It can't move again, nor charge
#   this turn.
# - tactical: its transport hasn't moved - wholly within 3"; it can still
#   make a Normal move or Advance.
# - combat: if it can't be set up that way (the player says so) - wholly
#   within 6", engaged only with enemy units its transport is engaged with,
#   and each model makes a hazard roll; the unit is Battle-shocked, and it
#   can't move again, nor charge this turn.
#
# A transport ability can let its units disembark after it Advanced anyway
# (datasheet_abilities SHOCK_DISEMBARK_AFTER - e.g. Rapid Disembarkation): a
# shock disembark move, set up the same way, after which the unit can't
# declare a charge this turn.
#
# A unit can embark during the battle too: in its player's movement phase,
# once it's made a Normal, Advance or Fall Back move that ended with every
# model within 3" of one of their TRANSPORT units' models, it can embark in
# that transport - off the battlefield, as if it had started the battle
# there. A unit can't embark and disembark in the same phase.
#
# A transport whose capacity was entered (Model.transport) can only carry
# models with its keywords, without its excluded ones, up to its capacity -
# some taking up more space than others (e.g. an Impulsor: 7 ADEPTUS ASTARTES
# INFANTRY models, not TERMINATOR or JUMP PACK, each GRAVIS model taking up
# the space of 2). One whose capacity wasn't entered can carry anything.
# (What happens to units inside a destroyed transport: see
# app/services/in_game/emergency.py.)

DISEMBARK_RANGE = 3.0
COMBAT_DISEMBARK_RANGE = 6.0
EMBARK_RANGE = 3.0
RAPID, TACTICAL, COMBAT = "rapid", "tactical", "combat"
ENGAGEMENT_RANGE = 2.0
# The kind of move (see GameUnitMove) disembarking from a transport that's
# moved counts as.
DISEMBARKED = "disembarked"
# The transit (see GameUnitTransit) recorded, as well as "disembarked", for a
# shock disembark move.
SHOCK_DISEMBARKED = "shock_disembarked"
# The transits recorded, as well as "disembarked", for rapid and combat
# disembark moves (both stop the unit charging this turn).
RAPID_DISEMBARKED = "rapid_disembarked"
COMBAT_DISEMBARKED = "combat_disembarked"
NO_CHARGE = (SHOCK_DISEMBARKED, RAPID_DISEMBARKED, COMBAT_DISEMBARKED)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def transport(game: Game, unit: Unit) -> Unit | None:
    # The transport the unit's embarked in, if it is.
    formation = deployment.battle_formation(game, unit)
    if formation is None or formation.place != "embarked" or formation.transport_unit_id is None:
        return None
    return deployment.find_unit(game, formation.transport_unit_id)


def embarked_units(game: Game, seat: int) -> list[tuple[Unit, Unit]]:
    # The player's units embarked in a transport that's on the battlefield:
    # (unit, transport).
    player = next(p for p in game.players if p.seat == seat)
    placed = deployment.positions(game)
    found = []
    for unit in deployment.deployable_units(player):
        carrier = transport(game, unit)
        if carrier is not None and deployment.is_deployed(carrier, placed):
            found.append((unit, carrier))
    return found


def _capacities(carrier: Unit):
    return [m.model.transport for m in carrier.unit_models if m.model.transport is not None]


def _space(capacity, keywords: set[str]) -> int:
    # The space a model with these keywords takes up in the transport.
    return max([v for k, v in capacity.space.items() if k in keywords], default=1)


def capacity_reason(game: Game, unit: Unit, carrier: Unit) -> str | None:
    # Why the unit can't embark in the transport because of what it can carry
    # (its keywords, and the room left after the units already in it), or
    # None if it can.
    from app.services.list_building import enhancements as enhancement_rules

    capacities = _capacities(carrier)
    if not capacities:
        return None
    # (A transport of several models: the first's rules, everyone's room.)
    capacity = capacities[0]
    total = sum(c.capacity for c in capacities)

    def keywords(u: Unit, unit_model) -> set[str]:
        return enhancement_rules.model_keywords(u, unit_model)

    name = carrier.faction_unit.name
    models = surviving_models(game, unit)
    # A model whose ability lets it go wherever its Bodyguard unit can (e.g.
    # Authority of the Inquisition), while it's leading one: its own keywords
    # don't count.
    from app.seeds import datasheet_abilities
    from app.services.in_game import shooting

    as_bodyguard = datasheet_abilities.TRANSPORT_AS_BODYGUARD
    for unit_model in models:
        if shooting.leading(unit) and {a.name for a in unit_model.model.abilities} & as_bodyguard:
            continue
        held = keywords(unit, unit_model)
        missing = [k for k in capacity.keywords if k not in held]
        if missing:
            return f"{name} can only carry {' '.join(capacity.keywords)} models"
        excluded = [k for k in capacity.excluded_keywords if k in held]
        if excluded:
            return f"{name} can't carry {'/'.join(excluded)} models"
    others = [
        u
        for u in deployment.deployable_units(deployment.owner(game, carrier))
        if u.id != unit.id and getattr(transport(game, u), "id", None) == carrier.id
    ]
    used = sum(
        _space(capacity, keywords(u, m)) for u in others for m in surviving_models(game, u)
    )
    needed = sum(_space(capacity, keywords(unit, m)) for m in models)
    if used + needed > total:
        return (
            f"there isn't room in {name}: {total - used} of its {total} spaces are free, "
            f"and the unit needs {needed}"
        )
    return None


def _transport_bases(game: Game, carrier: Unit) -> list[Base]:
    placed = deployment.positions(game)
    return [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in deployment.models_on_battlefield(game, carrier)
    ]


def transited(game: Game, unit: Unit, kind: str) -> bool:
    # Whether the unit has embarked ("embarked") or disembarked
    # ("disembarked") in this movement phase.
    return any(
        t.unit_id == unit.id
        and t.kind == kind
        and t.battle_round == game.battle_round
        and t.turn_seat == game.turn_seat
        for t in game.unit_transits
    )


def record_transit(game: Game, unit: Unit, kind: str) -> None:
    game.unit_transits.append(
        GameUnitTransit(
            unit_id=unit.id, battle_round=game.battle_round, turn_seat=game.turn_seat, kind=kind
        )
    )


def _check_phase(game: Game, unit: Unit, what: str) -> None:
    from app.services.in_game import reinforcements

    if game.status != "in_progress" or game.phase != "movement":
        raise _bad_request(f"units {what} in the movement phase")
    if deployment.owner(game, unit).seat != game.turn_seat:
        raise _bad_request(f"only the player whose turn it is can {what} their units")
    if reinforcements.movement_ended(game):
        raise _bad_request("the movement phase is over")


def _shock_moves(carrier: Unit) -> set[str]:
    # The moves after which the transport's units can shock disembark.
    from app.seeds import datasheet_abilities

    config = datasheet_abilities.SHOCK_DISEMBARK_AFTER
    return {
        kind
        for m in carrier.unit_models
        for a in m.model.abilities
        for kind in config.get(a.name, ())
    }


def shock(game: Game, carrier: Unit) -> bool:
    # Whether disembarking from the transport now is a shock disembark move:
    # it made a move this phase that only a shock disembark is allowed after.
    from app.services.in_game import movement

    moved = movement.unit_move(game, carrier)
    return (
        moved is not None
        and moved.completed
        and moved.kind in ("advance", "fall_back")
        and moved.kind in _shock_moves(carrier)
    )


def check_turn(game: Game, unit: Unit) -> Unit:
    # That the unit can disembark now; its transport.
    from app.services.in_game import movement

    _check_phase(game, unit, "disembark")
    carrier = transport(game, unit)
    if carrier is None:
        raise _bad_request("that unit isn't embarked in a transport")
    if not deployment.is_deployed(carrier, deployment.positions(game)):
        raise _bad_request("its transport isn't on the battlefield")
    if transited(game, unit, "embarked"):
        raise _bad_request("it embarked this phase: it can't disembark in the same phase")
    moved = movement.unit_move(game, carrier)
    if (
        moved is not None
        and moved.completed
        and moved.kind in ("advance", "fall_back")
        and not shock(game, carrier)
    ):
        what = "Advanced" if moved.kind == "advance" else "Fell Back"
        raise _bad_request(f"its transport {what} this turn")
    return carrier


def disembark_mode(game: Game, carrier: Unit, combat: bool = False) -> str:
    # The disembark mode: rapid if the transport made a Normal (or ingress)
    # move this phase - or a shock disembark (which is set up the same way);
    # otherwise tactical, or combat if the player can't set the unit up that
    # way (`combat`).
    from app.services.in_game import movement, reinforcements

    moved = movement.unit_move(game, carrier)
    if moved is not None and moved.completed and moved.kind in (
        "normal", reinforcements.ARRIVED, "advance", "fall_back"
    ):
        return RAPID
    return COMBAT if combat else TACTICAL


def no_charge(game: Game, unit: Unit) -> str | None:
    # Why the unit can't declare a charge this turn after disembarking, if
    # it can't.
    if transited(game, unit, SHOCK_DISEMBARKED):
        return "it made a shock disembark move this turn"
    if transited(game, unit, RAPID_DISEMBARKED):
        return "it made a rapid disembark move this turn"
    if transited(game, unit, COMBAT_DISEMBARKED):
        return "it made a combat or emergency disembark move this turn"
    return None


def surviving_models(game: Game, unit: Unit):
    # The unit's models that aren't destroyed (it may have lost some before
    # embarking) - those that disembark.
    destroyed = {d.unit_model_id for d in game.model_damage if d.destroyed}
    return [m for m in deployment.unit_models(unit) if m.id not in destroyed]


def check_disembark(
    game: Game,
    unit: Unit,
    placement: dict[int, tuple[float, float, float]],
    combat: bool = False,
) -> Placement:
    # Whether the unit could disembark with its models at `placement` - in a
    # combat disembark move, if `combat` and it can't be a rapid one.
    from app.services.in_game import fighting, movement, reinforcements

    carrier = transport(game, unit)
    mode = disembark_mode(game, carrier, combat) if carrier else TACTICAL
    reach = COMBAT_DISEMBARK_RANGE if mode == COMBAT else DISEMBARK_RANGE
    models, bases = deployment.unit_bases(unit, placement, surviving_models(game, unit))
    others = deployment.placed_bases(game, unit)
    seat = deployment.owner(game, unit).seat
    carriers = _transport_bases(game, carrier) if carrier else []
    # In a combat disembark, models can end engaged with enemy units the
    # transport is engaged with.
    allowed = (
        {m.id for t in fighting.fight_targets(game, carrier) for m in t.unit_models}
        if mode == COMBAT and carrier
        else set()
    )
    enemies = [b for p, m, b in others if p.seat != seat and m.id not in allowed]
    # After an ingress move, as the transport had to be set up.
    move = movement.unit_move(game, carrier) if carrier else None
    ingress = mode == RAPID and move is not None and move.kind == reinforcements.ARRIVED
    far_from = [b for p, _, b in others if p.seat != seat]
    layout = game.layout
    side = "defender" if seat == game.attacker_seat else "attacker"
    enemy_zone = layout.deployment.zone(side) if layout and layout.deployment else None
    problems = deployment.physical_problems(game, models, bases, others)
    for model in models:
        base = bases[model.id]
        found = []
        if not regions.base_wholly_within_of(base, carriers, reach):
            found.append(f'isn\'t wholly within {reach:g}" of its transport')
        if any(gap(base, e) <= ENGAGEMENT_RANGE + TOLERANCE for e in enemies):
            found.append("is within Engagement Range of an enemy model")
        if ingress:
            if any(gap(base, e) < reinforcements.ENEMY_DISTANCE - TOLERANCE for e in far_from):
                found.append('is within 8" of an enemy model (its transport arrived this turn)')
            if (
                not reinforcements.has_deep_strike(carrier)
                and game.battle_round <= reinforcements.FIRST_ROUND
                and enemy_zone
                and deployment.distance_to_polygon(base, enemy_zone) <= TOLERANCE
            ):
                found.append("is in the enemy deployment zone (its transport arrived this turn)")
        problems[model.id] = found + problems[model.id]
    return deployment.summarise(models, problems)


def disembark(
    game: Game,
    unit: Unit,
    placement: dict[int, tuple[float, float, float]],
    combat: bool = False,
) -> None:
    # The unit disembarks as placed, if it can (see disembark_mode).
    from app.services.in_game import battle_shock

    carrier = check_turn(game, unit)
    mode = disembark_mode(game, carrier, combat)
    result = check_disembark(game, unit, placement, combat)
    if not result.valid:
        raise _bad_request("can't disembark there: " + "; ".join(result.problems))
    for unit_model_id, (x, y, rotation) in placement.items():
        game.model_positions.append(
            GameModelPosition(unit_model_id=unit_model_id, x=x, y=y, rotation=rotation)
        )
    game.battle_formations.remove(deployment.battle_formation(game, unit))
    record_transit(game, unit, "disembarked")
    game.disembarkations.append(
        GameDisembarkation(
            unit_id=unit.id,
            transport_unit_id=carrier.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
        )
    )
    if shock(game, carrier):
        record_transit(game, unit, SHOCK_DISEMBARKED)
    elif mode == RAPID:
        record_transit(game, unit, RAPID_DISEMBARKED)
    elif mode == COMBAT:
        record_transit(game, unit, COMBAT_DISEMBARKED)
        battle_shock.battle_shock_outright(game, unit, "combat disembark", 0)
        for unit_model in placement:
            _hazard(game, unit, next(m for m in unit.unit_models if m.id == unit_model))
    if mode != TACTICAL:
        # It can't move again this phase.
        game.unit_moves.append(
            GameUnitMove(
                unit_id=unit.id,
                battle_round=game.battle_round,
                turn_seat=game.turn_seat,
                kind=DISEMBARKED,
                completed=True,
            )
        )


def _hazard(game: Game, unit: Unit, unit_model) -> None:
    # A combat disembark's hazard roll for the model: on a failure it suffers
    # mortal wounds by its keywords (see app/services/combat.py).
    import random

    from app.services.combat import hazard_failed, hazard_wounds
    from app.services.in_game import casualties
    from app.services.list_building.enhancements import model_keywords

    if hazard_failed(random.randint(1, 6)):
        wounds = sum(
            1
            for _ in range(hazard_wounds([model_keywords(unit, m) for m in unit.unit_models]))
            if not casualties.resists(unit_model)
        )
        if wounds:
            casualties._lose(game, unit_model, wounds)


# --- embarking during the battle ---

# The moves a unit can embark after.
EMBARK_AFTER = ("normal", "advance", "fall_back")


def embark_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't embark now (in any transport), or None if it could.
    from app.services.in_game import battle_formations, movement

    if not deployment.is_deployed(unit, deployment.positions(game)):
        return "it isn't on the battlefield"
    if battle_formations.is_transport(unit):
        return "a TRANSPORT can't embark in another"
    move = movement.unit_move(game, unit)
    if move is None or not move.completed or move.kind not in EMBARK_AFTER:
        return "it hasn't made a Normal, Advance or Fall Back move this phase"
    if transited(game, unit, "disembarked"):
        return "it disembarked this phase: it can't embark in the same phase"
    from app.services.in_game.shooting import set_up_this_turn

    if set_up_this_turn(game, unit):
        return "it was set up on the battlefield this turn"
    return None


def transports_in_reach(game: Game, unit: Unit) -> list[Unit]:
    # The player's TRANSPORT units on the battlefield that every model of the
    # unit is within 3" of (a model of).
    from app.services.in_game import battle_formations

    player = deployment.owner(game, unit)
    placed = deployment.positions(game)
    bases = [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in deployment.models_on_battlefield(game, unit)
    ]
    found = []
    for carrier in deployment.deployable_units(player):
        if carrier.id == unit.id or not battle_formations.is_transport(carrier):
            continue
        if not deployment.is_deployed(carrier, placed):
            continue
        carriers = _transport_bases(game, carrier)
        if bases and all(
            any(gap(b, c) <= EMBARK_RANGE + TOLERANCE for c in carriers) for b in bases
        ):
            found.append(carrier)
    return found


def embarkable(game: Game) -> list[tuple[Unit, list[Unit]]]:
    # The units the player whose turn it is could embark now, each with the
    # transports it could embark in.
    if game.status != "in_progress" or game.phase != "movement" or game.turn_seat is None:
        return []
    player = next(p for p in game.players if p.seat == game.turn_seat)
    found = []
    for unit in deployment.deployable_units(player):
        if embark_reason(game, unit) is not None:
            continue
        carriers = transports_in_reach(game, unit)
        if carriers:
            found.append((unit, carriers))
    return found


def embark(game: Game, unit: Unit, carrier: Unit) -> None:
    # The unit embarks in the transport, if it can: off the battlefield.
    _check_phase(game, unit, "embark")
    if (reason := embark_reason(game, unit)) is not None:
        raise _bad_request(f"it can't embark: {reason}")
    if carrier.id not in {c.id for c in transports_in_reach(game, unit)}:
        raise _bad_request(
            f'every model must be within 3" of {carrier.faction_unit.name}, one of its '
            "player's TRANSPORT units"
        )
    if (reason := capacity_reason(game, unit, carrier)) is not None:
        raise _bad_request(f"it can't embark: {reason}")
    _take_aboard(game, unit, carrier)


def _take_aboard(game: Game, unit: Unit, carrier: Unit) -> None:
    models = {m.id for m in unit.unit_models}
    for position in [p for p in game.model_positions if p.unit_model_id in models]:
        game.model_positions.remove(position)
    game.battle_formations.append(
        GameBattleFormation(unit_id=unit.id, place="embarked", transport_unit_id=carrier.id)
    )
    record_transit(game, unit, "embarked")


def embark_now(game: Game, unit: Unit, carrier: Unit) -> None:
    # A rule has the unit embark outside its Movement phase (e.g. Reactive
    # Safeguard): every model must still be within 3" of the transport, with
    # room for the whole unit.
    if carrier.id not in {c.id for c in transports_in_reach(game, unit)}:
        raise _bad_request(f'every model must be within 3" of {carrier.faction_unit.name}')
    if (reason := capacity_reason(game, unit, carrier)) is not None:
        raise _bad_request(f"it can't embark: {reason}")
    _take_aboard(game, unit, carrier)
