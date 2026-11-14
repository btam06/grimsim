from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.models import Unit
from app.engine.state import Game, GameActOfFaith, GameMiracleGain, GamePlayer
from app.services import dice
from app.services.in_game import deployment
from app.services.list_building import enhancements as enhancement_rules

# The Adepta Sororitas' Acts of Faith, in a game.
#
# A player whose Army Faction is ADEPTA SORORITAS gains a Miracle dice at the
# start of each turn (theirs and their opponent's), and each time an ADEPTA
# SORORITAS unit of their army is destroyed. Its value is a D6 rolled then;
# the player's Miracle dice pool is those values (GamePlayer.miracle_dice).
#
# Each unit of theirs with the Acts of Faith ability can perform one Act of
# Faith a phase: before one of its rolls of the kinds in ROLLS, one dice from
# the pool is used instead of rolling one die of it (only one, even for a
# 2D6 roll): it counts as an unmodified roll of that value, and it's taken
# out of the pool. A die it substituted can't be re-rolled.
#
# Rolls in attacks (Hit, Wound, Damage for the attacker; Saving throws for
# the defender) are chosen before the attack is resolved: the first such
# roll the attack makes (with the chosen weapon, if one is) is the Miracle
# dice - see app/services/combat.py's Miracle. If the attack never makes
# that roll, the dice isn't used.
#
# Its detachments' rules about Miracle dice that need no decision:
#
# - Sacred Rites (Army of Faith): two Acts of Faith a phase per unit.
# - Saintly Example: its bearer destroyed, D3 more Miracle dice.
# - Litanies of Faith: at the start of its player's Command phase, its bearer
#   (on the battlefield) takes a Leadership test - passed, a Miracle dice.
# - Triptych of the Macharian Crusade: a Saving throw its bearer's unit
#   substitutes with a Miracle dice succeeds, whatever its value.
# - Faith and Fury, Divine Guidance (stratagems): the unit destroys an enemy
#   model with its attacks in the phase they're used on it - a Miracle dice
#   (once each use).
# - Blade of Saint Ellynor: each time its bearer's unit fights and destroys
#   an enemy model, a Miracle dice.

FACTION = "Adepta Sororitas"
KEYWORD = "ADEPTA SORORITAS"
ACTS_OF_FAITH = "Acts of Faith"

ADVANCE = "advance"
BATTLE_SHOCK = "battle_shock"
CHARGE = "charge"
DAMAGE = "damage"
HIT = "hit"
SAVE = "save"
WOUND = "wound"
ROLLS = (ADVANCE, BATTLE_SHOCK, CHARGE, DAMAGE, HIT, SAVE, WOUND)
ROLL_NAMES = {
    ADVANCE: "Advance roll",
    BATTLE_SHOCK: "Battle-shock test",
    CHARGE: "Charge roll",
    DAMAGE: "Damage roll",
    HIT: "Hit roll",
    SAVE: "Saving throw",
    WOUND: "Wound roll",
}
# The rolls an attacking unit's Act of Faith can be for, and a defending one's.
ATTACK_ROLLS = (HIT, WOUND, DAMAGE)
DEFENCE_ROLLS = (SAVE,)

START_OF_TURN = "start_of_turn"
UNIT_DESTROYED = "unit_destroyed"
SAINTLY_EXAMPLE = "Saintly Example"
LITANIES_OF_FAITH = "Litanies of Faith"
MACHARIAN_TRIPTYCH = "Triptych of the Macharian Crusade"
BLADE_OF_SAINT_ELLYNOR = "Blade of Saint Ellynor"
# Stratagems that gain a Miracle dice when the unit destroys an enemy model.
KILL_STRATAGEMS = ("Faith and Fury", "Divine Guidance")
SACRED_RITES = "Army of Faith"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _player(game: Game, seat: int) -> GamePlayer:
    return next(p for p in game.players if p.seat == seat)


def army_rule(player: GamePlayer) -> bool:
    # Whether the player's Army Faction is ADEPTA SORORITAS.
    army_list = player.army_list
    return army_list is not None and army_list.faction is not None and (
        army_list.faction.name == FACTION
    )


def has_ability(unit: Unit) -> bool:
    return any(
        a.name == ACTS_OF_FAITH for m in unit.unit_models for a in m.model.faction_abilities
    )


def _bearer(unit: Unit, enhancement: str):
    # The unit's model with that enhancement, if it has one.
    return next(
        (
            m
            for m in unit.unit_models
            if m.enhancement is not None and m.enhancement.name == enhancement
        ),
        None,
    )


