from types import SimpleNamespace

from httpx import AsyncClient
from sqlalchemy import select

from app.models import Game
from app.services import dice
from tests.test_deployment import _unit_named
from tests.test_movement import _battle
from tests.test_simulation import _units

# Each game's dice (see app/services/dice.py): rolls from a stream seeded
# with the game's seed, so the same seed and actions give the same rolls.


def _rolls(seed, count):
    game = SimpleNamespace(rng_seed=seed, rng_rolls=0)
    token = dice._current.set(dice._Stream(game))
    try:
        return [dice.d6() for _ in range(count)], game.rng_rolls
    finally:
        dice._current.reset(token)


def test_a_seed_gives_the_same_rolls():
    first, counted = _rolls(7, 50)
    assert _rolls(7, 50) == (first, counted)
    assert counted == 50
    assert set(first) <= set(range(1, 7))
    assert _rolls(8, 50)[0] != first


async def test_a_game_rolls_from_its_seed(client: AsyncClient, session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.dice.new_seed", lambda: 1234)
    game, deployment = await _battle(client, session, tmp_path)
    assert game["seed"] == 1234

    async def rolls():
        return (
            await session.execute(select(Game.rng_rolls).where(Game.id == game["id"]))
        ).scalar_one()

    before = await rolls()
    d = _unit_named(deployment, "D")
    response = await client.post(
        f"/games/{game['id']}/movement/advance", json={"unit_id": d["unit_id"]}
    )
    assert response.status_code == 200, response.text
    # The game's next roll: the same seed, that far in, gives the same D6.
    expected = _rolls_from(1234, before)
    assert response.json()["units"][0]["advance_roll"] == expected
    assert await rolls() == before + 1


def _rolls_from(seed, n):
    stream = dice._Stream(SimpleNamespace(rng_seed=seed, rng_rolls=n))
    stream.read()
    token = dice._current.set(stream)
    try:
        return dice.d6()
    finally:
        dice._current.reset(token)


async def test_the_calculator_uses_its_own_dice(client: AsyncClient, session, tmp_path):
    a, d, gun = await _units(client, session, tmp_path)
    game_id = (
        await session.execute(select(Game.id).order_by(Game.id.desc()).limit(1))
    ).scalar_one()

    async def rolls():
        return (
            await session.execute(select(Game.rng_rolls).where(Game.id == game_id))
        ).scalar_one()

    before = await rolls()
    payload = {"attacking_unit_id": d["unit_id"], "defending_unit_id": a["unit_id"],
               "selected_weapon_ids": [gun]}
    assert (await client.post("/combat", json=payload)).status_code == 200
    response = await client.post("/combat/simulate", json=payload | {"runs": 50})
    assert response.status_code == 200, response.text
    assert await rolls() == before
