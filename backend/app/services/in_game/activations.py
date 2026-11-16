from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException

from app.engine.state import Game
from app.models import Unit, UnitModel
from app.services import dice
from app.services.in_game import deployment
from app.services.in_game.deployment import TOLERANCE, gap

# Activated abilities, in a game: ones their player chooses to use, in a
# window, at most so often - e.g. Lord of the Storm (once a battle, at the end
# of its player's Command phase), Harbinger of Despair (once a turn, at the
# start of its player's phases), Gravitic Pulse (at the start of its
# opponent's Movement phase). Each is one entry of datasheet_abilities
# ACTIVATIONS:
#
#   {ability name: {
#       "phases": the phases it's used in ("any": every one),
#       "turn": "own" | "opponent" | "any" - whose turn,
#       "once": "battle" | "round" | "turn" | "phase" (per unit with it),
#       "target": None | "enemy" | "friendly" | "option",
#       "range": inches (from the model with it, or `from_unit`: its unit),
#       "visible": whether the target must be visible to it,
#       "keywords": the target's keywords (all of them),
#       "excluding": keywords the target can't have,
#       "engaged": the target must be within Engagement Range of it,
#       "effect": what it does (see EFFECTS below), and its settings,
#       "when": "start" | "end" - only at the start or end of the phase,
#   }}
#
# A start-of-phase ability is used in the phase's start step (see
# phase_start.py: the game waits for each player who could use one there,
# before anything else happens in the phase); an end-of-phase one in its end
# step (phase_end.py: ending the phase waits for them). One "at the start of
# the battle round" ("phases": "round_start") is used in that step, before
# the round's first turn (see battle_round.py) - and if it says to select
# one ("required"), the round can't start until it's been.
# What's been used is kept as marked units (see mission_state): kind USED +
# the ability, the unit with it.

USED = "activated:"
ENGAGEMENT_RANGE = 2.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _config() -> dict:
    from app.seeds import datasheet_abilities

    return datasheet_abilities.ACTIVATIONS


@dataclass
class Activation:
    # One the player could use now: the unit and model with it, the ability,
    # and what it could target (if anything).
    unit: Unit
    model: UnitModel
    ability: str
    how: dict
    targets: list[Unit] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    reason: str | None = None


def _base(game: Game, unit_model: UnitModel):
    p = deployment.positions(game)[unit_model.id]
    return deployment.base_at(unit_model, p.x, p.y, p.rotation)


def _bases(game: Game, unit: Unit) -> list:
    placed = deployment.positions(game)
    return [_base(game, m) for m in deployment.models_on_battlefield(game, unit) if m.id in placed]


def _used(game: Game, unit: Unit, ability: str, once: str, uses: int = 1) -> bool:
    # Whether it's been used up: once a battle (or `uses` times), round, turn
    # or phase.
    from app.services.in_game import mission_state

    kind = f"{USED}{ability}@{game.phase}" if once == "phase" else f"{USED}{ability}"
    marks = [m for m in mission_state.marked(game, kind) if m.unit_id == unit.id]
    if once == "battle":
        return len(marks) >= uses
    for m in marks:
        if once == "round" and m.battle_round == game.battle_round:
            return True
        if once in ("turn", "phase") and (m.battle_round, m.turn_seat) == (game.battle_round, game.turn_seat):
            return True
    return False


_PHASES = ("command", "movement", "shooting", "charge", "fight")


def _record(game: Game, seat: int, unit: Unit, ability: str) -> None:
    from app.services.in_game import mission_state

    mission_state.mark(game, seat, f"{USED}{ability}", unit.id)
    mission_state.mark(game, seat, f"{USED}{ability}@{game.phase}", unit.id)