def acts_per_phase(player: GamePlayer) -> int:
    # Sacred Rites (the Army of Faith detachment): two a phase.
    army_list = player.army_list
    if any(d.name == SACRED_RITES for d in getattr(army_list, "detachments", None) or []):
        return 2
    return 1


def _sororitas(unit: Unit) -> bool:
    return any(
        KEYWORD in enhancement_rules.model_keywords(unit, m) for m in unit.unit_models
    )


# --- gaining Miracle dice ---


def _gain(game: Game, player: GamePlayer, reason: str, unit_id: int | None = None) -> None:
    value = dice.randint(1, 6)
    player.miracle_dice.append(value)
    _record_gain(game, player, reason, unit_id, value)


def _record_gain(
    game: Game, player: GamePlayer, reason: str, unit_id: int | None, value: int
) -> None:
    # (A dice already in the pool - e.g. Simulacrum Imperialis' roll.)
    game.miracle_gains.append(
        GameMiracleGain(
            seat=player.seat,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            reason=reason,
            unit_id=unit_id,
            value=value,
        )
    )


def start_of_turn(game: Game) -> None:
    # The start of a turn: a Miracle dice each; then the start of its
    # player's Command phase - Litanies of Faith.
    for player in game.players:
        if army_rule(player):
            _gain(game, player, START_OF_TURN)
    player = _player(game, game.turn_seat)
    if not army_rule(player):
        return
    placed = deployment.positions(game)
    for unit in deployment.deployable_units(player):
        bearer = _bearer(unit, LITANIES_OF_FAITH)
        if bearer is None or bearer.id not in placed:
            continue
        # A Leadership test: 2D6, passed on at least its Leadership.
        if dice.randint(1, 6) + dice.randint(1, 6) >= bearer.model.leadership:
            _gain(game, player, LITANIES_OF_FAITH, unit.id)


def _destroyed(game: Game, unit: Unit) -> bool:
    # Every model of the unit destroyed (on the battlefield or off it).
    from app.services.in_game import casualties

    lost = casualties.damage(game)
    return bool(unit.unit_models) and all(
        m.id in lost and lost[m.id].destroyed for m in unit.unit_models
    )


def model_destroyed(game: Game, unit: Unit, unit_model=None) -> None:
    # One of the unit's models (`unit_model`, if known) was just destroyed:
    # if it had Saintly Example, its player gains D3 Miracle dice; and if
    # that was the last of an ADEPTA SORORITAS unit, one (once a unit).
    player = deployment.owner(game, unit)
    if not army_rule(player):
        return
    if (
        unit_model is not None
        and unit_model.enhancement is not None
        and unit_model.enhancement.name == SAINTLY_EXAMPLE
        and not any(
            g.reason == SAINTLY_EXAMPLE and g.unit_id == unit.id for g in game.miracle_gains
        )
    ):
        for _ in range(dice.randint(1, 3)):
            _gain(game, player, SAINTLY_EXAMPLE, unit.id)
    if not _sororitas(unit) or not _destroyed(game, unit):
        return
    if any(g.reason == UNIT_DESTROYED and g.unit_id == unit.id for g in game.miracle_gains):
        return
    _gain(game, player, UNIT_DESTROYED, unit.id)


def after_attacks(game: Game, unit: Unit, models_destroyed: int, fought: bool) -> None:
    # The unit's attacks (shooting, or fighting if `fought`) destroyed
    # `models_destroyed` enemy models: Miracle dice for Faith and Fury and
    # Divine Guidance (used on it this phase, once a use), and Blade of Saint
    # Ellynor (each time it fights).
    player = deployment.owner(game, unit)
    if models_destroyed <= 0 or not army_rule(player):
        return
    for use in player.stratagem_uses:
        if (
            use.stratagem is not None
            and use.stratagem.name in KILL_STRATAGEMS
            and use.target_unit_id == unit.id
            and use.battle_round == game.battle_round
            and use.turn_seat == game.turn_seat
            and use.phase == game.phase
        ):
            reason = f"{use.stratagem.name} #{use.id}"
            if not any(g.reason == reason for g in game.miracle_gains):
                _gain(game, player, reason, unit.id)
    if fought and _bearer(unit, BLADE_OF_SAINT_ELLYNOR) is not None:
        _gain(game, player, BLADE_OF_SAINT_ELLYNOR, unit.id)


# --- performing an Act of Faith ---


def _this_phase(game: Game, act: GameActOfFaith) -> bool:
    return (
        act.battle_round == game.battle_round
        and act.turn_seat == game.turn_seat
        and act.phase == game.phase
    )


