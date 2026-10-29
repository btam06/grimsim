from httpx import AsyncClient

from app.models import GameStratagemTarget, GameStratagemUse, Stratagem
from app.routers.games import _load_game
from app.services.in_game import battle_shock, deployment
from app.services.in_game import game as game_service
from tests.test_deployment import _unit_named
from tests.test_movement import _battle

# 15.01: a player can't target the same unit with more than one stratagem in
# a phase; 01.07: nor one of theirs that's Battle-shocked. Seat 2's movement
# phase.


async def test_one_stratagem_per_unit_per_phase(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path)
    d = _unit_named(deployment_, "D")
    stratagem = Stratagem(name="Some Stratagem", cp=1, is_core=True)
    session.add(stratagem)
    await session.commit()
    game_ = await _load_game(session, game["id"])
    player = game_service.player_at(game_, 2)
    unit = deployment.find_unit(game_, d["unit_id"])
    assert game_service.unit_target_reason(game_, player, unit) is None
    use = GameStratagemUse(
        stratagem_id=stratagem.id, battle_round=game_.battle_round, turn_seat=game_.turn_seat,
        phase=game_.phase, cp=1,
    )
    use.target_link = GameStratagemTarget(unit_id=unit.id)
    player.stratagem_uses.append(use)
    assert "already targeted it this phase" in game_service.unit_target_reason(
        game_, player, unit
    )


async def test_battle_shocked_units_cant_be_targeted(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path)
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, _unit_named(deployment_, "D")["unit_id"])
    battle_shock.battle_shock_outright(game_, unit, "test", 1)
    player = game_service.player_at(game_, 2)
    assert game_service.unit_target_reason(game_, player, unit) == "it's Battle-shocked"
