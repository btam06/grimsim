from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.engine import context
from app.engine import store as game_store
from app.engine.state import Game
from app.models.stratagem import UNIT_TARGET_ACTIONS
from app.routers import games as g
from app.schemas import (
    ActionIn,
    ResurrectionIn,
    FormationGrantIn,
    PhaseStartIn,
    BattleShockTakeIn,
    CommandChoiceIn,
    ConsolidateIn,
    DeployUnitIn,
    EmbarkIn,
    FightIn,
    FormationIn,
    GameAchieveIn,
    GameStratagemIn,
    MissionAnswerIn,
    ModelPositionIn,
    ObjectiveSelectionIn,
    PsychicIn,
    RepairIn,
    RuleChoiceIn,
    SeatIn,
    ShootIn,
    TeleportHomerIn,
    UnitAbilityTargetIn,
    UnitIdIn,
    UnitMoveIn,
    UnitPlacementIn,
)
from app.services import dice, weapon_profiles
from app.services.in_game import (
    battle_round,
    charging,
    command_phase,
    deployment,
    embarked,
    fighting,
    movement,
    regions,
    reinforcements,
    scouts,
)
from app.services.in_game import shooting as shooting_service
from app.services.in_game import emergency as emergency_service
from app.services.in_game import phase_end as phase_end_service
from app.services.in_game import phase_start as phase_start_service

# The agent interface: everything a player can do in a game, as one list of
# legal actions and one way to apply them - for a program to play the game
# (see GET /games/{id}/agent and POST /games/{id}/agent/apply).
#
# Each action has a `type` (what it does - "shoot", "move", "use_stratagem"...),
# the `seat` deciding it, and its `params` - what the matching endpoint takes.
# Discrete choices (units, targets, weapons, options, stratagems) are listed
# in full: one action each. Placing models isn't: a model can end up anywhere
# within its reach, so an action that places a unit's models (moving,
# charging, deploying, disembarking...) carries a `placement` - each model's
# start and how far it can go - and, where one could be found and checked, a
# legal `default` (often: where they are now). Apply it with its own
# positions in `params.positions`, and the endpoint's checks decide.
#
# `waiting_for` is the decision holding the game up: whose it is, and why
# (Battle-shock tests to take, a Fight step pick, the end of a phase...).
# Both players' other legal actions are listed too (e.g. stratagems the
# opponent can use now).
#
# Actions applied here are kept in a debug log: was the action listed as
# legal then, did it work (or why not), and how long it took. An action that
# was listed but was then rejected means the two disagree - a bug to look at.
# (The list is built from the same state the game's panels show, and applied
# through the same endpoints, so it can't drift from what a person can do.
# It's slow - each piece reloads the game - which is fine for now.)

router = APIRouter(prefix="/games", tags=["agent"])

# How many spots to try when looking for a default placement.
PLACEMENT_TRIES = 40
# How far a searched placement's models are nudged to a free spot at most
# (see deployment.formation): a spot that needs more is passed over for the
# next - near enough where it was wanted, and far quicker than packing them in.
SEARCH_NUDGE = 2.0


@dataclass
class Action:
    type: str
    seat: int
    label: str
    params: dict = field(default_factory=dict)
    # For an action that places models: {"unit_id", "check", "models": [{
    # "unit_model_id", "x", "y", "rotation", "reach"}], "default": positions
    # or None}.
    placement: dict | None = None

    @property
    def concrete(self) -> bool:
        # Whether it can be applied as listed (a placement needs positions).
        return self.placement is None or self.placement.get("default") is not None


class AgentActionIn(BaseModel):
    type: str
    seat: int
    params: dict = {}


class AgentApplyIn(BaseModel):
    action: AgentActionIn


def _key(action_type: str, seat: int, params: dict) -> str:
    # How an applied action is matched with the listed ones (positions left
    # out: placements are matched on everything else).
    trimmed = {k: v for k, v in params.items() if k != "positions"}
    return json.dumps([action_type, seat, trimmed], sort_keys=True, default=str)


def _state(game: Game) -> str:
    if game.status != "in_progress":
        return f"{game.status} ({g.deployment_service.deployment_step(game) or '-'})"
    return f"round {game.battle_round}, seat {game.turn_seat}'s {game.phase}"


# --- placements ---


