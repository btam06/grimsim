from __future__ import annotations

import math

from app.engine import context
from app.engine.state import PHASES, Game
from app.services.in_game import (
    battle_shock,
    casualties,
    deployment,
    movement,
    objectives,
    shooting,
)

# A game as numbers, for machine learning (see app/engine/env.py): what one
# player sees - the game as a whole, each unit in it, and each legal action -
# as lists of floats, every list for one kind of thing the same length.
#
# It's from the player's side: their units come first, then their
# opponent's, and the defender sees the battlefield turned round (x -> 60 -
# x, y -> 44 - y), so each player's own deployment zone is always where the
# attacker's is. Distances are in inches over the battlefield's width (60"),
# counts and characteristics over a typical most - roughly 0 to 1.

BOARD_WIDTH, BOARD_HEIGHT = 60.0, 44.0
# Unit slots per side: units past these are left out (an army list rarely
# has more than 20).
MAX_UNITS = 30
MAX_OBJECTIVES = 8
STATUSES = ("setup", "in_progress", "finished")
# Every action type the agent interface lists (see app/routers/agent.py) -
# any other counts as "other".
ACTION_TYPES = (
    "start_game", "advance", "set_formation", "declare_formations", "deploy",
    "roll_first_turn", "finish_teleport_homers", "scout_move", "finish_scouts",
    "emergency_disembark", "battle_shock", "mission_prompt", "claim_offer", "hold_offer",
    "place_reanimated", "round_start_choice", "command_choice", "select_objective", "rally",
    "repair", "roll_advance", "move", "reset_move", "disembark", "embark", "bring_in",
    "roll_reactive_move", "reactive_move", "overwatch", "shoot", "shoot_scoot",
    "start_action", "shooting_start", "psychic", "roll_charge", "reroll_charge", "charge",
    "pile_in", "finish_piling_in", "fight", "pass_fight", "consolidate",
    "skip_consolidation", "surge_move", "discard_secondary", "achieve_secondary",
    "use_stratagem", "other",
)
KEYWORDS = (
    "INFANTRY", "VEHICLE", "MONSTER", "CHARACTER", "FLY", "BATTLELINE", "TRANSPORT",
    "AIRCRAFT",
)
MOVE_KINDS = ("normal", "advance", "fall_back")

GLOBAL_SIZE = 8 + len(STATUSES) + len(PHASES) + 7 * MAX_OBJECTIVES
UNIT_SIZE = 27 + len(KEYWORDS)
ACTION_SIZE = len(ACTION_TYPES) + len(MOVE_KINDS) + 8


def observe(game: Game, seat: int, actions: list[dict]) -> dict:
    # What the player sees, with the legal `actions` (the agent interface's
    # dicts - see app/routers/agent.py):
    #   global:        GLOBAL_SIZE floats
    #   units:         2 * MAX_UNITS rows of UNIT_SIZE floats (theirs, then
    #                  their opponent's; empty slots all 0)
    #   unit_mask:     1 for each slot with a unit in it, else 0
    #   actions:       a row of ACTION_SIZE floats per action
    #   action_units:  the slot of the unit each action is for (-1: none)
    #   action_targets: the slot of the unit each targets (-1: none)
    # (Read inside the game's context - see app/engine/context.py.)
    view = _View(game, seat)
    units = [[0.0] * UNIT_SIZE for _ in range(2 * MAX_UNITS)]
    mask = [0] * (2 * MAX_UNITS)
    for unit, slot in view.slots.items():
        units[slot] = view.unit_row(unit)
        mask[slot] = 1
    return {
        "seat": seat,
        "global": view.global_row(),
        "units": units,
        "unit_mask": mask,
        "actions": [view.action_row(a) for a in actions],
        "action_units": [view.slot_of(a["params"].get("unit_id")) for a in actions],
        "action_targets": [view.slot_of(a["params"].get("target_unit_id")) for a in actions],
    }


def vp(game: Game, seat: int) -> int:
    player = next(p for p in game.players if p.seat == seat)
    return sum(score.points for score in player.scores)


