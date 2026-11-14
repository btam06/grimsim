from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.state import Game
from app.routers import games as g
from app.seeds.factions.adepta_sororitas import acts_of_faith, miracle_rules, unit_abilities
from app.services.in_game import deployment

# The Adepta Sororitas' choices, for the agent interface (see agent.py): a
# few sensible ones each rather than every combination, so the action list
# stays short.
#
# - An Act of Faith uses the pool's highest Miracle dice - for an Advance or
#   charge roll, a Battle-shock test, or an attack's first Hit roll (as a
#   variant of the roll, test, shot or fight).
# - Discarding Miracle dice for an ability as a unit's selected to shoot or
#   fight (Righteous Repugnance, Rapturous Blows, Righteous Rage) uses the
#   lowest ones (a variant of the shot or fight).
# - Manual of Saint Griselda: the two lowest. Chaplet of Sacrifice: the
#   lowest dice of 3 or less. Psalm of Righteous Judgement: the lowest (not
#   a 6), or decline. Sacred Healing: 1 model, or discarding the lowest.
# - Condemnatory Psalms and Judged for Execution: each target. Hagiomnifex:
#   each ability.
#
# Defending choices (a Saving throw's Act of Faith) are the defender's,
# asked as the attack's made (see app/services/in_game/attack_decisions.py):
# "attack_decision" actions (see agent.py).
#
# The new action types aren't in app/engine/features.py ACTION_TYPES: they
# count as "other", so a policy's inputs keep their size.


@dataclass
class Choice:
    type: str
    seat: int
    label: str
    params: dict = field(default_factory=dict)


def act_of_faith_pool(game: Game, unit) -> list[int]:
    # The unit's player's Miracle dice, if it can perform an Act of Faith now.
    if acts_of_faith.cant_reason(game, unit) is not None:
        return []
    return list(deployment.owner(game, unit).miracle_dice)


def attack_variants(game: Game, unit, fighting: bool = False) -> list[tuple[dict, str]]:
    # Extra params for the unit's shot (or fight): an Act of Faith for its
    # first Hit roll; and Miracle dice discarded for its abilities.
    found = []
    if pool := act_of_faith_pool(game, unit):
        value = max(pool)
        found.append(({"miracle": {"roll": "hit", "value": value}},
                      f"Act of Faith: Hit roll {value}"))
    dice = sorted(deployment.owner(game, unit).miracle_dice)
    discards: dict[str, int] = {}
    for name in unit_abilities.discard_options(game, unit):
        if dice:
            discards[name] = dice.pop(0)
    rage = []
    if fighting:
        for _ in range(miracle_rules.rage_max(game, unit)):
            if dice:
                rage.append(dice.pop(0))
    if discards or rage:
        extra: dict = {}
        if discards:
            extra["miracle_discards"] = discards
        if rage:
            extra["righteous_rage"] = rage
        names = list(discards) + ([miracle_rules.RIGHTEOUS_RAGE] if rage else [])
        found.append((extra, "discarding Miracle dice: " + ", ".join(names)))
    return found


def actions(game: Game, units: dict) -> list[Choice]:
    # The Sororitas choices that aren't part of a roll, shot or fight.
    found: list[Choice] = []
    add = found.append

    def seat_of(unit_id: int) -> int:
        return deployment.owner(game, units[unit_id]).seat

    for state in g._miracle_dice_out(game):
        seat, pool = state.seat, sorted(state.pool)
        if state.manual and pool:
            values = pool[:2]
            add(Choice("miracle_manual", seat,
                       f"Manual of Saint Griselda: discard {', '.join(map(str, values))} "
                       f"for a {min(6, sum(values))}",
                       {"values": values}))
        if state.chaplet:
            low = [v for v in pool if v <= 3][: state.chaplet]
            if low:
                add(Choice("miracle_chaplet", seat,
                           f"Chaplet of Sacrifice: re-roll {', '.join(map(str, low))}",
                           {"values": low}))
        for offer in state.offers:
            if pool and pool[0] < 6:
                add(Choice("miracle_psalm", seat,
                           f"{offer.rule}: discard {pool[0]} for a 6",
                           {"offer_id": offer.id, "value": pool[0]}))
            add(Choice("miracle_psalm", seat, f"{offer.rule}: decline",
                       {"offer_id": offer.id, "value": None}))
        for healing in state.sacred_healing:
            add(Choice("sacred_healing", seat, f"Sacred Healing: return 1 to {healing.name}",
                       {"unit_id": healing.unit_id}))
            if pool:
                add(Choice("sacred_healing", seat,
                           f"Sacred Healing: discard {pool[0]}, return up to D3+1 to "
                           f"{healing.name}",
                           {"unit_id": healing.unit_id, "discard": pool[0]}))
    for unit in g._condemnation_out(game).units:
        for target in unit.targets:
            add(Choice("condemn", seat_of(unit.unit_id),
                       f"Condemnatory Psalms: {unit.name} condemns {target.name}",
                       {"unit_id": unit.unit_id, "target_unit_id": target.unit_id}))
    for unit in g._judgement_out(game).units:
        for target in unit.targets:
            add(Choice("judge", seat_of(unit.unit_id),
                       f"Judged for Execution: {unit.name} judges {target.name}",
                       {"unit_id": unit.unit_id, "target_unit_id": target.unit_id}))
    for unit in g._hagiomnifex_out(game):
        if unit.reason is None:
            for ability in unit.abilities:
                add(Choice("hagiomnifex", unit.seat, f"Hagiomnifex: {unit.name} - {ability}",
                           {"unit_id": unit.unit_id, "ability": ability}))
    return found