def performed(game: Game, unit: Unit) -> list[GameActOfFaith]:
    # The Acts of Faith the unit performed this phase.
    return [a for a in game.acts_of_faith if a.unit_id == unit.id and _this_phase(game, a)]


def substituted(game: Game, unit: Unit, roll: str) -> bool:
    # Whether a Miracle dice substituted a die of the unit's `roll` this
    # phase (so the roll can't be re-rolled).
    return any(act.roll == roll for act in performed(game, unit))


def cant_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't perform an Act of Faith now, or None if it can.
    player = deployment.owner(game, unit)
    if not army_rule(player):
        return "its Army Faction isn't Adepta Sororitas"
    if not has_ability(unit):
        return "it doesn't have Acts of Faith"
    if not player.miracle_dice:
        return "there are no Miracle dice in the pool"
    from app.seeds.factions.adepta_sororitas import miracle_rules

    if miracle_rules.chaplet_used(game, player.seat):
        return "the Chaplet of Sacrifice has been used: it's the end of the Command phase"
    if len(performed(game, unit)) >= acts_per_phase(player):
        return (
            "it has already performed an Act of Faith this phase"
            if acts_per_phase(player) == 1
            else "it has already performed its Acts of Faith this phase"
        )
    return None


def able_units(game: Game, player: GamePlayer) -> list[int]:
    # The player's units that can perform an Act of Faith now.
    return [
        u.id for u in deployment.deployable_units(player) if cant_reason(game, u) is None
    ]


def check(game: Game, unit: Unit, roll: str, value: int) -> None:
    # Raises if the unit can't perform an Act of Faith for `roll`, using a
    # Miracle dice of `value`.
    if roll not in ROLLS:
        raise _bad_request(f"an Act of Faith can't be used for that roll ({roll})")
    if (reason := cant_reason(game, unit)) is not None:
        raise _bad_request(f"{unit.label} can't perform an Act of Faith: {reason}")
    if value not in deployment.owner(game, unit).miracle_dice:
        raise _bad_request(f"there's no Miracle dice of {value} in the pool")


def perform(game: Game, unit: Unit, roll: str, value: int) -> int:
    # The unit performs an Act of Faith: the Miracle dice of `value` is taken
    # from the pool to substitute a die of its `roll`. Its value.
    check(game, unit, roll, value)
    player = deployment.owner(game, unit)
    player.miracle_dice.remove(value)
    game.acts_of_faith.append(
        GameActOfFaith(
            seat=player.seat,
            unit_id=unit.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            phase=game.phase,
            roll=roll,
            value=value,
        )
    )
    # (e.g. a Cherub: a Miracle dice after it.)
    from app.seeds.factions.adepta_sororitas import unit_abilities

    unit_abilities.act_of_faith_performed(game, unit)
    return value


@dataclass
class AttackMiracle:
    # An Act of Faith for an attack (see app/services/combat.py): the unit
    # whose it is, the roll and the Miracle dice's value - the first such
    # roll (with the weapon `weapon_id`, if given) is that value. `used`
    # once it has been.
    unit: Unit
    roll: str
    value: int
    weapon_id: int | None = None
    used: bool = False
    # A Saving throw that succeeds whatever its value (Triptych of the
    # Macharian Crusade).
    auto_success: bool = False

    def applies(self, roll: str, weapon) -> bool:
        return (
            not self.used
            and roll == self.roll
            and (self.weapon_id is None or getattr(weapon, "id", None) == self.weapon_id)
        )

    def take(self) -> int:
        self.used = True
        return self.value


def attack_miracle(
    game: Game, unit: Unit, choice, allowed: tuple[str, ...]
) -> AttackMiracle | None:
    # The Act of Faith chosen for the unit's part in an attack (a
    # MiracleIn, or None), checked.
    if choice is None:
        return None
    if choice.roll not in allowed:
        raise _bad_request(
            f"{unit.label}'s Act of Faith here can only be for: "
            + ", ".join(ROLL_NAMES[r] for r in allowed)
        )
    check(game, unit, choice.roll, choice.value)
    return AttackMiracle(
        unit,
        choice.roll,
        choice.value,
        choice.weapon_id,
        auto_success=choice.roll == SAVE and _bearer(unit, MACHARIAN_TRIPTYCH) is not None,
    )


def spend(game: Game, miracle: AttackMiracle | None) -> None:
    # After the attack: the Miracle dice is spent if it was used.
    if miracle is not None and miracle.used:
        perform(game, miracle.unit, miracle.roll, miracle.value)
