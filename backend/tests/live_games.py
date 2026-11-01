from app.engine import store
from app.engine.state import GameModelDamage, GameModelPosition, GamePlayer

# Games' state, as played in memory (see app/engine/store.py) - for tests
# that set a game up directly.


def game(game_id: int | None = None):
    # The game (the test's latest, if no id's given).
    return store.get(game_id if game_id is not None else store.ids()[-1]).game


def position(unit_model_id: int, game_id: int | None = None) -> GameModelPosition:
    return next(p for p in game(game_id).model_positions if p.unit_model_id == unit_model_id)


def remove_position(unit_model_id: int, game_id: int | None = None) -> None:
    g = game(game_id)
    g.model_positions[:] = [p for p in g.model_positions if p.unit_model_id != unit_model_id]


def damage(game_id: int, unit_model_id: int, wounds_lost: int, destroyed: bool = False) -> None:
    game(game_id).model_damage.append(
        GameModelDamage(
            game_id=game_id, unit_model_id=unit_model_id, wounds_lost=wounds_lost,
            destroyed=destroyed,
        )
    )


def player(game_id: int, seat: int) -> GamePlayer:
    return next(p for p in game(game_id).players if p.seat == seat)
