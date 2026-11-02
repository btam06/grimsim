from __future__ import annotations

import math

from app.engine import context
from app.engine.state import PHASES, Game
from app.services import combat
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
    "use_stratagem", "phase_start_ability", "finish_phase_start", "grant_formation", "resurrect", "turn_end_reserves", "reroll_advance", "end_phase", "finish_phase_end", "other",
)
KEYWORDS = (
    "INFANTRY", "VEHICLE", "MONSTER", "CHARACTER", "FLY", "BATTLELINE", "TRANSPORT",
    "AIRCRAFT",
)
MOVE_KINDS = ("normal", "advance", "fall_back")

GLOBAL_SIZE = 8 + len(STATUSES) + len(PHASES) + 7 * MAX_OBJECTIVES
UNIT_SIZE = 35 + len(KEYWORDS)
ACTION_SIZE = len(ACTION_TYPES) + len(MOVE_KINDS) + 12
# Attacks that hit automatically (24.39).
TORRENT = "Torrent"


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
        # What it hits with: its ranged weapons', then its melee weapons' -
        # attacks (on average, all its models'), best Strength and AP, and
        # average Damage.
        for weapons in (
            [w for m in on or alive for w in shooting.ranged_weapons(m)],
            [w for m in on or alive for w in m.weapons if w.weapon_type == "melee"],
        ):
            row += [
                sum(combat.average_damage(w.attacks) for w in weapons) / 40,
                max((w.strength for w in weapons), default=0) / 12,
                -min((w.ap for w in weapons), default=0) / 4,
                (sum(combat.average_damage(w.damage) for w in weapons) / len(weapons)
                 if weapons else 0) / 4,
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
            # (Using a once-a-battle ability with it - e.g. Banner of Macragge.)
            float(bool(params.get("abilities"))),
        ]
        # An attack: the damage it's expected to do, and how much of the
        # target that is (its wounds left, and its models).
        damage = wounds_share = models_share = 0.0
        if action["type"] in ATTACKS and params.get("target_unit_id") is not None:
            damage, wounds_share, models_share = self.expected(
                params["unit_id"], params["target_unit_id"], set(params.get("weapon_ids") or ()),
                melee=action["type"] in MELEE_ATTACKS,
            )
        row += [damage / 20, wounds_share, models_share]
        return row

    def expected(
        self, unit_id: int, target_id: int, weapon_ids: set, melee: bool
    ) -> tuple[float, float, float]:
        # The damage the unit's chosen weapons are expected to do to the
        # target, as a share of its wounds left and of its models. Shooting:
        # the models that can fire each (in range, seeing it - see
        # app/services/in_game/shooting.py reach), at half range or not, and
        # the target's cover; melee: every model on the battlefield with one.
        # (An average, with the common weapon abilities - see _weapon_damage
        # - but not unit, army or stratagem rules.)
        game = self.game
        unit = deployment.find_unit(game, unit_id)
        target = deployment.find_unit(game, target_id)
        defenders = deployment.models_on_battlefield(game, target)
        if not defenders:
            return 0.0, 0.0, 0.0
        wounds_left = sum(casualties.wounds_remaining(game, target).values()) or 1
        keywords = {k.name for m in defenders for k in m.model.keywords}
        firing: list[tuple[object, bool]] = []
        in_cover = heavy = False
        if melee:
            firing = [
                (w, False)
                for m in deployment.models_on_battlefield(game, unit)
                for w in m.weapons
                if w.weapon_type == "melee" and w.id in weapon_ids
            ]
        else:
            reach = shooting.reach(game, unit, target)
            by_id = {
                m.id: {w.id: w for w in shooting.ranged_weapons(m)}
                for m in deployment.models_on_battlefield(game, unit)
            }
            firing = [
                (by_id[model_id][weapon_id], half)
                for model_id, weapons in reach.firing.items()
                for weapon_id, half in weapons.items()
                if weapon_id in weapon_ids and weapon_id in by_id.get(model_id, {})
            ]
            if not firing and shooting.move_status(game, unit).advanced:
                # (Advanced: its Assault weapons, as reach doesn't know them.)
                firing = [
                    (w, False) for m in deployment.models_on_battlefield(game, unit)
                    for w in shooting.ranged_weapons(m) if w.id in weapon_ids
                ]
            in_cover = reach.in_cover
            heavy = game.phase == "shooting" and shooting.move_status(game, unit).moved_less_than_3
        damage = kills = 0.0
        per_model = defenders[0].wounds
        for weapon, half in firing:
            dealt = _weapon_damage(
                weapon, defenders[0].model, keywords, len(defenders), half, in_cover, heavy
            )
            capped = min(dealt[1], per_model)
            damage += dealt[0] * capped
            kills += dealt[0] * capped / per_model
        return damage, min(1.0, damage / wounds_left), min(1.0, kills / len(defenders))