def _positions(game: Game, unit) -> dict[int, tuple[float, float, float]]:
    placed = deployment.positions(game)
    return {
        m.id: (placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    }


def _as_positions(placement: dict) -> list[dict]:
    return [
        {"unit_model_id": i, "x": round(x, 3), "y": round(y, 3), "rotation": round(r, 3)}
        for i, (x, y, r) in placement.items()
    ]


def _valid(check) -> bool:
    try:
        return check().valid
    except HTTPException:
        return False


def _placement(game: Game, unit, check: str, reach, default) -> dict:
    # The placement spec: each model's start (where it is now, if it's on the
    # battlefield) and reach (inches, or None: set up, not moved).
    starts = _positions(game, unit)
    models = []
    for m in unit.unit_models:
        start = starts.get(m.id)
        models.append(
            {
                "unit_model_id": m.id,
                "x": start[0] if start else None,
                "y": start[1] if start else None,
                "rotation": start[2] if start else None,
                "reach": reach(m) if callable(reach) else reach,
            }
        )
    return {
        "unit_id": unit.id,
        "check": check,
        "models": models,
        "default": _as_positions(default) if default else None,
    }


def _search(candidates, make, check) -> dict | None:
    # The first placement made at one of the candidate spots that passes the
    # check.
    for i, (x, y) in enumerate(candidates):
        if i >= PLACEMENT_TRIES:
            break
        try:
            placement = make(x, y)
        except HTTPException:
            continue
        if _valid(lambda: check(placement)):
            return placement
    return None


def _zone_spots(game: Game, seat: int | None) -> list[tuple[float, float]]:
    # Spots in the player's deployment zone (anywhere, with no seat).
    zone = regions.deployment_zone(game, seat) if seat is not None else None
    spots = [
        (x + 0.5, y + 0.5)
        for x in range(1, 60, 3)
        for y in range(1, 44, 3)
        if zone is None or regions.point_in((x + 0.5, y + 0.5), zone)
    ]
    dice.shuffle(spots)
    return spots


def _deployment_anchors(game: Game, seat: int) -> list[tuple[str, tuple[float, float]]]:
    # Where in their deployment zone a unit can be deployed, for an agent to
    # choose between - each the closest spot that fits to: their home
    # objective, the middle of the battlefield (as far forward as it can),
    # and each flank (as far to either side as it can).
    zone = regions.deployment_zone(game, seat)
    if not zone:
        return [("", (30.0, 22.0))]
    cx = sum(p[0] for p in zone) / len(zone)
    cy = sum(p[1] for p in zone) / len(zone)
    anchors = [
        ("on its home objective", (o.x, o.y))
        for o in g.objectives_service.objectives(game)
        if g.objectives_service.is_home(game, o, seat)
    ][:1]
    anchors.append(("forward", (30.0, 22.0)))
    fx, fy = 30.0 - cx, 22.0 - cy
    d = math.hypot(fx, fy) or 1.0
    px, py = -fy / d, fx / d
    anchors += [("on the left flank", (cx + px * 60, cy + py * 60)),
                ("on the right flank", (cx - px * 60, cy - py * 60))]
    return anchors


def _deploy_spot(game: Game, unit, where: str, anchor, spots) -> dict | None:
    # The closest spot to the anchor where the unit fits (see _search) -
    # kept through deployment (the actions are listed again after each unit's
    # deployed): checked again as it is, and only looked for again if it's
    # no longer clear (or, if none was found, once the board's changed).
    cache = context.cache("deploy_spots")
    key = (unit.id, where)
    check = lambda p: deployment.check_placement(game, unit, p)  # noqa: E731
    board = _board(game)
    if cache is not None and key in cache:
        kept, kept_board = cache[key]
        if kept is None and kept_board == board:
            return None
        if kept is not None and _valid(lambda: check(kept)):
            return kept
    found = _search(
        sorted(spots, key=lambda p: math.dist(p, anchor)),
        lambda x, y: deployment.formation(game, unit, x, y, nudge=SEARCH_NUDGE),
        check,
    )
    if cache is not None:
        cache[key] = (found, board)
    return found


def _arrival_spot(game: Game, unit, deep_strike: bool) -> dict | None:
    # Where the unit can arrive from Reserves (see _search) - kept for the
    # phase, like _deploy_spot.
    cache = context.cache("arrival_spots")
    key = (game.battle_round, game.turn_seat, game.phase, unit.id)
    check = lambda p: reinforcements.check_arrival(game, unit, p)  # noqa: E731
    board = _board(game)
    if cache is not None and key in cache:
        kept, kept_board = cache[key]
        if kept is None and kept_board == board:
            return None
        if kept is not None and _valid(lambda: check(kept)):
            return kept
    if deep_strike:
        found = _search(
            _zone_spots(game, None), lambda x, y: deployment.formation(game, unit, x, y, nudge=SEARCH_NUDGE), check
        )
    else:
        # (In two ranks flush with the edge: wholly within 6" of it.)
        found = _search(_edge_spots(), lambda x, y: _along_edge(game, unit, x, y), check)
    if cache is not None:
        cache[key] = (found, board)
    return found


def _along_edge(game: Game, unit, x: float, y: float) -> dict:
    # The unit set up at an edge spot (see _edge_spots) in two ranks along
    # that edge, against it.
    if x in (3.5, 56.5):
        return deployment.formation(
            game, unit, 0.0 if x < 30 else 60.0, y, ranks=2, upright=True, nudge=SEARCH_NUDGE
        )
    return deployment.formation(
        game, unit, x, 0.0 if y < 22 else 44.0, ranks=2, nudge=SEARCH_NUDGE
    )


def _board(game: Game) -> int:
    # Where every model stands, in short: a spot not found is only looked for
    # again once something's moved (or been set up, or removed).
    return hash(tuple(sorted((p.unit_model_id, p.x, p.y) for p in game.model_positions)))


def _edge_spots() -> list[tuple[float, float]]:
    spots = [(x, y) for x in range(4, 58, 4) for y in (3.5, 40.5)] + [
        (x, y) for x in (3.5, 56.5) for y in range(4, 42, 4)
    ]
    dice.shuffle(spots)
    return spots


def _towards(game: Game, unit, targets: list, reach: float) -> dict:
    # Each of the unit's models moved straight towards the closest model of
    # the targets, as far as it can (stopping just short of base contact).
    placed = _positions(game, unit)
    theirs = [p for t in targets for p in _positions(game, t).values()]
    moved = {}
    for i, (x, y, r) in placed.items():
        if not theirs:
            moved[i] = (x, y, r)
            continue
        tx, ty, _ = min(theirs, key=lambda p: math.dist((x, y), p[:2]))
        d = math.dist((x, y), (tx, ty))
        # (Centre to centre: leave room for both bases - about an inch each.)
        step = max(0.0, min(reach, d - 2.0))
        moved[i] = (x + (tx - x) * step / d, y + (ty - y) * step / d, r) if d else (x, y, r)
    return moved


def _centre(placed: dict) -> tuple[float, float]:
    return (
        sum(p[0] for p in placed.values()) / len(placed),
        sum(p[1] for p in placed.values()) / len(placed),
    )


# Where a move towards a point is tried: the whole way (as far as it can go),
# three quarters, half - each straight there, or to one side or the other.
MOVE_STEPS = (1.0, 0.75, 0.5)
MOVE_SIDESTEPS = (0.0, 1.5, -1.5, 3.0, -3.0)
# How many of them (clear of terrain and other models) are checked in full.
MOVE_CHECKS = 3


def _move_towards(game: Game, unit, kind: str, point, reach: float) -> dict | None:
    # The unit moved towards the point - the first of the spots tried that's
    # clear of terrain features and other models, and passes the move check
    # (paths and all). None if none does.
    #
    # Kept for the phase (the actions are listed again after every action):
    # while the unit hasn't moved, only other models overlapping it could
    # change - enemy models (round which it paths) don't move in its phase.
    placed = _positions(game, unit)
    if not placed or reach < 0.5:
        return None
    cx, cy = _centre(placed)
    d = math.dist((cx, cy), point)
    if d < 0.5:
        return None
    others = deployment.placed_bases(game, unit)
    models = deployment.models_on_battlefield(game, unit)

    def clear(guess) -> bool:
        _, bases = deployment.unit_bases(unit, guess, models)
        return not any(deployment.physical_problems(game, models, bases, others).values())

    cache = context.cache("moves_towards")
    key = (
        game.battle_round, game.turn_seat, game.phase, unit.id, kind,
        tuple(sorted(placed.items())), point, round(reach, 2),
    )
    if cache is not None and key in cache:
        guess = cache[key]
        if guess is None or clear(guess):
            return guess
    guess = _search_towards(game, unit, kind, placed, point, reach, clear)
    if cache is not None:
        cache[key] = guess
    return guess


def _search_towards(game: Game, unit, kind: str, placed: dict, point, reach: float, clear):
    cx, cy = _centre(placed)
    d = math.dist((cx, cy), point)
    ux, uy = (point[0] - cx) / d, (point[1] - cy) / d
    checks = 0
    for fraction in MOVE_STEPS:
        step = min(reach, d) * fraction
        if step < 0.5:
            continue
        for side in MOVE_SIDESTEPS:
            dx, dy = ux * step - uy * side, uy * step + ux * side
            guess = {i: (x + dx, y + dy, r) for i, (x, y, r) in placed.items()}
            if not clear(guess):
                continue
            if _valid(lambda: movement.check_move(game, unit, kind, guess)):
                return guess
            checks += 1
            if checks >= MOVE_CHECKS:
                return None
    return None


def _objective_to_move_to(game: Game, unit, seat: int, control: list) -> list:
    # The closest objective the player doesn't control (or if they control
    # them all, the closest) - not if the unit's already at it. `control`:
    # objectives.control(game, live=True).
    placed = _positions(game, unit)
    if not placed or not control:
        return []
    centre = _centre(placed)
    open_ = [c.objective for c in control if c.live_controller != seat]
    picked = min(
        open_ or [c.objective for c in control],
        key=lambda o: math.dist(centre, (o.x, o.y)),
    )
    return [picked] if math.dist(centre, (picked.x, picked.y)) >= 1.0 else []


# Waiting on a player's abilities for the start of the phase (see
# app/services/in_game/phase_start.py window_seat).
START_OF_PHASE = "abilities for the start of the phase"
# And on their declarations for the end of the phase (see
# app/services/in_game/phase_end.py).
END_OF_PHASE = "declarations for the end of the phase"


# --- the decision holding the game up ---


async def _waiting_for(session: AsyncSession, game: Game) -> dict:
    gid = game.id
    if game.status == "setup":
        return {"seat": game.attacker_seat, "reason": "the game hasn't started"}
    if game.status == "finished":
        return {"seat": None, "reason": "the game is over"}
    step = g.deployment_service.deployment_step(game)
    if game.status == "deployment":
        if step == "formations":
            formations = g._formations_out(game)
            seat = next((p.seat for p in formations.players if not p.done), None)
            return {"seat": seat, "reason": "declaring battle formations"}
        if step == "deploying":
            return {"seat": g.deployment_service.deploying_seat(game), "reason": "deploying"}
        if step == "first_turn":
            return {"seat": game.attacker_seat, "reason": "rolling off for the first turn"}
        return {"seat": g.scouts_service.scouting_seat(game), "reason": "Scouts moves"}
    # Teleport Homer tokens are set up once the battle's begun (first round).
    homers = g._teleport_homers_out(game)
    if homers.waiting_seats:
        return {"seat": homers.waiting_seats[0], "reason": "setting up Teleport Homers"}
    emergency = g._emergency_out(game)
    if emergency.units:
        return {"seat": emergency.units[0].seat, "reason": "emergency disembarking"}
    if (seat := phase_start_service.window_seat(game)) is not None:
        return {"seat": seat, "reason": START_OF_PHASE}
    if (seat := phase_end_service.window_seat(game)) is not None:
        return {"seat": seat, "reason": END_OF_PHASE}
    battle_shock = await g._battle_shock_out(session, game)
    if battle_shock.pending:
        return {"seat": battle_shock.pending[0].seat, "reason": "taking Battle-shock tests"}
    prompts = g._mission_state_out(game).prompts
    if prompts:
        return {"seat": prompts[0].seat, "reason": f"answering {prompts[0].mission}"}
    offers = g._scoring_out(game).offers
    if offers:
        return {"seat": offers[0].seat, "reason": f"claiming or holding {offers[0].name}"}
    reanimation = await g.get_reanimation(gid, session)
    if reanimation.placing:
        return {"seat": reanimation.seat, "reason": "placing reanimated models"}
    turn, other = game.turn_seat, g.game_service.other_seat(game.turn_seat)
    if (seat := _round_choice_seat(game)) is not None:
        return {"seat": seat, "reason": "choosing an option for the battle round"}
    if game.phase == "movement" and reinforcements.movement_ended(game):
        return {"seat": other, "reason": "the end of the Movement phase (Rapid Ingress, Overwatch)"}
    if game.phase == "charge" and g.core_stratagems_service.charge_ended(game):
        return {"seat": other, "reason": "the end of the Charge phase (Heroic Intervention)"}
    if game.phase == "fight":
        fight_state = g._fight_out(game)
        if fight_state.step == "pile_in":
            return {"seat": fighting.piling_seat(game), "reason": "piling in"}
        if fight_state.seat is not None:
            what = "consolidating" if fight_state.step == "consolidate" else "picking a unit to fight"
            return {"seat": fight_state.seat, "reason": what}
    return {"seat": turn, "reason": f"their {game.phase.replace('_', ' ')} phase"}


def _emergency_default(game: Game, unit, suggested) -> dict:
    # The suggested set-up if it's allowed - otherwise as many of its models
    # as can be set up together, the rest left out (destroyed): one at a
    # time, each kept if the set-up still is. (None at all is always
    # allowed, so there's always one to take.)
    placement = {p.unit_model_id: (p.x, p.y, p.rotation) for p in suggested}
    if _valid(lambda: emergency_service.check(game, unit, placement)):
        return placement
    kept: dict = {}
    for model_id, spot in placement.items():
        trying = {**kept, model_id: spot}
        if _valid(lambda: emergency_service.check(game, unit, trying)):
            kept = trying
    return kept


def _round_choice_seat(game: Game) -> int | None:
    # At the start of a battle round, the first player still to choose a
    # required option for an army rule (e.g. Doctrina Imperatives).
    if game.phase != battle_round.START_OF_ROUND:
        return None
    for player in game.players:
        chosen = battle_round.choices(game, player.seat)
        for rule in battle_round.player_rules(game, player, game.battle_round):
            if rule.required and rule.faction_ability_id not in chosen:
                return player.seat
    return None


# --- the legal actions ---


async def _legal_actions(session: AsyncSession, game: Game, waiting: dict) -> list[Action]:
    gid = game.id
    found: list[Action] = []
    add = found.append
    step = g.deployment_service.deployment_step(game)
    units = {u.id: u for p in game.players for u in deployment.deployable_units(p)}

    if game.status == "setup":
        add(Action("start_game", waiting["seat"], "Start the game"))
        return found
    if game.status == "finished":
        return found

    # --- before the battle ---
    if game.status == "deployment":
        if step == "formations":
            await _formation_actions(game, add, units)
        elif step == "deploying":
            seat = g.deployment_service.deploying_seat(game)
            for unit in deployment.deployable_units(next(p for p in game.players if p.seat == seat)):
                if deployment.is_deployed(unit, deployment.positions(game)):
                    continue
                if deployment.battle_formation(game, unit) is not None:
                    continue
                # Where: a few spots to choose from (see _deployment_anchors).
                spots = _zone_spots(game, seat)
                found_any = False
                for where, anchor in _deployment_anchors(game, seat):
                    default = _deploy_spot(game, unit, where, anchor, spots)
                    if default is None:
                        continue
                    found_any = True
                    add(Action(
                        "deploy", seat, f"Deploy {unit.label} {where}".rstrip(),
                        {"unit_id": unit.id, "where": where},
                        _placement(game, unit, "deployment", None, default),
                    ))
                if not found_any:
                    add(Action(
                        "deploy", seat, f"Deploy {unit.label}", {"unit_id": unit.id},
                        _placement(game, unit, "deployment", None, None),
                    ))
        elif step == "first_turn":
            add(Action("roll_first_turn", waiting["seat"], "Roll off for the first turn"))
        else:
            seat = g.scouts_service.scouting_seat(game)
            if seat is not None:
                scouting = g._scouts_out(game)
                for su in scouting.units:
                    unit = units[su.unit_id]
                    if su.in_reserves:
                        default = _search(
                            _zone_spots(game, seat),
                            lambda x, y, u=unit: deployment.formation(game, u, x, y, nudge=SEARCH_NUDGE),
                            lambda p, u=unit: scouts.check(game, seat, u, p),
                        )
                    else:
                        default = _positions(game, unit)
                    add(Action(
                        "scout_move", seat, f"Scouts move: {su.name}", {"unit_id": su.unit_id},
                        _placement(game, unit, "scouts", su.distance, default),
                    ))
                add(Action("finish_scouts", seat, "Done with Scouts moves", {"seat": seat}))
        return found

    # --- in the battle ---
    turn = game.turn_seat

    # Always-blocking decisions first: Teleport Homer tokens (set up at the
    # start of the battle - finishing without any is allowed), ...
    for seat in g._teleport_homers_out(game).waiting_seats:
        add(Action("finish_teleport_homers", seat, "Done with Teleport Homers"))
    emergency = g._emergency_out(game)
    for eu in emergency.units:
        unit = units[eu.unit_id]
        placement = _placement(game, unit, "emergency", 6.0, None)
        placement["default"] = _as_positions(_emergency_default(game, unit, eu.suggested))
        add(Action(
            "emergency_disembark", eu.seat, f"Emergency disembark {eu.name}",
            {"unit_id": eu.unit_id}, placement,
        ))
    # ... abilities for the start of the phase, one player at a time: the
    # player whose turn it is first (e.g. Secutor of Olympus, Data-spike), then
    # their opponent (e.g. Data-spike, Defend the Divine Work) - nothing else
    # until each is done.
    if waiting.get("reason") == START_OF_PHASE:
        seat = waiting["seat"]
        for ability in await g.get_shooting_start(gid, session):
            if deployment.owner(game, units[ability.unit_id]).seat != seat:
                continue
            for target in ability.targets:
                add(Action("shooting_start", seat,
                           f"{ability.unit_name}: {ability.ability} on {target.name}",
                           {"unit_id": ability.unit_id, "ability": ability.ability,
                            "target_unit_id": target.unit_id}))
        if phase_start_service.waiting(game) == seat:
            for available in phase_start_service.available(game):
                add(Action("phase_start_ability", seat,
                           f"{available.ability}: {available.unit.label}",
                           {"seat": seat, "unit_id": available.unit.id,
                            "ability": available.ability}))
        add(Action("finish_phase_start", seat, "Done with abilities for the start of the phase",
                   {"seat": seat}))
        return found
    # ... and declarations for the end of the phase, likewise, once the player
    # whose turn it is ends it: Resurrection Orbs; units going into Strategic
    # Reserves at the end of the turn (e.g. Tunnelling Horrors).
    if waiting.get("reason") == END_OF_PHASE:
        seat = waiting["seat"]
        for ru in (await g.get_resurrection(gid, session)).units:
            if not ru.declared and ru.seat == seat:
                add(Action("resurrect", seat, f"{ru.name} resurrects at the end of the phase",
                           {"seat": seat, "unit_id": ru.unit_id}))
        if game.phase == g.game_service.PHASES[-1]:
            for tu in (await g.get_turn_end_reserves(gid, session)).units:
                if not tu.declared and tu.seat == seat:
                    add(Action("turn_end_reserves", seat,
                               f"{tu.name} goes into Strategic Reserves at the end of the turn",
                               {"seat": seat, "unit_id": tu.unit_id}))
        add(Action("finish_phase_end", seat, "Done with declarations for the end of the phase",
                   {"seat": seat}))
        return found
    battle_shock = await g._battle_shock_out(session, game)
    for test in battle_shock.pending:
        add(Action("battle_shock", test.seat, f"Take {test.unit_name}'s Battle-shock test",
                   {"test_id": test.id, "insane_bravery": False}))
        if battle_shock.insane_bravery.get(test.seat) is None:
            add(Action("battle_shock", test.seat,
                       f"Insane Bravery for {test.unit_name}'s Battle-shock test",
                       {"test_id": test.id, "insane_bravery": True}))
    for prompt in g._mission_state_out(game).prompts:
        options = prompt.options or prompt.units
        if prompt.pick_min == 0:
            add(Action("mission_prompt", prompt.seat, f"{prompt.mission}: none",
                       {"prompt_id": prompt.id, "ids": []}))
        for option in options:
            add(Action("mission_prompt", prompt.seat, f"{prompt.mission}: {option.label}",
                       {"prompt_id": prompt.id, "ids": [option.id]}))
    for offer in g._scoring_out(game).offers:
        add(Action("claim_offer", offer.seat, f"Claim {offer.name} ({offer.points} VP)",
                   {"offer_id": offer.id}))
        add(Action("hold_offer", offer.seat, f"Hold {offer.name}", {"offer_id": offer.id}))
    reanimation = await g.get_reanimation(gid, session)
    if reanimation.placing:
        for ru in reanimation.units:
            add(Action(
                "place_reanimated", reanimation.seat, f"Place {ru.name}'s returned models",
                {"unit_id": ru.unit_id},
                _placement(game, units[ru.unit_id], "reanimation", None,
                           {p.unit_model_id: (p.x, p.y, p.rotation) for p in ru.to_place}),
            ))
    if found:
        return found

    # Advancing: the seat the game waits on (at a pause, that's declining) -
    # not before the battle round's required options are chosen, nor the
    # Command phase's (e.g. Canticles of the Omnissiah).
    if _round_choice_seat(game) is None and not (
        game.phase == "command" and command_phase.missing_choices(game)
    ):
        # (The player whose turn it is ending their phase, with something to
        # declare for its end: the declarations first - see phase_end.py.)
        if waiting["seat"] == game.turn_seat and phase_end_service.to_open(game):
            add(Action("end_phase", waiting["seat"], "End of phase: declarations for it first"))
        else:
            add(Action("advance", waiting["seat"], "Next phase / end of phase"))

    if game.phase == "start_of_round":
        for player in (await g.round_start(gid, session)).players:
            for rule in player.rules:
                if not rule.options or rule.faction_ability_id is None:
                    continue
                # (Likewise once chosen.)
                if rule.chosen is not None:
                    continue
                for option in rule.options + ([] if rule.required else [None]):
                    add(Action("round_start_choice", player.seat, f"{rule.name}: {option or 'none'}",
                               {"seat": player.seat, "faction_ability_id": rule.faction_ability_id,
                                "option": option}))

    if game.phase == "command":
        command = g._command_out(game)
        if command.seat is not None:
            for ability in command.abilities:
                # One selection an ability a phase here: a person can change
                # their mind until the phase ends, but an agent needn't (and
                # could go back and forth for ever).
                if ability.chosen:
                    continue
                for option in ability.options:
                    # An option with targets of its own (an enemy unit - e.g.
                    # Invocation of Machine Vengeance) needs one of them.
                    if option in ability.option_targets:
                        targets = ability.option_targets[option]
                    else:
                        targets = ability.targets if ability.needs_target else [None]
                    for target in targets:
                        add(Action(
                            "command_choice", command.seat,
                            f"{ability.unit_name}: {ability.ability} - {option}"
                            + (f" on {target.name}" if target else ""),
                            {"seat": command.seat, "unit_id": ability.unit_id,
                             "faction_ability_id": ability.faction_ability_id,
                             "ability": ability.ability, "option": option,
                             "target_unit_id": target.unit_id if target else None},
                        ))
            # (Once selected, not again: changing it would only go round in
            # circles - a person can, but an agent needn't.)
            for selection in command.objective_selections:
                if g.selected_objectives_service.own_selection(
                    game, command.seat, selection.name
                ) is not None:
                    continue
                for option in selection.options:
                    add(Action("select_objective", command.seat,
                               f"{selection.name}: {option.name}",
                               {"seat": command.seat, "name": selection.name,
                                "objective_id": option.id}))
        for rally in await g.get_rallies(gid, session):
            for target in rally.targets:
                add(Action("rally", turn, f"{rally.unit_name}: {rally.ability} on {target.name}",
                           {"unit_id": rally.unit_id, "ability": rally.ability,
                            "target_unit_id": target.unit_id}))
        for rep in await g.get_repairs(gid, session):
            for target in rep.targets:
                add(Action("repair", turn, f"{rep.unit_name}: {rep.ability} on {target.name}",
                           {"unit_id": rep.unit_id, "ability": rep.ability,
                            "unit_model_id": target.unit_model_id}))

    if game.phase == "movement":
        await _movement_actions(session, game, add, units, turn)

    if game.phase == "shooting":
        await _shooting_actions(session, game, add, units, turn)

    if game.phase == "charge":
        await _charge_actions(session, game, add, units)

    if game.phase == "fight":
        await _fight_actions(session, game, add, units)

    # Psychic abilities, surge moves waiting to be made.
    for pu in g._psychic_out(game).units:
        for ab in pu.abilities:
            if not ab.usable:
                continue
            for target in ab.targets or [None]:
                add(Action("psychic", pu.seat, f"{pu.name}: {ab.name}"
                           + (f" on {target.name}" if target else ""),
                           {"unit_id": pu.unit_id, "ability": ab.name,
                            "target_unit_id": target.unit_id if target else None}))
    for sm in g._surge_out(game):
        unit = units[sm.unit_id]
        add(Action("surge_move", sm.seat, f"Surge move {sm.name} towards {sm.target_name}",
                   {"unit_id": sm.unit_id},
                   _placement(game, unit, "surge", sm.distance, _positions(game, unit))))

    # Tactical secondaries a player discards - at the end of their turn (its
    # last phase).
    for player in game.players:
        if player.seat != turn or game.phase != g.game_service.PHASES[-1]:
            continue
        for card in player.secondaries:
            if card.status != "active":
                continue
            if not card.fixed:
                add(Action("discard_secondary", player.seat, f"Discard {card.mission.name}",
                           {"card_id": card.id}))

    # Stratagems either player can use now.
    for seat in (1, 2):
        await _stratagem_actions(session, game, add, seat)
    return found


async def _formation_actions(game: Game, add, units) -> None:
    from app.services.in_game.movement import is_aircraft

    formations = g._formations_out(game)
    for player in formations.players:
        if player.done:
            continue
        seat = player.seat
        transports = [u for u in player.units if u.transport]
        for fu in player.units:
            unit = units[fu.unit_id]
            if fu.place is not None:
                add(Action("set_formation", seat, f"{fu.name}: on the battlefield",
                           {"seat": seat, "unit_id": fu.unit_id, "place": None}))
            if fu.place != "reserves" and (
                player.reserves_points + fu.points <= player.reserves_limit or is_aircraft(unit)
            ):
                add(Action("set_formation", seat, f"{fu.name}: Strategic Reserves",
                           {"seat": seat, "unit_id": fu.unit_id, "place": "reserves"}))
            if not fu.transport:
                for t in transports:
                    if fu.place == "embarked" and fu.transport_unit_id == t.unit_id:
                        continue
                    if embarked.capacity_reason(game, unit, units[t.unit_id]) is None:
                        add(Action("set_formation", seat, f"{fu.name}: embarked in {t.name}",
                                   {"seat": seat, "unit_id": fu.unit_id, "place": "embarked",
                                    "transport_unit_id": t.unit_id}))
        # Abilities that give a unit an ability now (e.g. Thunderhawk
        # Insertion: Deep Strike).
        for grant in player.grants:
            for target in grant.targets:
                if target.unit_id == grant.unit_id:
                    continue
                add(Action("grant_formation", seat,
                           f"{grant.ability}: {grant.grants} for {target.name}",
                           {"seat": seat, "source_unit_id": grant.source_unit_id,
                            "ability": grant.ability, "unit_id": target.unit_id}))
        if all(
            not is_aircraft(units[fu.unit_id]) or fu.place == "reserves" for fu in player.units
        ):
            add(Action("declare_formations", seat, "Declare battle formations", {"seat": seat}))


async def _movement_actions(session, game: Game, add, units, turn) -> None:
    gid = game.id
    if not reinforcements.movement_ended(game):
        move_state = g._movement_out(game)
        control = g.objectives_service.control(game, live=True)
        for mu in move_state.units:
            unit = units[mu.unit_id]
            # Each unit moves once a phase here: a person can redo a move
            # until the phase ends, but an agent needn't (and would spend
            # most of its steps on it).
            if mu.arrived or mu.disembarked or mu.moved:
                continue
            speeds = {m.unit_model_id: m.movement for m in mu.models}
            if "advance" in mu.allowed_kinds and mu.advance_roll is None:
                add(Action("roll_advance", turn, f"Roll to Advance with {mu.name}",
                           {"unit_id": mu.unit_id}))
            if mu.can_reroll_advance:
                add(Action("reroll_advance", turn, f"Re-roll {mu.name}'s Advance roll",
                           {"unit_id": mu.unit_id}))
            for kind in mu.allowed_kinds:
                if kind == "advance" and mu.advance_roll is None:
                    continue
                extra = (mu.advance_roll or 0) if kind == "advance" else 0
                # (No default: staying where it is would only be a 0" move,
                # losing it Remained Stationary.)
                for options in [{}] + ([{"take_to_skies": True}] if mu.can_fly else []) + (
                    [{"mobile": True}] if mu.super_heavy_walker else []
                ):
                    add(Action(
                        "move", turn,
                        f"{movement.KIND_NAMES[kind]}: {mu.name}"
                        + "".join(f" ({k.replace('_', ' ')})" for k in options),
                        {"unit_id": mu.unit_id, "kind": kind, **options},
                        _placement(game, unit, "move",
                                   lambda m, e=extra: speeds.get(m.id, 0) + e, None),
                    ))
                # The same move, its default towards the closest enemy unit
                # (as far as it can go, short of Engagement Range) - and
                # towards the closest objective its player doesn't control
                # (if it isn't there yet).
                if kind != "fall_back":
                    reach = min(speeds.values(), default=0) + extra
                    enemies = charging.enemy_units(game, unit)
                    closest = min(
                        enemies, key=lambda e: charging.distance(game, unit, e), default=None
                    )
                    goals = []
                    if closest is not None and _positions(game, closest):
                        gap = charging.distance(game, unit, closest)
                        goals.append((closest.label, _centre(_positions(game, closest)),
                                      min(reach, gap - movement.ENGAGEMENT_RANGE - 0.5)))
                    for objective in _objective_to_move_to(game, unit, turn, control):
                        goals.append((f"the {objective.kind} objective at "
                                      f"({objective.x:g}, {objective.y:g})",
                                      (objective.x, objective.y), reach))
                    for name, point, step in goals:
                        guess = _move_towards(game, unit, kind, point, step - 0.1)
                        if guess is not None:
                            add(Action(
                                "move", turn,
                                f"{movement.KIND_NAMES[kind]}: {mu.name} towards {name}",
                                {"unit_id": mu.unit_id, "kind": kind},
                                _placement(game, unit, "move",
                                           lambda m, e=extra: speeds.get(m.id, 0) + e, guess),
                            ))
        embarked_state = g._embarked_out(game)
        for eu in embarked_state.units:
            unit = units[eu.unit_id]
            carrier = units[eu.transport_unit_id]
            for combat in (False, True) if eu.mode != "rapid" else (False,):
                reach = 6.0 if combat else 3.0
                cx, cy = list(_positions(game, carrier).values())[0][:2]
                spots = [(cx + dx, cy + dy) for dx in (-4, 0, 4) for dy in (-4, 0, 4) if dx or dy]
                default = _search(
                    spots,
                    lambda x, y, u=unit: deployment.formation(
                        game, u, x, y, embarked.surviving_models(game, u), nudge=SEARCH_NUDGE
                    ),
                    lambda p, u=unit, c=combat: embarked.check_disembark(game, u, p, c),
                )
                add(Action(
                    "disembark", turn,
                    f"{'Combat disembark' if combat else 'Disembark'} {eu.name} from {eu.transport_name}",
                    {"unit_id": eu.unit_id, "combat_disembark": combat},
                    _placement(game, unit, "disembark", reach, default),
                ))
        for emb in embarked_state.embarkable:
            for t in emb.transports:
                add(Action("embark", turn, f"Embark {emb.name} in {t.name}",
                           {"unit_id": emb.unit_id, "transport_unit_id": t.unit_id}))
    reserves = g._reserves_out(game)
    if reserves.seat is not None:
        for ru in reserves.units:
            unit = units[ru.unit_id]
            default = _arrival_spot(game, unit, ru.deep_strike)
            add(Action("bring_in", reserves.seat, f"Bring in {ru.name} from Reserves",
                       {"unit_id": ru.unit_id},
                       _placement(game, unit, "reserves", None, default)))
    for rm in g._reactive_out(game):
        if rm.roll is None:
            add(Action("roll_reactive_move", rm.seat, f"Roll for {rm.name}'s {rm.ability}",
                       {"unit_id": rm.unit_id}))
        else:
            unit = units[rm.unit_id]
            add(Action("reactive_move", rm.seat, f"{rm.ability}: move {rm.name}",
                       {"unit_id": rm.unit_id},
                       _placement(game, unit, "reactive", max(rm.roll, rm.further or 0),
                                  _positions(game, unit))))
    overwatch = await g.get_overwatch(gid, session)
    if overwatch.seat is not None and overwatch.available:
        for ou in overwatch.units:
            if not ou.can_shoot:
                continue
            for target in await g.overwatch_targets(gid, ou.unit_id, session):
                if not target.visible:
                    continue
                choices = _weapon_choices(game, units[ou.unit_id], target.weapons)
                for weapons in choices:
                    add(Action("overwatch", overwatch.seat,
                               f"Fire Overwatch: {ou.name} at {target.name}"
                               + _with(weapons, target.weapons, choices),
                               {"unit_id": ou.unit_id, "target_unit_id": target.unit_id,
                                **weapons}))


def _weapon_choices(game: Game, unit, weapons) -> list[dict]:
    # The weapons to shoot with (see _weapons) - split, if a model would fire
    # both its [CLOSE-QUARTERS] weapons and its other ranged weapons (it can
    # only fire one or the other, 24.07): its other weapons (with the
    # close-quarters ones no such model has), or the close-quarters ones.
    choice = _weapons(weapons)
    if not choice:
        return []
    chosen = set(choice["weapon_ids"])
    models = [
        [w for w in shooting_service.ranged_weapons(m) if w.id in chosen]
        for m in deployment.models_on_battlefield(game, unit)
        if not shooting_service._big(unit, m)
    ]
    cq = shooting_service.close_quarters
    clashing = [ws for ws in models if {cq(w) for w in ws} == {True, False}]
    if not clashing:
        return [choice]
    blocked = {w.id for ws in clashing for w in ws if cq(w)}
    close = {w.id for ws in models for w in ws if cq(w)}
    others = {**choice, "weapon_ids": [i for i in choice["weapon_ids"] if i not in blocked]}
    close_only = {
        **{k: [] for k in choice},
        "weapon_ids": [i for i in choice["weapon_ids"] if i in close],
    }
    return [others, close_only]


def _weapons(weapons) -> dict:
    # Every weapon that reaches - one profile of each (the first listed).
    seen, picked = set(), []
    for w in weapons:
        if not w.in_range or w.unusable:
            continue
        group = weapon_profiles.profile_group(w.name) or w.name
        if group in seen:
            continue
        seen.add(group)
        picked.append(w)
    if not picked:
        return {}
    return {
        "weapon_ids": [w.id for w in picked if not w.enhancement and not w.firing_deck],
        "enhancement_weapon_ids": [w.id for w in picked if w.enhancement],
        "firing_deck_weapon_ids": [w.id for w in picked if w.firing_deck],
    }


def _with(choice: dict, weapons, choices: list[dict]) -> str:
    # " (with X, Y)": which weapons, when there's more than one choice.
    if len(choices) < 2:
        return ""
    names = [w.name for w in weapons if w.id in choice["weapon_ids"] and not w.enhancement]
    return f" (with {', '.join(names)})"


async def _shooting_actions(session, game: Game, add, units, turn) -> None:
    gid = game.id
    shooting_state = await g.get_shooting(gid, session)
    for su in shooting_state.units:
        if su.can_shoot:
            for target in await g.shooting_targets(gid, su.unit_id, session):
                if not (target.visible or target.indirect):
                    continue
                choices = _weapon_choices(game, units[su.unit_id], target.weapons)
                for weapons in choices:
                    add(Action("shoot", turn,
                               f"{su.name} shoots {target.name}"
                               + _with(weapons, target.weapons, choices),
                               {"unit_id": su.unit_id, "target_unit_id": target.unit_id,
                                **weapons}))
        if su.shoot_scoot and su.shoot_scoot_reach:
            unit = units[su.unit_id]
            add(Action("shoot_scoot", turn, f"{su.shoot_scoot}: move {su.name}",
                       {"unit_id": su.unit_id},
                       _placement(game, unit, "shoot_scoot", su.shoot_scoot_reach,
                                  _positions(game, unit))))
    actions_state = g._actions_out(game)
    for unit_id, options in actions_state.options.items():
        for option in options:
            if option.reason is not None:
                continue
            for target in option.targets:
                add(Action("start_action", turn, f"{name_of(units, unit_id)}: {option.action} on {target.label}",
                           {"unit_id": unit_id, "action": option.action, "target_id": target.id}))


def name_of(units, unit_id) -> str:
    return units[unit_id].label if unit_id in units else str(unit_id)


async def _charge_actions(session, game: Game, add, units) -> None:
    gid = game.id
    charge_state = g._charge_out(game)
    for cu in charge_state.units:
        seat = deployment.owner(game, units[cu.unit_id]).seat
        if cu.charged or cu.failed:
            continue
        if cu.roll is None:
            if cu.reason is None:
                add(Action("roll_charge", seat, f"Declare a charge with {cu.name}",
                           {"unit_id": cu.unit_id}))
            continue
        if cu.can_reroll:
            add(Action("reroll_charge", seat, f"Re-roll {cu.name}'s charge", {"unit_id": cu.unit_id}))
        unit = units[cu.unit_id]
        for target in await g.charge_targets(gid, cu.unit_id, session):
            if not target.in_reach:
                continue
            enemy = units[target.unit_id]
            guess = _towards(game, unit, [enemy], cu.roll)
            default = guess if _valid(
                lambda: charging.check_charge(game, unit, [enemy], guess)
            ) else None
            add(Action("charge", seat, f"{cu.name} charges {target.name} (rolled {cu.roll})",
                       {"unit_id": cu.unit_id, "target_unit_ids": [target.unit_id]},
                       _placement(game, unit, "charge", cu.roll, default)))


async def _fight_actions(session, game: Game, add, units) -> None:
    gid = game.id
    pile = g._pile_in_out(game)
    if pile.seat is not None:
        for pu in pile.units:
            if not pu.can_pile_in:
                continue
            unit = units[pu.unit_id]
            stay = _positions(game, unit)
            default = stay if _valid(lambda: fighting.check_pile_in(game, unit, stay)) else None
            add(Action("pile_in", pile.seat, f"Pile in with {pu.name}", {"unit_id": pu.unit_id},
                       _placement(game, unit, "pile_in", fighting.PILE_IN, default)))
        add(Action("finish_piling_in", pile.seat, "Done piling in", {"seat": pile.seat}))
        return
    fight_state = g._fight_out(game)
    seat = fight_state.seat
    if fight_state.step in ("fights_first", "remaining"):
        for fu in fight_state.units:
            unit = units[fu.unit_id]
            if fu.overrun:
                targets = fighting.pile_in_targets(game, unit)
                guess = _towards(game, unit, targets, fighting.PILE_IN)
                default = guess if _valid(lambda: fighting.check_pile_in(game, unit, guess)) else None
                add(Action("pile_in", fu.seat, f"Overrun pile-in with {fu.name}",
                           {"unit_id": fu.unit_id},
                           _placement(game, unit, "pile_in", fighting.PILE_IN, default)))
            if not fu.can_fight:
                continue
            for target in await g.fight_targets(gid, fu.unit_id, session):
                picked = [w for w in target.weapons if w.default and w.in_range]
                if not picked and not any(w.extra_attacks for w in target.weapons):
                    continue
                params = {"unit_id": fu.unit_id, "target_unit_id": target.unit_id,
                          "weapon_ids": [w.id for w in picked if not w.enhancement],
                          "enhancement_weapon_ids": [w.id for w in picked if w.enhancement]}
                add(Action("fight", fu.seat, f"{fu.name} fights {target.name}", params))
                # The same, using its abilities for fighting (e.g. Banner of
                # Macragge).
                for ability in fu.abilities:
                    add(Action("fight", fu.seat,
                               f"{fu.name} fights {target.name}, using {ability}",
                               {**params, "abilities": [ability]}))
        if fight_state.can_pass and seat is not None:
            add(Action("pass_fight", seat, "Pass (nothing within 5\")", {"seat": seat}))
    if fight_state.step == "consolidate":
        for con in fight_state.consolidations:
            unit = units[con.unit_id]
            stay = _positions(game, unit)
            picks = [con.options[0].id] if con.options and con.mode != "ongoing" else []
            default = stay if _valid(
                lambda: fighting.check_consolidation(game, unit, stay, picks)
            ) else None
            add(Action("consolidate", seat, f"Consolidate {con.unit_name} ({con.mode})",
                       {"unit_id": con.unit_id, "pick_ids": picks},
                       _placement(game, unit, "consolidate", fighting.CONSOLIDATE, default)))
            add(Action("skip_consolidation", seat, f"Don't consolidate {con.unit_name}",
                       {"unit_id": con.unit_id}))


async def _stratagem_actions(session, game: Game, add, seat: int) -> None:
    gid = game.id
    player = g.game_service.player_at(game, seat)
    for stratagem in await g.usable_stratagems(gid, seat, session):
        if stratagem.game_action == "replace_secondary":
            for card in g.game_service.replaceable_secondaries(player):
                add(Action("use_stratagem", seat, f"{stratagem.name}: replace {card.mission.name}",
                           {"seat": seat, "stratagem_id": stratagem.id,
                            "target_secondary_id": card.id}))
            continue
        if stratagem.game_action in UNIT_TARGET_ACTIONS:
            for target in await g.stratagem_targets(gid, stratagem.id, seat, session):
                for choice in target.choices or [None]:
                    add(Action(
                        "use_stratagem", seat,
                        f"{stratagem.name} on {target.name}"
                        + (f": {choice.name}" if choice else "") + f" ({target.cp}CP)",
                        {"seat": seat, "stratagem_id": stratagem.id,
                         "target_unit_id": target.unit_id,
                         "target_choice_id": choice.id if choice else None},
                    ))
            continue
        # Any other: used as it stands (its effects are the calculator's, or
        # a person's to resolve).
        add(Action("use_stratagem", seat, f"{stratagem.name} ({stratagem.cp}CP)",
                   {"seat": seat, "stratagem_id": stratagem.id}))


# --- applying an action ---


def _pos(params: dict) -> list[ModelPositionIn]:
    if "positions" not in params:
        raise HTTPException(status_code=400, detail="this action needs params.positions")
    return [ModelPositionIn(**p) for p in params["positions"]]


async def _apply(session: AsyncSession, gid: int, a: AgentActionIn):
    p, seat = a.params, a.seat
    t = a.type
    if t == "start_game":
        return await g.start_game(gid, session)
    if t == "advance":
        return await g.advance(gid, session)
    if t == "set_formation":
        return await g.set_formation(gid, FormationIn(**p), session)
    if t == "declare_formations":
        return await g.declare_formations(gid, SeatIn(seat=seat), session)
    if t == "deploy":
        return await g.deploy_unit(gid, DeployUnitIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "roll_first_turn":
        return await g.roll_first_turn(gid, session)
    if t == "finish_teleport_homers":
        return await g.finish_teleport_homers(gid, TeleportHomerIn(seat=seat), session)
    if t == "phase_start_ability":
        return await g.use_phase_start(gid, PhaseStartIn(**p), session)
    if t in ("end_phase", "finish_phase_end"):
        # Declarations for the end of the phase (see phase_end.py): once
        # they're all made, the phase ends.
        game = await g._load_game(session, gid)
        if t == "end_phase":
            if seat != game.turn_seat or not phase_end_service.to_open(game):
                raise HTTPException(status_code=400, detail="there's nothing to declare first")
            phase_end_service.open(game)
        else:
            if phase_end_service.window_seat(game) != seat:
                raise HTTPException(status_code=400, detail="it isn't that player's to declare now")
            phase_end_service.finish(game, seat)
        if phase_end_service.window_seat(game) is None:
            return await g.advance(gid, session)
        return await g._commit_and_reload(session, gid)
    if t == "finish_phase_start":
        return await g.finish_phase_start(gid, SeatIn(seat=seat), session)
    if t == "scout_move":
        return await g.scout_move(gid, UnitPlacementIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "finish_scouts":
        return await g.finish_scouts(gid, SeatIn(seat=seat), session)
    if t == "emergency_disembark":
        return await g.emergency_disembark(gid, DeployUnitIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "battle_shock":
        return await g.take_battle_shock_test(
            gid, p["test_id"], BattleShockTakeIn(insane_bravery=p.get("insane_bravery", False)), session
        )
    if t == "mission_prompt":
        return await g.answer_mission_prompt(gid, p["prompt_id"], MissionAnswerIn(ids=p.get("ids", [])), session)
    if t == "claim_offer":
        return await g.claim_offer(gid, p["offer_id"], session)
    if t == "hold_offer":
        return await g.hold_offer(gid, p["offer_id"], session)
    if t == "place_reanimated":
        return await g.place_reanimated(gid, DeployUnitIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "round_start_choice":
        return await g.choose_rule_option(gid, RuleChoiceIn(**p), session)
    if t == "command_choice":
        return await g.choose_command_option(gid, CommandChoiceIn(**p), session)
    if t == "select_objective":
        return await g.select_objective(gid, ObjectiveSelectionIn(**p), session)
    if t == "rally":
        return await g.rally(gid, UnitAbilityTargetIn(**p), session)
    if t == "repair":
        return await g.repair(gid, RepairIn(**p), session)
    if t == "roll_advance":
        return await g.roll_advance(gid, UnitIdIn(unit_id=p["unit_id"]), session)
    if t == "move":
        return await g.move_unit(gid, UnitMoveIn(
            unit_id=p["unit_id"], kind=p["kind"], positions=_pos(p),
            take_to_skies=p.get("take_to_skies", False), mobile=p.get("mobile", False),
        ), session)
    if t == "reset_move":
        return await g.reset_move(gid, UnitIdIn(unit_id=p["unit_id"]), session)
    if t == "disembark":
        return await g.disembark(gid, DeployUnitIn(
            unit_id=p["unit_id"], positions=_pos(p), combat_disembark=p.get("combat_disembark", False)
        ), session)
    if t == "embark":
        return await g.embark(gid, EmbarkIn(**p), session)
    if t == "bring_in":
        return await g.bring_in(gid, DeployUnitIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "roll_reactive_move":
        return await g.roll_reactive_move(gid, UnitIdIn(unit_id=p["unit_id"]), session)
    if t == "reactive_move":
        return await g.make_reactive_move(gid, UnitPlacementIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "overwatch":
        return await g.fire_overwatch(gid, ShootIn(**p), session)
    if t == "shoot":
        return await g.shoot(gid, ShootIn(**p), session)
    if t == "shoot_scoot":
        return await g.shoot_scoot(gid, UnitPlacementIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "start_action":
        return await g.start_action(gid, ActionIn(**p), session)
    if t == "shooting_start":
        return await g.use_shooting_start(gid, UnitAbilityTargetIn(**p), session)
    if t == "psychic":
        return await g.use_psychic(gid, PsychicIn(**p), session)
    if t == "roll_charge":
        return await g.roll_charge(gid, UnitIdIn(unit_id=p["unit_id"]), session)
    if t == "reroll_advance":
        return await g.reroll_advance(gid, UnitIdIn(unit_id=p["unit_id"]), session)
    if t == "reroll_charge":
        return await g.reroll_charge(gid, UnitIdIn(unit_id=p["unit_id"]), session)
    if t == "charge":
        from app.schemas import ChargeIn

        return await g.make_charge(gid, ChargeIn(
            unit_id=p["unit_id"], target_unit_ids=p["target_unit_ids"], positions=_pos(p),
            take_to_skies=p.get("take_to_skies", False),
        ), session)
    if t == "pile_in":
        return await g.pile_in(gid, UnitPlacementIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "finish_piling_in":
        return await g.finish_piling_in(gid, SeatIn(seat=seat), session)
    if t == "fight":
        return await g.fight(gid, FightIn(**p), session)
    if t == "turn_end_reserves":
        return await g.declare_turn_end_reserves(gid, ResurrectionIn(**p), session)
    if t == "resurrect":
        return await g.declare_resurrection(gid, ResurrectionIn(**p), session)
    if t == "grant_formation":
        return await g.grant_formation_ability(gid, FormationGrantIn(**p), session)
    if t == "pass_fight":
        return await g.pass_fight(gid, SeatIn(seat=seat), session)
    if t == "consolidate":
        return await g.consolidate(gid, ConsolidateIn(
            unit_id=p["unit_id"], positions=_pos(p), pick_ids=p.get("pick_ids", [])
        ), session)
    if t == "skip_consolidation":
        return await g.skip_consolidation(gid, UnitIdIn(unit_id=p["unit_id"]), session)
    if t == "surge_move":
        return await g.make_surge_move(gid, UnitPlacementIn(unit_id=p["unit_id"], positions=_pos(p)), session)
    if t == "discard_secondary":
        return await g.discard_secondary(gid, p["card_id"], session)
    if t == "achieve_secondary":
        return await g.achieve_secondary(gid, p["card_id"], GameAchieveIn(points=p.get("points")), session)
    if t == "use_stratagem":
        return await g.use_stratagem(gid, GameStratagemIn(**{"seat": seat, **p}), session)
    raise HTTPException(status_code=400, detail=f"unknown action type {t!r}")


def _summary(result) -> str | None:
    # A short note of what the endpoint answered (e.g. a combat's damage).
    if result is None:
        return None
    data = result.model_dump() if hasattr(result, "model_dump") else result
    if isinstance(data, list):
        return f"{len(data)} entries"
    if not isinstance(data, dict):
        return str(data)[:200]
    combat = data.get("combat")
    if isinstance(combat, dict):
        return (
            f"{combat.get('hits', 0)} hits, {combat.get('total_damage', 0)} damage, "
            f"{combat.get('models_destroyed', 0)} models destroyed"
        )
    if "phase" in data and "battle_round" in data:
        return f"now round {data['battle_round']}, seat {data.get('turn_seat')}'s {data.get('phase')} ({data.get('status')})"
    return ", ".join(f"{k}" for k in list(data)[:6])


# --- endpoints ---


async def _decision(session: AsyncSession, game_id: int) -> dict:
    started = time.perf_counter()
    game = await g._load_game(session, game_id)
    rolls = game.rng_rolls
    waiting = await _waiting_for(session, game)
    actions = await _legal_actions(session, game, waiting)
    state = _state(game)
    # Nothing here changes the game (default placements are only checked) -
    # nor uses up its dice (shuffling where to try placing units).
    game.rng_rolls = rolls
    counts: dict[str, int] = {}
    for a in actions:
        counts[a.type] = counts.get(a.type, 0) + 1
    return {
        "state": state,
        "waiting_for": waiting,
        "actions": [{**asdict(a), "concrete": a.concrete} for a in actions],
        "counts": counts,
        "ms": round((time.perf_counter() - started) * 1000, 1),
    }


@router.get("/{game_id}/agent")
async def get_decision(game_id: int, session: AsyncSession = Depends(get_session)):
    # Whose decision the game is waiting on, and every legal action now.
    return await _decision(session, game_id)


async def _do(session: AsyncSession, game_id: int, action: AgentActionIn, listed_keys: set[str]):
    game = await g._load_game(session, game_id)
    live = game_store.get(game_id)
    state = _state(game)
    listed = _key(action.type, action.seat, action.params) in listed_keys
    started = time.perf_counter()
    ok, error, result = True, None, None
    # A rejected action leaves the game as it was.
    before = live.snapshot()
    try:
        result = await _apply(session, game_id, action)
    except HTTPException as exc:
        ok, error = False, str(exc.detail)
        live.restore(before)
    except Exception as exc:  # A crash: the log says so, with what it was.
        ok, error = False, f"{type(exc).__name__}: {exc}"
        live.restore(before)
    ms = round((time.perf_counter() - started) * 1000, 1)
    entry = {
        "id": len(live.agent_log) + 1,
        "at": datetime.now().isoformat(),
        "state": state,
        "seat": action.seat,
        "type": action.type,
        "params": action.params,
        "listed": listed,
        "ok": ok,
        "error": error,
        "result": _summary(result) if ok else None,
        "ms": ms,
        # Listed as legal, then rejected: the interface and the game disagree.
        "mismatch": listed and not ok,
    }
    live.agent_log.append(entry)
    return entry


def _log_out(entry: dict) -> dict:
    return entry


@router.post("/{game_id}/agent/apply")
async def apply_action(
    game_id: int, payload: AgentApplyIn, session: AsyncSession = Depends(get_session)
):
    # Applies an action (logged), and returns the new decision.
    decision = await _decision(session, game_id)
    keys = {_key(a["type"], a["seat"], a["params"]) for a in decision["actions"]}
    entry = await _do(session, game_id, payload.action, keys)
    return {"log": _log_out(entry), "decision": await _decision(session, game_id)}


@router.post("/{game_id}/agent/random")
async def random_action(
    game_id: int, seat: int | None = None, session: AsyncSession = Depends(get_session)
):
    # Applies one legal action picked at random - of the seat the game is
    # waiting on (or `seat`), among those that can be applied as listed. For
    # finding where the two disagree, or the game gets stuck.
    decision = await _decision(session, game_id)
    who = seat if seat is not None else decision["waiting_for"]["seat"]
    choices = [a for a in decision["actions"] if a["seat"] == who and a["concrete"]]
    if not choices:
        raise HTTPException(status_code=400, detail=f"seat {who} has no action that can be applied as listed")
    # (Advancing only when there's nothing else - or one time in five.)
    others = [a for a in choices if a["type"] != "advance"]
    pick = dice.choice(others if others and dice.chance() > 0.2 else choices)
    params = dict(pick["params"])
    if pick["placement"]:
        params["positions"] = pick["placement"]["default"]
    keys = {_key(a["type"], a["seat"], a["params"]) for a in decision["actions"]}
    entry = await _do(session, game_id, AgentActionIn(type=pick["type"], seat=who, params=params), keys)
    return {"log": _log_out(entry), "decision": await _decision(session, game_id)}


@router.get("/{game_id}/agent/log")
async def get_log(game_id: int, limit: int = 100, session: AsyncSession = Depends(get_session)):
    # The most recent actions applied through the agent interface, newest
    # first.
    await g._load_game(session, game_id)
    return list(reversed(game_store.get(game_id).agent_log))[:limit]
