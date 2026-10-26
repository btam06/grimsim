from __future__ import annotations

from app.combat_rules import Rule
from app.combat_rules.conditions import ALWAYS
from app.combat_rules.effects import REROLL_FAILED_WOUNDS
from app.models import Game, GameFireSupport, Unit
from app.services.in_game import deployment

# Fire Support (e.g. a Skorpius Dunerider): in its player's Shooting phase,
# after the transport has shot, one enemy unit it scored hits against is
# picked out (the one it shot at - each unit shoots one target here). Until
# the end of the phase, attacks against that unit by models that disembarked
# from the transport this turn can re-roll the Wound roll.

FIRE_SUPPORT = "Fire Support"
REROLL_WOUNDS = Rule(
    conditions=(ALWAYS,),
    effects=(REROLL_FAILED_WOUNDS,),
    description="Re-roll Wound rolls against the unit its transport picked out (Fire Support).",
)


def _this_turn(game: Game, record) -> bool:
    return record.battle_round == game.battle_round and record.turn_seat == game.turn_seat


def has_it(unit: Unit) -> bool:
    return any(a.name == FIRE_SUPPORT for m in unit.unit_models for a in m.model.abilities)


def after_shooting(game: Game, transport: Unit, target: Unit, hits: int) -> None:
    # The transport shot: if it has Fire Support and scored hits, in its
    # player's Shooting phase, the target is picked out.
    if (
        game.phase == "shooting"
        and deployment.owner(game, transport).seat == game.turn_seat
        and hits > 0
        and has_it(transport)
    ):
        game.fire_support_targets.append(
            GameFireSupport(
                transport_unit_id=transport.id,
                target_unit_id=target.id,
                battle_round=game.battle_round,
                turn_seat=game.turn_seat,
            )
        )


def rules(game: Game, unit: Unit, target: Unit) -> list[Rule]:
    # The re-roll the unit gets attacking the target, if a transport it
    # disembarked from this turn picked it out this Shooting phase.
    if game.phase != "shooting":
        return []
    transports = {
        d.transport_unit_id
        for d in game.disembarkations
        if d.unit_id == unit.id and _this_turn(game, d)
    }
    picked = any(
        f.transport_unit_id in transports and f.target_unit_id == target.id
        for f in game.fire_support_targets
        if _this_turn(game, f)
    )
    return [REROLL_WOUNDS] if picked else []