ATTACKS = ("shoot", "overwatch", "fight")
MELEE_ATTACKS = ("fight",)


def _roll(needed: int, natural_one: bool = True) -> float:
    # The chance of rolling `needed` or more on a D6 - a 6 always succeeding
    # and (with `natural_one`, for hits and wounds) a 1 always failing.
    chance = max(0.0, min(1.0, (7 - needed) / 6))
    return max(1 / 6, min(5 / 6, chance)) if natural_one else min(5 / 6, chance)


def _weapon_damage(
    weapon, defender, keywords: set[str], models: int, half: bool, in_cover: bool, heavy: bool
) -> tuple[float, float]:
    # One model's attacks with the weapon against a defender like `defender`
    # (its unit `models` strong, with `keywords`): (how many get through -
    # unsaved, or mortal - on average, and the damage each does). With the
    # weapon abilities the engine knows (app/seeds/weapon_abilities.py):
    # Torrent, Sustained N, Lethal Hits, Devastating Wounds, Rapid Fire N and
    # Melta N (at half range), Blast, Heavy, Anti-X N+, Twin-linked, Ignores
    # Cover - and the benefit of cover (a ranged attack's BS 1 worse, 13.08).
    names = {a.name for a in getattr(weapon, "abilities", [])}

    def number(prefix: str) -> int:
        for name in names:
            if name.startswith(prefix) and name[len(prefix):].strip().isdigit():
                return int(name[len(prefix):])
        return 0

    attacks = combat.average_damage(weapon.attacks)
    attacks += number("Rapid Fire ") if half else 0
    attacks += models // 5 if "Blast" in names else 0
    if TORRENT in names or not weapon.skill:
        hits, criticals = attacks, 0.0
    else:
        modifier = (1 if heavy and "Heavy" in names else 0) - (
            1 if in_cover and "Ignores Cover" not in names else 0
        )
        hits = attacks * _roll(weapon.skill - max(-1, min(1, modifier)))
        criticals = attacks / 6
    hits += criticals * number("Sustained ")
    # Wounds: critical hits wound outright with Lethal Hits; a 6 - or, with
    # Anti-X N+ against an X, N or more - is a critical wound.
    automatic = criticals if "Lethal Hits" in names else 0.0
    rolled = hits - automatic
    critical_on = 6
    for name in names:
        if name.startswith("Anti-") and name.endswith("+"):
            kind, _, needed = name[5:-1].rpartition(" ")
            if kind.upper() in keywords and needed.isdigit():
                critical_on = min(critical_on, int(needed))
    needed = min(combat.wound_threshold(weapon.strength, defender.toughness), critical_on)
    hit_wound, hit_critical = _roll(needed), _roll(critical_on)
    if "Twin-linked" in names:
        hit_wound += (1 - hit_wound) * hit_wound
        hit_critical += (1 - hit_wound) * hit_critical
    wounds = rolled * hit_wound + automatic
    mortal = rolled * hit_critical if "Devastating Wounds" in names else 0.0
    save = defender.save - weapon.ap
    if defender.invulnerable is not None:
        save = min(save, defender.invulnerable)
    through = (wounds - mortal) * (1 - _roll(save, natural_one=False)) + mortal
    if defender.feel_no_pain is not None:
        through *= 1 - _roll(defender.feel_no_pain, natural_one=False)
    each = combat.average_damage(weapon.damage) + (number("Melta ") if half else 0)
    return through, each


def _stratagem_cp(stratagem_id) -> float:
    if stratagem_id is None:
        return 0.0
    stratagem = context.catalog().get("Stratagem", stratagem_id)
    return float(stratagem.cp) if stratagem is not None else 0.0
