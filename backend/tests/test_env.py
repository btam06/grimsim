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


def _weapon(abilities=(), **stats):
    from types import SimpleNamespace

    base = dict(attacks="2", skill=3, strength=4, ap=-1, damage="1")
    return SimpleNamespace(
        abilities=[SimpleNamespace(name=a) for a in abilities], **(base | stats)
    )


def _defender(**stats):
    from types import SimpleNamespace

    base = dict(toughness=4, save=3, invulnerable=None, feel_no_pain=None)
    return SimpleNamespace(**(base | stats))


def test_expected_weapon_damage():
    from app.engine.features import _weapon_damage

    def through(weapon, defender=None, keywords=(), models=1, half=False, cover=False, heavy=False):
        return _weapon_damage(
            weapon, defender or _defender(), set(keywords), models, half, cover, heavy
        )[0]

    # 2 attacks, hitting on 3+ (2/3), wounding on 4+ (1/2), saved on 4+ (1/2).
    assert abs(through(_weapon()) - 2 * 2 / 3 * 1 / 2 * 1 / 2) < 1e-9
    # Cover: 4+ to hit; Heavy (unmoved) cancels it out; Ignores Cover too.
    assert abs(through(_weapon(), cover=True) - 2 * 1 / 2 * 1 / 2 * 1 / 2) < 1e-9
    assert through(_weapon(["Heavy"]), cover=True, heavy=True) == through(_weapon())
    assert through(_weapon(["Ignores Cover"]), cover=True) == through(_weapon())
    # Torrent always hits; Rapid Fire 2 at half range: 4 attacks.
    assert abs(through(_weapon(["Torrent"])) - 2 * 1 / 2 * 1 / 2) < 1e-9
    assert abs(through(_weapon(["Rapid Fire 2"]), half=True) - 2 * through(_weapon())) < 1e-9
    assert through(_weapon(["Rapid Fire 2"])) == through(_weapon())
    # Melta 2 at half range: 2 more damage each.
    assert _weapon_damage(_weapon(["Melta 2"]), _defender(), set(), 1, True, False, False)[1] == 3
    # An invulnerable save that's better than the armour save; Feel No Pain.
    assert through(_weapon(ap=-3), _defender(invulnerable=4)) == through(_weapon())
    assert abs(through(_weapon(), _defender(feel_no_pain=5)) - through(_weapon()) * 2 / 3) < 1e-9
    # Anti-Infantry 4+ against INFANTRY with Devastating Wounds: mortal
    # wounds on 4+ - no saves.
    anti = _weapon(["Anti-Infantry 4+", "Devastating Wounds"])
    assert abs(through(anti, keywords={"INFANTRY"}) - 2 * 2 / 3 * 1 / 2) < 1e-9
    assert through(anti) < through(anti, keywords={"INFANTRY"})
    # Blast: 1 more attack per 5 models.
    assert abs(through(_weapon(["Blast"]), models=10) - 2 * through(_weapon())) < 1e-9


async def test_attacks_say_what_they_would_do(client: AsyncClient, session, tmp_path):
    from app.engine import features

    path = await _save(client, session, tmp_path)
    env = GameEnv(path, seat=2, max_steps=400)
    obs, info = env.reset(seed=3)
    rng = random.Random(3)
    damage = features.ACTION_SIZE - 3
    seen = 0
    for _ in range(400):
        for action, row in zip(info["actions"], obs["actions"]):
            if action["type"] in ("shoot", "fight"):
                seen += 1
                assert row[damage] > 0
                assert 0 < row[damage + 1] <= 1 and 0 < row[damage + 2] <= 1
            else:
                assert row[damage:] == [0.0, 0.0, 0.0]
        if seen:
            break
        index = random_policy(Decision(None, obs["seat"], info["actions"]), rng)
        obs, _, terminated, truncated, info = env.step(index)
        if terminated or truncated:
            obs, info = env.reset()
    assert seen
    env.close()


async def test_a_policy_is_evaluated(client: AsyncClient, session, tmp_path):
    from app.engine.evaluate import evaluate, first_action

    path = await _save(client, session, tmp_path)
    result = evaluate(first_action, path, games=2, max_steps=60)
    assert [g.seat for g in result.games] == [1, 2]
    assert sum(result.count(o) for o in ("win", "draw", "loss", "unfinished")) == 2
    assert 0 <= result.interval[0] <= result.interval[1] <= 1
    assert "2 games" in result.summary()
    # The same seed: the same games - played in parallel or not.
    again = evaluate(first_action, path, games=2, max_steps=60, processes=2)
    assert [(g.vp, g.opponent_vp, g.steps) for g in again.games] == [
        (g.vp, g.opponent_vp, g.steps) for g in result.games
    ]


async def test_either_seat(client: AsyncClient, session, tmp_path):
    path = await _save(client, session, tmp_path)
    env = GameEnv(path, seat="random", seed=0)
    seats = set()
    for seed in range(8):
        _, info = env.reset(seed=seed)
        seats.add(env.seat)
        assert info["seat"] == env.seat
    assert seats == {1, 2}
    env.close()
