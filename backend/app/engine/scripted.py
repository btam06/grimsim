from __future__ import annotations

import math
import random

from app.engine import context
from app.engine.env import Decision
from app.engine.features import _View
from app.services.in_game import charging, deployment, objectives, shooting
from app.services.in_game.movement import ENGAGEMENT_RANGE

# A scripted player: rules of thumb, no learning - an opponent better than
# random play, and a teacher to start training from (see ml/imitate.py):
#
#     ml/.venv/bin/python -m ml.ppo saves/1/setup.json \
#         --opponent app.engine.scripted:scripted
#
# Each legal action gets a score and the best is taken (ties at random).
# Moving the game on (advance, end_phase) scores 0, so anything below that is
# only taken when it's all there is. In short: deploy melee units forward,
# the first unit on the home objective, the rest anywhere; move towards the
# closest objective it doesn't hold (melee units towards the closest enemy),
# one unit staying put on each objective held; shoot and fight for the most
# expected damage, finishing units off first; charge when the roll's likely;
# bring in Reserves; take the default for everything else; no stratagems.

# What each action type scores, when nothing more particular applies.
SCORES = {
    "start_game": 1.0, "roll_first_turn": 1.0, "deploy": 1.0, "declare_formations": 0.5,
    "set_formation": -1.0, "grant_formation": 0.5, "scout_move": -1.0,
    "emergency_disembark": 3.0, "place_reanimated": 3.0, "bring_in": 3.0,
    "battle_shock": 1.0, "mission_prompt": 1.0, "claim_offer": 1.0, "hold_offer": 0.5,
    "round_start_choice": 1.0, "command_choice": 1.0, "select_objective": 1.0,
    "rally": 1.5, "repair": 1.5, "resurrect": 1.5, "turn_end_reserves": -1.0,
    "shooting_start": 1.0, "phase_start_ability": 1.0, "psychic": 1.0,
    "disembark": 1.5, "embark": -1.0, "reset_move": -5.0, "reroll_advance": -1.0,
    "shoot_scoot": -1.0, "start_action": 0.3, "reroll_charge": 0.5,
    "pile_in": 2.0, "consolidate": 1.5, "surge_move": 0.5,
    "roll_reactive_move": 0.5, "reactive_move": 0.5,
    "achieve_secondary": 3.0, "discard_secondary": -0.5, "use_stratagem": -0.5,
    "pass_fight": 0.0, "skip_consolidation": 0.0,
}


def scripted(decision: Decision, rng: random.Random) -> int:
    with context.bound(decision.live):
        player = _Player(decision.live.game, decision.seat)
        scores = [player.score(a) + rng.random() * 0.01 for a in decision.actions]
    return max(range(len(scores)), key=scores.__getitem__)


def _chance_2d6(needed: float) -> float:
    # The chance of rolling `needed` or more on 2D6.
    n = math.ceil(needed)
    return sum(1 for a in range(1, 7) for b in range(1, 7) if a + b >= n) / 36