def _window_reason(game: Game, unit: Unit, how: dict, steps: bool = True) -> str | None:
    # Why it can't be used now, as far as its timing goes - `steps`: checking
    # the start or end step it's used in is open for its player (not when
    # working out whether that step needs to open - see step_options).
    from app.services.in_game import battle_round

    phases = how.get("phases", "any")
    if phases == "round_start":
        if game.status != "in_progress" or game.phase != battle_round.START_OF_ROUND:
            return "it's used at the start of the battle round"
        return None
    if game.status != "in_progress" or game.phase not in _PHASES:
        return "the battle isn't in a phase"
    if phases == "pre_battle":
        # (After both players have deployed: here, before the first turn's
        # Movement phase.)
        if game.battle_round != 1 or game.turn_seat != game.first_seat or game.phase != "command":
            return "it's used after deployment, before the first turn"
        return None
    if phases != "any" and game.phase not in phases:
        return f"it's used in the {' or '.join(phases)} phase"
    seat = deployment.owner(game, unit).seat
    turn = how.get("turn", "own")
    if turn == "own" and seat != game.turn_seat:
        return "it's used in its player's turn"
    if turn == "opponent" and seat == game.turn_seat:
        return "it's used in its opponent's turn"
    if how.get("not_first_round") and game.battle_round == 1:
        return "it isn't used in the first battle round"
    if steps and (reason := _step_reason(game, seat, how.get("when"))) is not None:
        return reason
    return None


def _step_reason(game: Game, seat: int, when: str | None) -> str | None:
    from app.services.in_game import phase_end, phase_start

    if when == "start" and not phase_start.step_open(game, seat):
        return "it's used at the start of the phase"
    if when == "end" and not phase_end.step_open(game, seat):
        return "it's used at the end of the phase"
    return None


def step_options(game: Game, seat: int, when: str) -> list[Activation]:
    # The player's abilities for the start (or end) of this phase that they
    # could use in it - whether it's open yet or not.
    found = []
    for a in available(game, seat, steps=False):
        if a.how.get("when") == when and a.reason is None:
            found.append(a)
    return found


def missing_round_start(game: Game) -> list[str]:
    # The abilities for the start of the battle round that must be used
    # before its first turn (e.g. Triarch Abilities: select one), not yet.
    return [
        f"{a.unit.label}'s {a.ability}"
        for a in available(game)
        if a.how.get("phases") == "round_start" and a.how.get("required") and a.reason is None
    ]


def _targets(game: Game, unit: Unit, model: UnitModel, how: dict) -> list[Unit]:
    from app.seeds.factions.adepta_sororitas.unit_abilities import visible_enemies

    kind = how.get("target")
    if kind is None or kind == "option":
        return []
    seat = deployment.owner(game, unit).seat
    reach = how.get("range", 1000.0)
    sources = _bases(game, unit) if how.get("from_unit") else [_base(game, model)]
    if kind == "enemy":
        if how.get("visible"):
            pool = visible_enemies(game, unit, reach, None if how.get("from_unit") else [model])
        else:
            pool = [
                u
                for p in game.players
                if p.seat != seat
                for u in deployment.deployable_units(p)
                if any(gap(s, b) <= reach + TOLERANCE for s in sources for b in _bases(game, u))
            ]
    else:
        player = next(p for p in game.players if p.seat == seat)
        pool = [
            u
            for u in deployment.deployable_units(player)
            if (how.get("include_self") or u.id != unit.id)
            and (
                how.get("anywhere")
                or any(gap(s, b) <= reach + TOLERANCE for s in sources for b in _bases(game, u))
            )
        ]
    found = []
    for u in pool:
        keywords = {k.name for m in u.unit_models for k in m.model.keywords}
        if not set(how.get("keywords", ())) <= keywords or keywords & set(how.get("excluding", ())):
            continue
        if how.get("engaged") and not any(
            gap(s, b) <= ENGAGEMENT_RANGE + TOLERANCE for s in _bases(game, unit) for b in _bases(game, u)
        ):
            continue
        check = EFFECT_TARGET_CHECKS.get(how["effect"])
        if check is not None and check(game, unit, u, how) is not None:
            continue
        found.append(u)
    return found


def _models_with(game: Game, unit: Unit, ability: str) -> list[UnitModel]:
    return [
        m
        for m in deployment.models_on_battlefield(game, unit)
        if any(a.name == ability for a in m.model.abilities)
        or any(a.name == ability for g in m.wargear for a in g.abilities)
    ]


