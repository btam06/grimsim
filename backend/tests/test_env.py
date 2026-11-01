import random

from httpx import AsyncClient

from app.engine import context, features, saves, store
from app.engine.env import Decision, GameEnv, random_policy
from app.engine.vec import VecEnv
from tests.test_engine import _armed_battle

# Games as a machine learning environment (see app/engine/env.py and
# app/engine/features.py): from a save, without the database.


async def _save(client, session, tmp_path) -> str:
    game_id = await _armed_battle(client, session, tmp_path)
    path = saves.folder(game_id) / "r1-s2-movement.json"
    store.clear()
    return str(path)


def _play(env: GameEnv, seed: int, steps: int = 400) -> list:
    # Random legal actions (from `seed`) until the episode's over: each
    # step's reward and info.
    rng = random.Random(seed)
    obs, info = env.reset(seed=seed)
    trace = []
    for _ in range(steps):
        index = random_policy(Decision(None, obs["seat"], info["actions"]), rng)
        obs, reward, terminated, truncated, info = env.step(index)
        trace.append((reward, info["rewards"], info["vp"], info["state"]))
        if terminated or truncated:
            break
    return trace


async def test_what_a_player_sees(client: AsyncClient, session, tmp_path):
    path = await _save(client, session, tmp_path)
    env = GameEnv(path, seat=2)
    obs, info = env.reset(seed=1)
    assert obs["seat"] == info["seat"] == 2
    assert len(obs["global"]) == features.GLOBAL_SIZE
    assert len(obs["units"]) == len(obs["unit_mask"]) == 2 * features.MAX_UNITS
    assert all(len(row) == features.UNIT_SIZE for row in obs["units"])
    assert len(obs["actions"]) == len(info["actions"]) > 0
    assert all(len(row) == features.ACTION_SIZE for row in obs["actions"])
    # Their own unit first, then their opponent's.
    assert obs["unit_mask"][0] == obs["unit_mask"][features.MAX_UNITS] == 1
    assert obs["units"][0][0] == 1.0 and obs["units"][features.MAX_UNITS][0] == 0.0
    # Each action's unit, by slot.
    for action, slot in zip(info["actions"], obs["action_units"]):
        if "unit_id" in action["params"]:
            assert slot == 0
    env.close()


async def test_the_defender_sees_it_turned_round(client: AsyncClient, session, tmp_path):
    path = await _save(client, session, tmp_path)
    env = GameEnv(path, seat=2)
    env.reset(seed=1)
    game = env.game
    with context.bound(env.engine.live):
        attacker = features.observe(game, game.attacker_seat, [])
        defender = features.observe(game, 3 - game.attacker_seat, [])
    mine, theirs = attacker["units"][0], defender["units"][features.MAX_UNITS]
    # The same unit (the attacker's), its x and y from each side.
    assert abs(mine[5] + theirs[5] - 1) < 1e-9
    assert abs(mine[6] + theirs[6] - 1) < 1e-9
    env.close()


async def test_an_episode_replays_from_its_seed(client: AsyncClient, session, tmp_path):
    path = await _save(client, session, tmp_path)
    env = GameEnv(path, seat=2, max_steps=150)
    first = _play(env, seed=5)
    assert first and first[-1][3]
    assert _play(env, seed=5) == first
    # A different seed: different dice (and choices).
    env.reset(seed=6)
    seeded = env.game.rng_seed
    env.reset(seed=5)
    assert env.game.rng_seed != seeded
    env.close()


async def test_self_play_rewards(client: AsyncClient, session, tmp_path):
    path = await _save(client, session, tmp_path)
    env = GameEnv(path, max_steps=300)
    trace = _play(env, seed=2, steps=300)
    seats = set()
    for reward, rewards, vp, _ in trace:
        # Zero-sum: one player's gain is the other's loss.
        assert abs(rewards[1] + rewards[2]) < 1e-9
        assert reward in rewards.values()
    # Both seats get decisions.
    obs, info = env.reset(seed=2)
    rng = random.Random(2)
    for _ in range(60):
        seats.add(info["seat"])
        index = random_policy(Decision(None, obs["seat"], info["actions"]), rng)
        obs, _, terminated, truncated, info = env.step(index)
        if terminated or truncated:
            break
    assert seats == {1, 2}
    env.close()


async def test_envs_in_parallel(client: AsyncClient, session, tmp_path):
    path = await _save(client, session, tmp_path)
    envs = VecEnv(2, saves=path, seat=2, seed=0, max_steps=40)
    try:
        obs, infos = envs.reset()
        assert len(obs) == len(infos) == 2
        done = [False, False]
        for _ in range(60):
            obs, rewards, terminated, truncated, infos = envs.step([0, 0])
            for i in range(2):
                if terminated[i] or truncated[i]:
                    done[i] = True
                    # A new episode, ready to play - the last one's end with it.
                    assert infos[i]["actions"] and infos[i]["final_info"]["done"]
                    assert "final_obs" in infos[i]
            if all(done):
                break
        assert all(done)
    finally:
        envs.close()


async def test_envs_one_at_a_time(client: AsyncClient, session, tmp_path):
    path = await _save(client, session, tmp_path)
    envs = VecEnv(2, saves=path, seat=2, seed=0, max_steps=40)
    try:
        obs, infos = envs.reset()
        for i in range(2):
            envs.send(i, 0)
        stepped = {0: 0, 1: 0}
        while min(stepped.values()) < 5:
            for i, (obs_i, reward, terminated, truncated, info) in envs.poll(timeout=60):
                stepped[i] += 1
                assert info["actions"]
                envs.send(i, 0)
        # (Waiting on the last actions sent.)
        while envs.pending:
            envs.poll(timeout=60)
    finally:
        envs.close()
