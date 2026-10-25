from __future__ import annotations

from app.models import Game, Unit
from app.services.in_game import battle_round, deployment
from app.services.in_game.deployment import TOLERANCE, gap

# The Chaos Knights' Harbingers of Dread, in a game. A player's models with
# the ability have Deathly Terror from the start of the battle, and the Dread
# abilities chosen at the start of the first, third and fifth battle rounds
# (see app/services/in_game/battle_round.py) for the rest of it. The ones
# that aren't combat rules (Doom and Darkness are - see the calculator):
#
# - Deathly Terror and Despair (Auras): an enemy unit within 9" of one of
#   those models has its Leadership worsened by 1 each - for its Battle-shock
#   tests (see app/services/in_game/battle_shock.py).
# - Dismay (Aura): in the Battle-shock step of the player's opponent's
#   Command phase, each enemy unit below its Starting Strength within 9"
#   must take a Battle-shock test.
# - Delirium (Aura): an enemy unit Below Half-strength within 9" suffers D3
#   mortal wounds each time it fails a Battle-shock test.
# - Dominion: the auras reach 3" further.

HARBINGERS_OF_DREAD = "Harbingers of Dread"
DEATHLY_TERROR = "Deathly Terror"
AURA_RANGE = 9.0
DOMINION_BONUS = 3.0


def _models(game: Game, seat: int) -> list:
    # The player's models on the battlefield with Harbingers of Dread: (unit
    # model, base).
    player = next(p for p in game.players if p.seat == seat)
    placed = deployment.positions(game)
    found = []
    for unit in deployment.deployable_units(player):
        for m in deployment.models_on_battlefield(game, unit):
            if any(a.name == HARBINGERS_OF_DREAD for a in m.model.faction_abilities):
                p = placed[m.id]
                found.append((m, deployment.base_at(m, p.x, p.y, p.rotation)))
    return found


def active(game: Game, seat: int) -> set[str]:
    # The player's active Dread abilities (none, without the rule on the
    # battlefield).
    models = _models(game, seat)
    if not models:
        return set()
    ability_id = next(
        a.id for m, _ in models for a in m.model.faction_abilities if a.name == HARBINGERS_OF_DREAD
    )
    return {DEATHLY_TERROR} | set(battle_round.chosen_options(game, seat, ability_id))


def aura_range(game: Game, seat: int) -> float:
    return AURA_RANGE + (DOMINION_BONUS if "Dominion" in active(game, seat) else 0)


def _within_aura(game: Game, unit: Unit) -> bool:
    # Whether the unit is within the Dread auras of its opponent's models.
    enemy = next(p.seat for p in game.players if p.seat != deployment.owner(game, unit).seat)
    models = _models(game, enemy)
    if not models:
        return False
    reach = aura_range(game, enemy)
    placed = deployment.positions(game)
    bases = [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in deployment.models_on_battlefield(game, unit)
    ]
    return any(gap(b, base) <= reach + TOLERANCE for _, base in models for b in bases)


def _enemy_active(game: Game, unit: Unit) -> set[str]:
    enemy = next(p.seat for p in game.players if p.seat != deployment.owner(game, unit).seat)
    return active(game, enemy)


def leadership_worsened(game: Game, unit: Unit) -> int:
    # How much its Leadership is worsened by (Deathly Terror, Despair).
    if not _within_aura(game, unit):
        return 0
    found = _enemy_active(game, unit)
    return (DEATHLY_TERROR in found) + ("Despair" in found)


def dismay(game: Game, unit: Unit) -> bool:
    # Whether Dismay makes it take a Battle-shock test (in its Battle-shock
    # step): it's below its Starting Strength, within the aura.
    from app.services.in_game import battle_shock

    return (
        "Dismay" in _enemy_active(game, unit)
        and battle_shock.below_starting_strength(game, unit)
        and _within_aura(game, unit)
    )


def delirium(game: Game, unit: Unit) -> bool:
    # Whether Delirium makes it suffer D3 mortal wounds when it fails a
    # Battle-shock test: it's Below Half-strength, within the aura.
    from app.services.in_game import battle_shock

    return (
        "Delirium" in _enemy_active(game, unit)
        and battle_shock.below_half_strength_strict(game, unit)
        and _within_aura(game, unit)
    )


def aura_models(game: Game, unit: Unit) -> list:
    # The unit's models with Dread auras, and how far they reach (to show).
    seat = deployment.owner(game, unit).seat
    reach = aura_range(game, seat)
    return [(m, reach) for m, _ in _models(game, seat) if m.unit_id == unit.id]