class _Player:
    def __init__(self, game, seat: int) -> None:
        self.game, self.seat = game, seat
        self.view = _View(game, seat)
        self.control = objectives.control(game, live=True)

    def score(self, action: dict) -> float:
        kind, params = action["type"], action["params"]
        if kind in ("shoot", "overwatch", "fight"):
            return self.attack(action)
        if kind == "move":
            return self.move(action)
        if kind == "deploy":
            return self.deploy(params)
        if kind == "roll_advance":
            return 0.5 if self.melee(params["unit_id"]) else -1.0
        if kind == "roll_charge":
            return self.charge_roll(params["unit_id"])
        if kind == "charge":
            return 3.0
        if kind == "battle_shock" and params.get("insane_bravery"):
            return 0.0
        if kind == "mission_prompt" and not params.get("ids"):
            return 0.5
        if kind == "round_start_choice" and params.get("option") is None:
            return -1.0
        return SCORES.get(kind, 0.0)

    # --- units ---

    def unit(self, unit_id: int):
        return deployment.find_unit(self.game, unit_id)

    def melee(self, unit_id: int) -> bool:
        # A unit with no ranged weapon of 12" or more: it fights. (All its
        # models, as it's deployed too.)
        models = deployment.unit_models(self.unit(unit_id))
        return not any(
            (w.range or 0) >= 12 for m in models for w in shooting.ranged_weapons(m)
        )

    def centre(self, unit) -> tuple[float, float] | None:
        placed = deployment.positions(self.game)
        points = [(placed[m.id].x, placed[m.id].y) for m in unit.unit_models if m.id in placed]
        if not points:
            return None
        return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)

    # --- moving ---

    def holding(self, unit) -> bool:
        # Whether the unit's holding an objective the player controls: it's
        # within 3" of it, the closest of their units to it (the others can
        # move on).
        here = self.centre(unit)
        if here is None:
            return False
        for c in self.control:
            point = (c.objective.x, c.objective.y)
            if c.live_controller != self.seat or math.dist(here, point) >= 3:
                continue
            closest = min(
                (
                    (math.dist(centre, point), u.id)
                    for u in self.own_units()
                    if (centre := self.centre(u)) is not None
                ),
                default=None,
            )
            if closest is not None and closest[1] == unit.id:
                return True
        return False

    def own_units(self) -> list:
        player = next(p for p in self.game.players if p.seat == self.seat)
        return [
            u for u in deployment.deployable_units(player)
            if deployment.models_on_battlefield(self.game, u)
        ]

    def goal(self, point: tuple[float, float]) -> tuple[float, float] | None:
        # The closest objective the player doesn't control.
        open_ = [
            (c.objective.x, c.objective.y) for c in self.control if c.live_controller != self.seat
        ]
        return min(open_, key=lambda o: math.dist(point, o), default=None)

    def closest_enemy(self, unit) -> tuple[float, float] | None:
        enemies = [
            e for e in charging.enemy_units(self.game, unit)
            if deployment.models_on_battlefield(self.game, e)
        ]
        if not enemies:
            return None
        closest = min(enemies, key=lambda e: charging.distance(self.game, unit, e))
        return self.centre(closest)

    def move(self, action: dict) -> float:
        # Progress towards where it's going, per 4": the closest objective its
        # player doesn't hold - or for a melee unit, the closest enemy.
        # Staying put (not moving) to hold an objective.
        unit = self.unit(action["params"]["unit_id"])
        default = (action.get("placement") or {}).get("default") or []
        now = self.centre(unit)
        if not default or now is None:
            return -1.0
        if self.holding(unit):
            return -1.0
        after = (
            sum(p["x"] for p in default) / len(default),
            sum(p["y"] for p in default) / len(default),
        )
        target = self.closest_enemy(unit) if self.melee(unit.id) else None
        target = target or self.goal(now)
        if target is None:
            return -1.0
        progress = math.dist(now, target) - math.dist(after, target)
        if progress <= 0:
            return -1.0
        # (An Advance gives up shooting: only for melee units.)
        if action["params"].get("kind") == "advance" and not self.melee(unit.id):
            return -1.0
        return 1.0 + progress / 4

    # --- deploying ---

    def deploy(self, params: dict) -> float:
        # Melee units forward; the first unit on the home objective; the rest
        # anywhere (at random).
        where = params.get("where", "")
        if self.melee(params["unit_id"]):
            return 1.3 if where == "forward" else 1.0
        if where == "on its home objective" and not any(
            self.holding_home(u) for u in self.own_units()
        ):
            return 1.2
        return 1.0

    def holding_home(self, unit) -> bool:
        here = self.centre(unit)
        return here is not None and any(
            objectives.is_home(self.game, c.objective, self.seat)
            and math.dist(here, (c.objective.x, c.objective.y)) < 3
            for c in self.control
        )

    # --- charging and attacking ---

    def charge_roll(self, unit_id: int) -> float:
        # Roll when it's likely to make it: a melee unit at a third's chance,
        # any other at four in five.
        unit = self.unit(unit_id)
        enemies = charging.enemy_units(self.game, unit)
        gap = min((charging.distance(self.game, unit, e) for e in enemies), default=math.inf)
        chance = _chance_2d6(gap - ENGAGEMENT_RANGE)
        return 2.0 if chance >= (1 / 3 if self.melee(unit_id) else 0.8) else -1.0

    def attack(self, action: dict) -> float:
        # The share of the target it's expected to destroy (its wounds, its
        # models) - a unit finished off most of all. Overwatch costs CP: only
        # for a good shot.
        params = action["params"]
        if params.get("target_unit_id") is None:
            return 2.0
        damage, wounds, models = self.view.expected(
            params["unit_id"], params["target_unit_id"], set(params.get("weapon_ids") or ()),
            melee=action["type"] == "fight",
        )
        value = 2.0 + 3 * wounds + models + (1.0 if wounds >= 1 else 0.0) + damage / 100
        if action["type"] == "overwatch":
            return value - 3.0 if wounds >= 0.25 else -1.0
        return value
