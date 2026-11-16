from __future__ import annotations

from app.models import Unit
from app.engine.state import Game
from app.services import dice
from app.services.in_game import deployment
from app.services.in_game.deployment import TOLERANCE, gap

# Necron datasheet abilities that happen as attacks are resolved, in a game:
#
# - Repair Barge (Ghost Ark): once a turn, just after an enemy unit finishes
#   its attacks, if a friendly NECRON WARRIORS unit within 3" of it lost
#   wounds to them, that unit's Reanimation Protocols activate (the same
#   unit at most once a turn). Always worth it, so it happens by itself.
# - Malevolent Arcing (Annihilation Barge): each time its twin tesla
#   destructor shoots, a D6 for the target and each other enemy unit within
#   3" of it - on a 5+, D3 mortal wounds once the attacks are resolved.

REPAIR_BARGE = "Repair Barge"
REPAIR_RANGE = 3.0
NECRON_WARRIORS = "NECRON WARRIORS"
# Marks (see app/services/in_game/mission_state.py): a Ghost Ark that's used
# it this turn, and a NECRON WARRIORS unit it's been used on this turn.
BARGE_USED = "repair_barge"
BARGE_TARGET = "repair_barge_target"

MALEVOLENT_ARCING = "Malevolent Arcing"
ARCING_WEAPON = "twin tesla destructor"
ARCING_RANGE = 3.0


def _bases(game: Game, unit: Unit, only: str | None = None) -> list:
    placed = deployment.positions(game)
    return [
        deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in deployment.models_on_battlefield(game, unit)
        if m.id in placed and (only is None or any(a.name == only for a in m.model.abilities))
    ]


def _this_turn(game: Game, kind: str) -> set[int]:
    from app.services.in_game import mission_state

    return {
        m.unit_id
        for m in mission_state.marked(game, kind)
        if m.battle_round == game.battle_round and m.turn_seat == game.turn_seat
    }


def repair_barge(game: Game, attacked: list[tuple[Unit, int]]) -> None:
    # An enemy unit has finished its attacks: `attacked` - the units it
    # attacked, and how many wounds each lost.
    from app.seeds.factions.necrons import reanimation
    from app.services.in_game import mission_state

    for unit, lost in attacked:
        if lost <= 0 or not deployment.models_on_battlefield(game, unit):
            continue
        if not any(k.name == NECRON_WARRIORS for m in unit.unit_models for k in m.model.keywords):
            continue
        if unit.id in _this_turn(game, BARGE_TARGET):
            continue
        seat = deployment.owner(game, unit).seat
        player = next(p for p in game.players if p.seat == seat)
        used = _this_turn(game, BARGE_USED)
        mine = _bases(game, unit)
        for ark in deployment.deployable_units(player):
            if ark.id in used:
                continue
            if any(
                gap(a, b) <= REPAIR_RANGE + TOLERANCE
                for a in _bases(game, ark, REPAIR_BARGE)
                for b in mine
            ):
                mission_state.mark(game, seat, BARGE_USED, ark.id)
                mission_state.mark(game, seat, BARGE_TARGET, unit.id)
                reanimation.activate(game, unit)
                break


def malevolent_arcing(game: Game, unit: Unit, target: Unit, weapon_names: list[str]) -> list[Unit]:
    # The unit's model with it shot `target` with its twin tesla destructor
    # (among `weapon_names`): the units struck by arcing energies suffer D3
    # mortal wounds each. Returns them.
    from app.services.combat import roll_dice
    from app.services.in_game import casualties, shooting

    if game.phase != "shooting" or deployment.owner(game, unit).seat != game.turn_seat:
        return []
    if not _bases(game, unit, MALEVOLENT_ARCING):
        return []
    if not any(n.lower().startswith(ARCING_WEAPON) for n in weapon_names):
        return []
    targets = _bases(game, target)
    candidates = [target] + [
        u
        for u in shooting.enemy_units(game, unit)
        if u.id != target.id
        and any(gap(a, b) <= ARCING_RANGE + TOLERANCE for a in _bases(game, u) for b in targets)
    ]
    struck = [u for u in candidates if dice.randint(1, 6) >= 5]
    for u in struck:
        if deployment.models_on_battlefield(game, u):
            casualties.mortal_wounds(game, u, roll_dice("D3"), destroyed_by=unit)
    return struck
