from __future__ import annotations

from app.engine.state import Game, GameAbilityUse
from app.models import Unit
from app.seeds.factions.adeptus_mechanicus.detachment_rules import ACQUISITION
from app.services.in_game import casualties, deployment, selected_objectives
from app.services.in_game.deployment import TOLERANCE, gap
from app.services.list_building import enhancements as enhancement_rules

# Adeptus Mechanicus enhancements the defending player can use as a saving
# throw is made for one of their units, in a game (asked as it fails - see
# app/services/in_game/attack_decisions.py):
#
# - Artisan (Explorator Maniple): while the bearer is leading a unit within
#   range of its player's Acquisition objective marker, once per phase, the
#   result of one saving throw made for that unit is changed to an
#   unmodified 6. (Its Hit and Wound rolls aren't offered: they're the
#   attacking side's, made one attack at a time.)
# - Necromechanic (Cohort Cybernetica): once per battle round, when a saving
#   throw made for a friendly LEGIO CYBERNETICA, or ADEPTUS MECHANICUS
#   VEHICLE, model within 12" of the bearer is failed, that attack's Damage
#   characteristic is changed to 0.

ARTISAN = "Artisan"
NECROMECHANIC = "Necromechanic"
NECROMECHANIC_RANGE = 12.0


def _alive(game: Game, unit_model) -> bool:
    lost = casualties.damage(game).get(unit_model.id)
    return not (lost is not None and lost.destroyed)


def _bearer(unit: Unit, enhancement: str):
    return next(
        (
            m
            for m in unit.unit_models
            if m.enhancement is not None and m.enhancement.name == enhancement
        ),
        None,
    )


def has_bearer(game: Game, enhancement: str) -> bool:
    # Whether any army in the game has the enhancement.
    return any(
        _bearer(unit, enhancement) is not None
        for player in game.players
        for unit in deployment.deployable_units(player)
    )


def _used(game: Game, seat: int, ability: str, this_phase: bool) -> bool:
    return any(
        u.seat == seat
        and u.ability == ability
        and u.battle_round == game.battle_round
        and (not this_phase or (u.turn_seat == game.turn_seat and u.phase == game.phase))
        for u in game.ability_uses
    )


def _use(game: Game, seat: int, unit_id: int, ability: str) -> None:
    game.ability_uses.append(
        GameAbilityUse(
            seat=seat,
            unit_id=unit_id,
            ability=ability,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            phase=game.phase,
        )
    )


# --- Artisan ---


def artisan_reason(game: Game, unit: Unit) -> str | None:
    # Why Artisan can't change one of the unit's saving throws now (None: it
    # can).
    bearer = _bearer(unit, ARTISAN)
    if bearer is None or not _alive(game, bearer):
        return "no model in it has Artisan"
    if not enhancement_rules.is_leading(unit, bearer):
        return "Artisan's bearer isn't leading it"
    if not selected_objectives.unit_within(game, unit, ACQUISITION):
        return "it isn't within range of its Acquisition objective marker"
    if _used(game, deployment.owner(game, unit).seat, ARTISAN, this_phase=True):
        return "Artisan has been used this phase"
    return None


def use_artisan(game: Game, unit: Unit) -> None:
    _use(game, deployment.owner(game, unit).seat, unit.id, ARTISAN)


# --- Necromechanic ---


def _necromechanic_victim(unit: Unit, unit_model) -> bool:
    keywords = enhancement_rules.model_keywords(unit, unit_model)
    return "LEGIO CYBERNETICA" in keywords or {"ADEPTUS MECHANICUS", "VEHICLE"} <= keywords


def necromechanic_bearer(game: Game, unit: Unit, unit_model_id: int):
    # The friendly model with Necromechanic that can change the Damage of an
    # attack whose save failed for that model of the unit (unit, unit model) -
    # None if none can.
    player = deployment.owner(game, unit)
    if _used(game, player.seat, NECROMECHANIC, this_phase=False):
        return None
    victim = next((m for m in unit.unit_models if m.id == unit_model_id), None)
    if victim is None or not _necromechanic_victim(unit, victim):
        return None
    placed = deployment.positions(game)
    if victim.id not in placed:
        return None
    p = placed[victim.id]
    victim_base = deployment.base_at(victim, p.x, p.y, p.rotation)
    for other in deployment.deployable_units(player):
        bearer = _bearer(other, NECROMECHANIC)
        if bearer is None or bearer.id not in placed or not _alive(game, bearer):
            continue
        q = placed[bearer.id]
        base = deployment.base_at(bearer, q.x, q.y, q.rotation)
        if gap(base, victim_base) <= NECROMECHANIC_RANGE + TOLERANCE:
            return other, bearer
    return None


def use_necromechanic(game: Game, unit: Unit) -> None:
    # (`unit`: the bearer's.)
    _use(game, deployment.owner(game, unit).seat, unit.id, NECROMECHANIC)
