from httpx import AsyncClient

from app.models import DatasheetAbility, GameModelDamage, GameStratagemUse, Stratagem
from app.routers.games import _load_game
from app.services.in_game import casualties, deployment, objectives
from app.services.in_game import game as game_service
from tests.test_deployment import _unit_named
from tests.test_movement import _battle

# Knight-style rules on seat 2's D (one model, 2 wounds): a Damaged profile,
# and Shock Charge (Crushing Impact for 0CP, even if already used this phase).


async def _knight(client, session, tmp_path, *abilities):
    game, deployment_ = await _battle(client, session, tmp_path)
    game_ = await _load_game(session, game["id"])
    unit = deployment.find_unit(game_, _unit_named(deployment_, "D")["unit_id"])
    for name in abilities:
        for m in unit.unit_models:
            m.model.abilities.append(DatasheetAbility(name=name, description=name))
    return game_, unit


async def test_a_damaged_profile(client: AsyncClient, session, tmp_path):
    game, unit = await _knight(client, session, tmp_path, "Damaged: 1-10 Wounds Remaining")
    model = unit.unit_models[0]
    model.model.oc = 10
    assert not casualties.damaged(game, unit)
    assert objectives.model_oc(game, model, set()) == 10
    # 1 of 2 wounds left: within 1-10 - -1 to hit, and 5 less OC.
    game.model_damage.append(
        GameModelDamage(unit_model_id=model.id, wounds_lost=1, destroyed=False)
    )
    assert casualties.damaged(game, unit)
    assert objectives.model_oc(game, model, set()) == 5


async def test_shock_charge(client: AsyncClient, session, tmp_path):
    crushing = Stratagem(name="Crushing Impact", cp=1, is_core=True)
    session.add(crushing)
    await session.commit()
    crushing = await game_service.core_stratagem(session, "Crushing Impact")
    game, unit = await _knight(client, session, tmp_path, "Shock Charge")
    with session.no_autoflush:
        player = game_service.player_at(game, 2)
        player.cp = 0
        assert game_service.stratagem_cost(crushing, unit) == (0, True)
        # No CP, and it's been used this phase: still usable on this unit.
        player.stratagem_uses.append(
            GameStratagemUse(
                stratagem_id=crushing.id, battle_round=game.battle_round,
                turn_seat=game.turn_seat, phase=game.phase, cp=1,
            )
        )
        assert game_service.stratagem_unavailable_reason(game, player, crushing) is None
        assert (
            game_service.stratagem_unavailable_reason(game, player, crushing, target=unit)
            is None
        )