def available(game: Game, seat: int | None = None, steps: bool = True) -> list[Activation]:
    # Every activated ability a unit (of `seat`'s, if given) has on the
    # battlefield - with what it could target now, or why it can't be used.
    config = _config()
    found = []
    for player in game.players:
        if seat is not None and player.seat != seat:
            continue
        for unit in deployment.deployable_units(player):
            for name, how in sorted(config.items()):
                models = _models_with(game, unit, name)
                if not models:
                    continue
                model = models[0]
                activation = Activation(unit=unit, model=model, ability=name, how=how)
                activation.reason = _window_reason(game, unit, how, steps) or (
                    "it's been used"
                    if _used(game, unit, name, how.get("once", "battle"), how.get("uses", 1))
                    else None
                )
                if activation.reason is None and (check := EFFECT_CHECKS.get(how["effect"])):
                    activation.reason = check(game, unit, how)
                if activation.reason is None:
                    activation.targets = _targets(game, unit, model, how)
                    activation.options = list(how.get("options", ()))
                    if how.get("target") in ("enemy", "friendly") and not activation.targets:
                        activation.reason = "there's nothing it could target"
                found.append(activation)
    return found


def use(
    game: Game, unit: Unit, ability: str, target: Unit | None = None, option: str | None = None
) -> dict:
    # The unit uses the ability (on `target`, or choosing `option`) - if it can
    # now. What happened, for the panel.
    match = next(
        (a for a in available(game, deployment.owner(game, unit).seat) if a.unit.id == unit.id and a.ability == ability),
        None,
    )
    if match is None:
        raise _bad_request(f"{unit.label} has no {ability} to use")
    if match.reason is not None:
        raise _bad_request(f"{ability} can't be used: {match.reason}")
    how = match.how
    if how.get("target") in ("enemy", "friendly"):
        if target is None or target.id not in {t.id for t in match.targets}:
            raise _bad_request(f"{ability} needs one of the units it can target")
    if how.get("target") == "option" and option not in match.options:
        raise _bad_request(f"choose one of: {', '.join(match.options)}")
    outcome = EFFECTS[how["effect"]](game, match, target, option)
    _record(game, deployment.owner(game, unit).seat, unit, ability)
    return outcome or {}


# --- what they do ---


def _mortals_each_enemy(game: Game, a: Activation, target, option) -> dict:
    # A D6 for each enemy unit within range of the model: the mortal wounds of
    # the best band it reaches (e.g. Lord of the Storm: 2-5 D3, 6 D3+3).
    from app.services.combat import roll_dice
    from app.services.in_game import casualties

    source = _base(game, a.model)
    seat = deployment.owner(game, a.unit).seat
    hit = []
    for p in game.players:
        if p.seat == seat:
            continue
        for enemy in deployment.deployable_units(p):
            if not any(gap(source, b) <= a.how["range"] + TOLERANCE for b in _bases(game, enemy)):
                continue
            roll = dice.randint(1, 6)
            wounds = next((w for least, w in a.how["bands"] if roll >= least), None)
            if wounds:
                n = roll_dice(wounds)
                casualties.mortal_wounds(game, enemy, n, destroyed_by=a.unit)
                hit.append(f"{enemy.label}: {n}")
    return {"note": "; ".join(hit) or "no mortal wounds"}


def _unit_effect(game: Game, a: Activation, target, option) -> dict:
    # Something done to the target for a while (see unit_effects) - e.g.
    # Tectonic Reverberations: pinned, -2" Move and -2 to Charge rolls.
    from app.services.in_game import unit_effects

    e = a.how["unit_effect"]
    unit_effects.apply(
        game, target, a.ability, unit_effects._until(game, e.lasts),
        move=e.move, advance=e.advance, charge=e.charge, source_unit=a.unit, hit=e.hit,
        phase=game.phase if e.lasts == "this phase" else None,
    )
    if a.how.get("halve"):
        from app.services.in_game import mission_state

        mission_state.mark(game, deployment.owner(game, a.unit).seat, HALVED, target.id)
        if any(k.name == "FLY" for m in target.unit_models for k in m.model.keywords):
            mission_state.mark(game, deployment.owner(game, a.unit).seat, FLY_PULSED, target.id)
    return {"note": f"{target.label}: {unit_effects.describe(unit_effects.active(game, target)[-1])}"}


def _battle_shock(game: Game, a: Activation, target, option) -> dict:
    # The target takes a Battle-shock test (e.g. Harbinger of Despair: -1).
    from app.services.in_game import battle_shock

    if battle_shock.is_battle_shocked(game, target) or any(
        t.unit_id == target.id for t in battle_shock.pending(game)
    ):
        raise _bad_request(f"{target.label} is already Battle-shocked or has a test to take")
    battle_shock.require(game, target, a.ability, a.how.get("modifier", 0))
    return {"note": f"{target.label} takes a Battle-shock test"}