class _View:
    def __init__(self, game: Game, seat: int) -> None:
        self.game = game
        self.seat = seat
        # The defender sees it turned round.
        self.flip = seat != game.attacker_seat
        self.placed = deployment.positions(game)
        self.lost = casualties.damage(game)
        self.shocked = battle_shock.battle_shocked_ids(game)
        self.objectives = [
            (o.objective.x, o.objective.y, o) for o in objectives.control(game, live=True)
        ][:MAX_OBJECTIVES]
        self.slots: dict = {}
        self.by_id: dict[int, int] = {}
        for player in game.players:
            first = 0 if player.seat == seat else MAX_UNITS
            for i, unit in enumerate(deployment.deployable_units(player)[:MAX_UNITS]):
                self.slots[unit] = first + i
                self.by_id[unit.id] = first + i

    def xy(self, x: float, y: float) -> tuple[float, float]:
        if self.flip:
            x, y = BOARD_WIDTH - x, BOARD_HEIGHT - y
        return x / BOARD_WIDTH, y / BOARD_HEIGHT

    def slot_of(self, unit_id) -> int:
        return self.by_id.get(unit_id, -1) if isinstance(unit_id, int) else -1

    def global_row(self) -> list[float]:
        game, seat = self.game, self.seat
        other = next((p.seat for p in game.players if p.seat != seat), None)
        me = next(p for p in game.players if p.seat == seat)
        them = next((p for p in game.players if p.seat == other), None)
        row = [
            (game.battle_round or 0) / 5,
            float(game.turn_seat == seat),
            float(game.first_seat == seat),
            float(game.attacker_seat == seat),
            me.cp / 10,
            (them.cp if them else 0) / 10,
            vp(game, seat) / 100,
            (vp(game, other) if them else 0) / 100,
        ]
        row += [float(game.status == s) for s in STATUSES]
        row += [float(game.phase == p) for p in PHASES]
        for i in range(MAX_OBJECTIVES):
            if i < len(self.objectives):
                x, y, control = self.objectives[i]
                row += [
                    1.0,
                    *self.xy(x, y),
                    float(control.live_controller == seat),
                    float(control.live_controller == other),
                    control.oc.get(seat, 0) / 20,
                    control.oc.get(other, 0) / 20,
                ]
            else:
                row += [0.0] * 7
        return row

    def unit_row(self, unit) -> list[float]:
        game = self.game
        models = deployment.unit_models(unit)
        alive = [
            m for m in models if not (m.id in self.lost and self.lost[m.id].destroyed)
        ]
        on = [m for m in alive if m.id in self.placed]
        formation = deployment.battle_formation(game, unit)
        place = formation.place if formation is not None else None
        first = (on or alive or models)[0].model
        wounds = sum(m.wounds for m in models) or 1
        left = sum(casualties.wounds_remaining(game, unit).values()) if on else 0
        if on:
            xs = [self.placed[m.id].x for m in on]
            ys = [self.placed[m.id].y for m in on]
            x, y = self.xy(sum(xs) / len(xs), sum(ys) / len(ys))
            nearest = min(
                (math.dist((sum(xs) / len(xs), sum(ys) / len(ys)), (ox, oy))
                 for ox, oy, _ in self.objectives),
                default=BOARD_WIDTH,
            ) / BOARD_WIDTH
        else:
            x = y = 0.0
            nearest = 1.0
        keywords = {k.name for m in models for k in m.model.keywords}
        ranged = [w.range for m in on or alive for w in shooting.ranged_weapons(m)]
        melee = any(w.weapon_type == "melee" for m in on or alive for w in m.weapons)
        status = shooting.move_status(game, unit) if on else shooting.MoveStatus()
        shot = any(
            s.unit_id == unit.id
            and s.battle_round == game.battle_round
            and s.turn_seat == game.turn_seat
            for s in game.unit_shots
        )
        row = [
            float(self.slots[unit] < MAX_UNITS),
            float(bool(on)),
            float(place == "reserves"),
            float(place == "embarked"),
            float(not alive),
            x,
            y,
            len(alive) / max(len(models), 1),
            len(alive) / 20,
            left / wounds,
            first.movement / 20,
            first.toughness / 12,
            first.save / 7,
            (first.invulnerable or 7) / 7,
            first.wounds / 20,
            first.leadership / 10,
            first.oc / 5,
            unit.points / 500,
            max(ranged, default=0) / 48,
            float(melee),
            float(unit.id in self.shocked),
            float(bool(on) and movement.in_engagement_range(game, unit)),
            float(status.advanced),
            float(status.fell_back),
            float(status.remained_stationary),
            float(shot),
            nearest,
        ]
        row += [float(k in keywords) for k in KEYWORDS]
        return row

    def action_row(self, action: dict) -> list[float]:
        params = action["params"]
        kind = action["type"] if action["type"] in ACTION_TYPES else "other"
        row = [float(kind == t) for t in ACTION_TYPES]
        row += [float(params.get("kind") == k) for k in MOVE_KINDS]
        # Where a placement puts the unit: the middle of its models, and how
        # far that is from where they are now.
        default = (action.get("placement") or {}).get("default") or []
        if default:
            cx = sum(p["x"] for p in default) / len(default)
            cy = sum(p["y"] for p in default) / len(default)
            now = [self.placed[p["unit_model_id"]] for p in default
                   if p["unit_model_id"] in self.placed]
            moved = (
                math.dist(
                    (cx, cy),
                    (sum(p.x for p in now) / len(now), sum(p.y for p in now) / len(now)),
                ) / 24
                if now
                else 0.0
            )
            row += [1.0, *self.xy(cx, cy), moved]
        else:
            row += [0.0, 0.0, 0.0, 0.0]
        weapons = (
            len(params.get("weapon_ids") or [])
            + len(params.get("enhancement_weapon_ids") or [])
            + len(params.get("firing_deck_weapon_ids") or [])
        )
        row += [
            weapons / 10,
            float(bool(params.get("take_to_skies") or params.get("mobile"))),
            float(" towards " in action.get("label", "")),
            _stratagem_cp(params.get("stratagem_id")) / 3,
        ]
        return row


def _stratagem_cp(stratagem_id) -> float:
    if stratagem_id is None:
        return 0.0
    stratagem = context.catalog().get("Stratagem", stratagem_id)
    return float(stratagem.cp) if stratagem is not None else 0.0
