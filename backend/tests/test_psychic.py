from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import DatasheetAbility, Model, UnitModel
from app.routers.games import _load_game, _rule_options
from app.services.in_game import battle_shock, deployment, shooting
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to

# A (seat 1, at (20, 38)) is a psyker level 1 unit with Soul Sight and
# Shrouding; D (seat 2) is at (20, 4). Seat 2 goes first.


async def _psyker(session, unit):
    unit_model = await session.get(UnitModel, unit["models"][0]["unit_model_id"])
    model = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.abilities))
            .where(Model.id == unit_model.model_id)
        )
    ).scalar_one()
    for name in ("Librarian", "Soul Sight", "Shrouding"):
        model.abilities.append(DatasheetAbility(name=name, description=name))
    await session.commit()


async def _psychic(client, game_id):
    return (await client.get(f"/games/{game_id}/psychic")).json()


async def _use(client, game_id, unit, ability, target=None):
    return await client.post(
        f"/games/{game_id}/psychic",
        json={
            "unit_id": unit["unit_id"],
            "ability": ability,
            "target_unit_id": target["unit_id"] if target else None,
        },
    )


async def _game_with_psyker(client, session, tmp_path):
    units = {1: [("A", 2, {"weapon_range": 24})], 2: [("D", 2, {"weapon_range": 24})]}
    game, deployment_ = await _battle(client, session, tmp_path, units=units)
    a = next(u for u in deployment_["units"] if u["name"] == "A")
    d = next(u for u in deployment_["units"] if u["name"] == "D")
    await _psyker(session, a)
    return game["id"], a, d


async def test_soul_sight_and_the_psyker_level(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, d = await _game_with_psyker(client, session, tmp_path)
    [unit] = (await _psychic(client, game_id))["units"]
    assert (unit["psyker_level"], [x["name"] for x in unit["abilities"]]) == (
        1, ["Shrouding", "Soul Sight"]
    )
    # Soul Sight: only in its own Shooting phase.
    response = await _use(client, game_id, a, "Soul Sight", d)
    assert "Shooting phase" in response.json()["detail"]
    await _advance_to(client, game_id, 1, 1, "shooting")
    monkeypatch.setattr("app.services.in_game.psychic.random.randint", lambda a, b: 4)
    response = await _use(client, game_id, a, "Soul Sight", d)
    assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    unit_a, unit_d = (deployment.find_unit(game, u["unit_id"]) for u in (a, d))
    # Ranged attacks against D ignore cover this phase.
    assert not shooting.reach(game, unit_a, unit_d).in_cover
    # Its psyker level (1) is used up this round.
    response = await _use(client, game_id, a, "Shrouding")
    assert "psyker level" in response.json()["detail"]


async def test_shrouding_and_a_psychic_roll_of_1(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, d = await _game_with_psyker(client, session, tmp_path)
    # Seat 2's Shooting phase: D could attack it.
    await _advance_to(client, game_id, 1, 2, "shooting")
    monkeypatch.setattr("app.services.in_game.psychic.random.randint", lambda a, b: 1)
    response = await _use(client, game_id, a, "Shrouding")
    assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    unit_a = deployment.find_unit(game, a["unit_id"])
    # Attacks against it are -1 to hit this phase; a 1 Battle-shocked it.
    assert "Shrouded" in _rule_options(game, unit_a)
    assert battle_shock.is_battle_shocked(game, unit_a)
    # Not next phase.
    await _advance_to(client, game_id, 1, 2, "charge")
    game = await _load_game(session, game_id)
    assert "Shrouded" not in _rule_options(game, deployment.find_unit(game, a["unit_id"]))