def _skill(game: Game, a: Activation, target, option) -> dict:
    # The target's weapons' Weapon Skill is improved by 1 until the end of the
    # phase (e.g. Accelerator Mandible).
    from app.services.in_game import unit_effects

    unit_effects.apply(
        game, target, a.ability, unit_effects.turn_index(game), melee_skill=-1,
        source_unit=a.unit, phase=game.phase,
    )
    return {"note": f"{target.label}: +1 Weapon Skill this phase"}


def _self_destruct(game: Game, a: Activation, target, option) -> dict:
    # One of the unit's models engaged with the target is destroyed; a D6 (+1
    # against a VEHICLE): 2-5, D3 mortal wounds to it; 6+, 3 (Self-destruction).
    from app.services.combat import roll_dice
    from app.services.in_game import casualties

    theirs = _bases(game, target)
    model = next(
        m
        for m in deployment.models_on_battlefield(game, a.unit)
        if any(gap(_base(game, m), b) <= ENGAGEMENT_RANGE + TOLERANCE for b in theirs)
    )
    left = casualties.wounds_remaining(game, a.unit).get(model.id, model.wounds)
    casualties._lose(game, model, left)
    roll = dice.randint(1, 6) + (
        1 if any(k.name == "VEHICLE" for m in target.unit_models for k in m.model.keywords) else 0
    )
    wounds = 3 if roll >= 6 else roll_dice("D3") if roll >= 2 else 0
    if wounds:
        casualties.mortal_wounds(game, target, wounds, destroyed_by=a.unit)
    return {"note": f"rolled {roll}: {wounds} mortal wounds to {target.label}"}


def _embark(game: Game, a: Activation, target, option) -> dict:
    # The target embarks within this TRANSPORT (e.g. Invasion Beams).
    from app.services.in_game import embarked

    if (reason := embarked.capacity_reason(game, target, a.unit)) is not None:
        raise _bad_request(f"{target.label} can't embark: {reason}")
    embarked._take_aboard(game, target, a.unit)
    return {"note": f"{target.label} embarks within {a.unit.label}"}


def _embark_target_check(game: Game, unit: Unit, target: Unit, how: dict) -> str | None:
    # Wholly within range of the transport, unengaged, and fitting.
    from app.services.in_game import battle_formations, embarked, movement

    if battle_formations.is_transport(target):
        return "a TRANSPORT"
    if movement.in_engagement_range(game, target):
        return "engaged"
    carrier = _bases(game, unit)
    reach = how.get("range", 6.0)
    from app.services.in_game.regions import base_wholly_within_of

    if not all(base_wholly_within_of(b, carrier, reach) for b in _bases(game, target)):
        return "not wholly within range"
    return embarked.capacity_reason(game, target, unit)


def _transport_empty(game: Game, unit: Unit, how: dict) -> str | None:
    from app.services.in_game import embarked

    if any(c.id == unit.id for _, c in embarked.embarked_units(game, deployment.owner(game, unit).seat)):
        return "there are models embarked within it"
    return None


def _engaged_check(game: Game, unit: Unit, how: dict) -> str | None:
    from app.services.in_game import movement

    if not movement.in_engagement_range(game, unit):
        return "it isn't within Engagement Range of an enemy unit"
    return None


def _empowered(game: Game, a: Activation, target, option) -> dict:
    # The unit's own boost until the end of the turn (e.g. Dark Ritual: it can
    # charge after Advancing, +1 to hit and wound) - see own_rules and
    # eligible_after.
    return {"note": f"{a.unit.label}: {a.how.get('describe', a.ability)} until the end of the turn"}


def _choose(game: Game, a: Activation, target, option) -> dict:
    # An option chosen until the next battle round (e.g. Triarch Abilities) -
    # kept as a mark of kind CHOSEN + option.
    from app.services.in_game import mission_state

    seat = deployment.owner(game, a.unit).seat
    for m in mission_state.marked(game, f"{CHOSEN}{a.ability}"):
        if m.unit_id == a.unit.id:
            m.ended = True
    mission_state.mark(game, seat, f"{CHOSEN}{a.ability}:{option}", a.unit.id)
    mission_state.mark(game, seat, f"{CHOSEN}{a.ability}", a.unit.id)
    return {"note": f"{a.unit.label}: {option} until the next battle round"}


