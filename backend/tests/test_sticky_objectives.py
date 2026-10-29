from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import DatasheetAbility, Model, UnitModel
from app.routers.games import _load_game
from app.services.in_game import battle_shock, deployment, objectives
from tests.test_deployment import _unit_named
from tests.test_movement import _battle
from tests.test_objectives import ON_THE_RUIN, UNITS, _objective
from tests.test_reinforcements import _advance_to
from tests.test_shooting import _place

# The test layout's one objective is the Medium ruin's area (x 7-13, y 8-12).
# A (seat 1) and D (seat 2) have 2 models each, OC 1.

OFF_IT = [(30, 36), (31.5, 36)]
FAR_OFF = [(30, 6), (31.5, 6)]


async def _secure_for(session, game_id, seat):
    game = await _load_game(session, game_id)
    [objective] = objectives.objectives(game)
    objectives.secure(game, objective.id, seat)
    await session.commit()


async def _refresh(session, game_id):
    # The end of a phase: control is determined.
    session.expire_all()
    game = await _load_game(session, game_id)
    objectives.refresh_secured(game)
    objectives.determine(game)
    await session.commit()


async def _shock(session, game_id, unit):
    game = await _load_game(session, game_id)
    battle_shock.battle_shock_outright(
        game, deployment.find_unit(game, unit["unit_id"]), "test", 1
    )
    await session.commit()


async def test_a_secured_objective_stays_until_outscored_at_a_phase_end(
    client: AsyncClient, session, tmp_path
):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _place(session, a, OFF_IT)
    await _place(session, d, FAR_OFF)
    await _secure_for(session, game_id, 1)
    # No models on it: still seat 1's.
    objective = await _objective(client, game_id)
    assert (objective["live_controller"], objective["secured_by"]) == (1, 1)

    # D on it, more OC than seat 1's 0: still seat 1's until the phase ends...
    await _place(session, d, ON_THE_RUIN)
    objective = await _objective(client, game_id)
    assert (objective["oc"], objective["live_controller"]) == ({"1": 0, "2": 2}, 1)
    # ...then it's no longer secured, and seat 2 controls it.
    await _refresh(session, game_id)
    objective = await _objective(client, game_id)
    assert (objective["controller"], objective["secured_by"]) == (2, None)


async def test_a_secured_objective_stays_in_a_tie(client: AsyncClient, session, tmp_path):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _place(session, a, [(8, 9), (12, 11)])
    await _place(session, d, ON_THE_RUIN)
    await _secure_for(session, game_id, 1)
    # 2 to 2: a tie isn't more - still seat 1's after the phase ends.
    await _refresh(session, game_id)
    objective = await _objective(client, game_id)
    assert (objective["oc"], objective["controller"], objective["secured_by"]) == (
        {"1": 2, "2": 2}, 1, 1
    )


async def test_battle_shocked_models_dont_take_a_secured_objective(
    client: AsyncClient, session, tmp_path
):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    await _place(session, a, OFF_IT)
    await _place(session, d, ON_THE_RUIN)
    await _shock(session, game_id, d)
    await _secure_for(session, game_id, 1)
    # None of seat 1's models there, only Battle-shocked ones of seat 2's (OC
    # 0): 0 to 0, still seat 1's.
    await _refresh(session, game_id)
    objective = await _objective(client, game_id)
    assert (objective["oc"], objective["controller"], objective["secured_by"]) == (
        {"1": 0, "2": 0}, 1, 1
    )


async def test_raise_the_banner_secures_at_the_end_of_movement(
    client: AsyncClient, session, tmp_path
):
    game, deployment_ = await _battle(client, session, tmp_path, units=UNITS)
    game_id = game["id"]
    a, d = _unit_named(deployment_, "A"), _unit_named(deployment_, "D")
    unit_model = await session.get(UnitModel, a["models"][0]["unit_model_id"])
    model = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    model.abilities.append(DatasheetAbility(name="Raise the Banner", description="Raise the Banner"))
    await session.commit()
    await _place(session, a, ON_THE_RUIN)
    await _place(session, d, FAR_OFF)
    await _advance_to(client, game_id, 1, 1, "movement")
    objective = await _objective(client, game_id)
    assert objective["secured_by"] is None
    await _advance_to(client, game_id, 1, 1, "shooting")
    objective = await _objective(client, game_id)
    assert (objective["controller"], objective["secured_by"]) == (1, 1)
    # A leaves it: still seat 1's.
    await _place(session, a, OFF_IT)
    assert (await _objective(client, game_id))["controller"] == 1
