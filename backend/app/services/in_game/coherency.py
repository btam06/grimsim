from __future__ import annotations

from app.models import Game, GameModelDamage, Unit
from app.services.in_game import deployment
from app.services.in_game.deployment import COHERENCY_RANGE, TOLERANCE, UNIT_SPAN, gap

# Regaining coherency (03.03): in the End of Turn step of each player's turn,
# each unit on the battlefield that isn't in coherency loses models, one at a
# time, until it is - its models within 2" of another, and 9" of every other.
# Those models are destroyed, but trigger nothing a destroyed model would
# (they aren't in the turn record). Which go is chosen for the player: those
# outside the biggest group of models within 2" of each other, furthest first;
# then whichever is more than 9" from the most others.


def _bases(game: Game, unit: Unit) -> dict:
    placed = deployment.positions(game)
    return {
        m.id: deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    }


def _near(bases: dict, i: int, j: int) -> bool:
    return gap(bases[i], bases[j]) <= COHERENCY_RANGE + TOLERANCE


def _groups(bases: dict) -> list[set[int]]:
    # The models in groups of models within 2" of each other (chained).
    left, groups = set(bases), []
    while left:
        group, todo = set(), [left.pop()]
        while todo:
            i = todo.pop()
            group.add(i)
            for j in list(left):
                if _near(bases, i, j):
                    left.remove(j)
                    todo.append(j)
        groups.append(group)
    return groups


def _too_far(bases: dict, i: int) -> int:
    return sum(1 for j in bases if j != i and gap(bases[i], bases[j]) > UNIT_SPAN + TOLERANCE)


def next_to_remove(bases: dict) -> int | None:
    # The model to remove for the unit to regain coherency - None if it's in
    # coherency.
    if len(bases) < 2:
        return None
    groups = sorted(_groups(bases), key=lambda g: (-len(g), min(g)))
    if len(groups) > 1:
        keep = groups[0]

        def distance(i: int) -> float:
            return min(gap(bases[i], bases[k]) for k in keep)

        return max((i for i in bases if i not in keep), key=lambda i: (distance(i), i))
    worst = max(bases, key=lambda i: (_too_far(bases, i), i))
    return worst if _too_far(bases, worst) else None


def regain(game: Game) -> list[int]:
    # The End of Turn step: every unit on the battlefield out of coherency
    # loses models until it's back in. The models removed.
    removed = []
    damage = {d.unit_model_id: d for d in game.model_damage}
    for player in game.players:
        for unit in deployment.deployable_units(player):
            bases = _bases(game, unit)
            while (i := next_to_remove(bases)) is not None:
                position = deployment.positions(game)[i]
                game.model_positions.remove(position)
                model = next(m for m in unit.unit_models if m.id == i)
                record = damage.get(i)
                if record is None:
                    record = GameModelDamage(unit_model_id=i, wounds_lost=0, destroyed=False)
                    game.model_damage.append(record)
                record.wounds_lost, record.destroyed = model.wounds, True
                removed.append(i)
                del bases[i]
    return removed