def _gate(game: Game, a: Activation, target, option) -> dict:
    # Eternity Gate: the target (in Strategic Reserves or on the battlefield -
    # then taken off it, into Reserves) can arrive this phase wholly within
    # 6" of the Monolith, unengaged, even in the enemy deployment zone; it
    # can't charge this turn (see reinforcements.check_arrival, charging).
    from app.engine.state import GameBattleFormation
    from app.services.in_game import mission_state, reinforcements

    seat = deployment.owner(game, a.unit).seat
    if deployment.is_deployed(target, deployment.positions(game)):
        models = {m.id for m in target.unit_models}
        for position in [p for p in game.model_positions if p.unit_model_id in models]:
            game.model_positions.remove(position)
        formation = deployment.battle_formation(game, target)
        if formation is None:
            game.battle_formations.append(GameBattleFormation(unit_id=target.id, place="reserves"))
        else:
            formation.place = "reserves"
    elif not reinforcements.in_reserves(game, target):
        raise _bad_request(f"{target.label} isn't on the battlefield or in Strategic Reserves")
    mission_state.mark(game, seat, f"{GATE}{a.unit.id}", target.id)
    return {"note": f"{target.label} can arrive within 6\" of {a.unit.label}"}


def _gate_target_check(game: Game, unit: Unit, target: Unit, how: dict) -> str | None:
    from app.services.in_game import movement, reinforcements

    if deployment.is_deployed(target, deployment.positions(game)):
        if movement.in_engagement_range(game, target):
            return "engaged"
        return None
    return None if reinforcements.in_reserves(game, target) else "not available"


def _surrogate(game: Game, a: Activation, target, option) -> dict:
    # Surrogate Hosts: the target model (a CHARACTER in another unit) is
    # destroyed, ignoring rules triggered then, and this model's put in its
    # place. (Only while it isn't leading a unit: its unit is just it - the
    # attachment change isn't modelled.)
    host = next(
        m
        for m in deployment.models_on_battlefield(game, target)
        if any(k.name == "CHARACTER" for k in m.model.keywords)
    )
    placed = deployment.positions(game)
    there = placed[host.id]
    mine = placed[a.model.id]
    mine.x, mine.y, mine.rotation = there.x, there.y, there.rotation
    from app.engine.state import GameModelDamage
    from app.services.in_game import casualties

    record = casualties.damage(game).get(host.id)
    if record is None:
        record = GameModelDamage(unit_model_id=host.id, wounds_lost=0, destroyed=False)
        game.model_damage.append(record)
    record.wounds_lost, record.destroyed = host.wounds, True
    game.model_positions.remove(there)
    return {"note": f"{host.model.name} is destroyed; {a.model.model.name} takes its place"}


def _surrogate_check(game: Game, unit: Unit, how: dict) -> str | None:
    if len(deployment.models_on_battlefield(game, unit)) != 1:
        return "it's leading a unit (swapping attachments isn't modelled)"
    return None


def _surrogate_target_check(game: Game, unit: Unit, target: Unit, how: dict) -> str | None:
    hosts = [
        m
        for m in deployment.models_on_battlefield(game, target)
        if {"CHARACTER", "INFANTRY", "NECRONS"} <= {k.name for k in m.model.keywords}
        and not {"EPIC HERO", "SKORPEKH LORD"} & {k.name for k in m.model.keywords}
    ]
    return None if hosts else "no eligible CHARACTER model"


def _grand_illusion(game: Game, a: Activation, target, option) -> dict:
    # Grand Illusion (after deployment): the target goes into Strategic
    # Reserves, whatever the limit (redeploying it on the battlefield isn't
    # offered - set it up from Reserves instead).
    from app.engine.state import GameBattleFormation

    models = {m.id for m in target.unit_models}
    for position in [p for p in game.model_positions if p.unit_model_id in models]:
        game.model_positions.remove(position)
    formation = deployment.battle_formation(game, target)
    if formation is None:
        game.battle_formations.append(GameBattleFormation(unit_id=target.id, place="reserves"))
    else:
        formation.place = "reserves"
    return {"note": f"{target.label} is placed into Strategic Reserves"}


EFFECTS = {
    "mortals_each_enemy": _mortals_each_enemy,
    "unit_effect": _unit_effect,
    "battle_shock": _battle_shock,
    "skill": _skill,
    "self_destruct": _self_destruct,
    "embark": _embark,
    "empowered": _empowered,
    "choose": _choose,
    "gate": _gate,
    "surrogate": _surrogate,
    "grand_illusion": _grand_illusion,
}
# Checks on the unit using it, and on each target.
EFFECT_CHECKS = {
    "self_destruct": _engaged_check,
    "embark": _transport_empty,
    "surrogate": _surrogate_check,
}
EFFECT_TARGET_CHECKS = {
    "embark": _embark_target_check,
    "gate": _gate_target_check,
    "surrogate": _surrogate_target_check,
}

# Marks: a unit whose Move, Advance and Charge rolls are halved this turn, and
# one that can FLY that suffers D3 mortal wounds on a 4+ each time it ends a
# move (Gravitic Pulse); Triarch Abilities' choice; an Eternity Gate's
# traveller (kind GATE + the Monolith's unit id).
HALVED = "halved"
FLY_PULSED = "fly_pulsed"
CHOSEN = "chosen:"
GATE = "eternity_gate:"


def _this_turn_marks(game: Game, kind: str) -> list:
    from app.services.in_game import mission_state

    return [
        m
        for m in mission_state.marked(game, kind)
        if (m.battle_round, m.turn_seat) == (game.battle_round, game.turn_seat)
    ]


def halved(game: Game, unit: Unit) -> bool:
    # Whether its Move characteristic, and Advance and Charge rolls, are halved
    # this turn (Gravitic Pulse).
    return any(m.unit_id == unit.id for m in _this_turn_marks(game, HALVED))


def after_move(game: Game, unit: Unit) -> None:
    # It ended a move: a FLY unit hit by Gravitic Pulse rolls a D6 - on a 4+,
    # D3 mortal wounds.
    from app.services.combat import roll_dice
    from app.services.in_game import casualties

    if any(m.unit_id == unit.id for m in _this_turn_marks(game, FLY_PULSED)):
        if dice.randint(1, 6) >= 4:
            casualties.mortal_wounds(game, unit, roll_dice("D3"))


def empowered(game: Game, unit: Unit) -> list[str]:
    # The "empowered" abilities the unit used this turn (e.g. Dark Ritual).
    config = _config()
    return [
        name
        for name, how in config.items()
        if how["effect"] == "empowered"
        and any(m.unit_id == unit.id for m in _this_turn_marks(game, f"{USED}{name}"))
    ]


def own_rules(game: Game, unit: Unit) -> list:
    # Rules for the unit's attacks from what it used this turn (e.g. Dark
    # Ritual's +1 to hit and wound).
    config = _config()
    return [r for name in empowered(game, unit) for r in config[name].get("rules", ())]


def eligible_after(game: Game, unit: Unit, action: str, to: str) -> bool:
    # Whether what it used this turn lets it `to` after `action` (e.g. Dark
    # Ritual: declare a charge after Advancing).
    config = _config()
    return any(to in config[name].get("eligible_after", {}).get(action, ()) for name in empowered(game, unit))


def chosen(game: Game, unit: Unit, ability: str) -> str | None:
    # The option the unit chose for the ability this battle round (Triarch
    # Abilities).
    prefix = f"{CHOSEN}{ability}:"
    found = [
        m
        for m in game.marked_units
        if m.kind.startswith(prefix) and m.unit_id == unit.id and m.battle_round == game.battle_round
        and not m.ended
    ]
    return found[-1].kind[len(prefix):] if found else None


def gate_traveller(game: Game, unit: Unit) -> Unit | None:
    # The Monolith whose Eternity Gate the unit's travelling through this
    # turn, if any.
    for m in game.marked_units:
        if m.kind.startswith(GATE) and m.unit_id == unit.id and (m.battle_round, m.turn_seat) == (
            game.battle_round, game.turn_seat
        ):
            return deployment.find_unit(game, int(m.kind[len(GATE):]))
    return None
