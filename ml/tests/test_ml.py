import pickle
import random
from types import SimpleNamespace

import pytest
import torch

from app.engine import features
from ml import batch, model
from ml.policy import ModelPolicy
from ml.ppo import Sequences, Step, advantages

# The model and its training's bookkeeping, on made-up observations (the
# shapes features.observe gives - see backend/app/engine/features.py).


def _obs(actions: int, seed: int = 0) -> dict:
    rng = random.Random(seed)
    units = [[rng.random() for _ in range(features.UNIT_SIZE)] for _ in range(2 * features.MAX_UNITS)]
    mask = [1 if i in (0, 1, features.MAX_UNITS) else 0 for i in range(2 * features.MAX_UNITS)]
    return {
        "seat": 1,
        "global": [rng.random() for _ in range(features.GLOBAL_SIZE)],
        "units": units,
        "unit_mask": mask,
        "actions": [[rng.random() for _ in range(features.ACTION_SIZE)] for _ in range(actions)],
        "action_units": [i % 2 for i in range(actions)],
        "action_targets": [features.MAX_UNITS if i % 3 == 0 else -1 for i in range(actions)],
    }


def test_a_batch_pads_its_actions():
    b = batch.collate([batch.encode(_obs(2)), batch.encode(_obs(5, seed=1))])
    assert b["actions"].shape == (2, 5, features.ACTION_SIZE)
    assert b["action_mask"].tolist() == [[True, True, False, False, False], [True] * 5]
    assert b["action_units"][0, 2:].tolist() == [-1, -1, -1]
    assert b["units"].shape == (2, 2 * features.MAX_UNITS, features.UNIT_SIZE)


def test_the_model_scores_every_action():
    torch.manual_seed(0)
    policy = model.Policy(hidden=32, layers=1, heads=2)
    logits, values = policy(batch.collate([batch.encode(_obs(3)), batch.encode(_obs(6, seed=1))]))
    assert logits.shape == (2, 6) and values.shape == (2,)
    # Padding can't be chosen.
    assert torch.isinf(logits[0, 3:]).all() and torch.isfinite(logits[0, :3]).all()
    # Scores follow the actions, whatever their order.
    obs = _obs(4)
    shuffled = dict(obs)
    order = [2, 0, 3, 1]
    for key in ("actions", "action_units", "action_targets"):
        shuffled[key] = [obs[key][i] for i in order]
    first, _ = policy(batch.collate([batch.encode(obs)]))
    second, _ = policy(batch.collate([batch.encode(shuffled)]))
    assert torch.allclose(first[0, order], second[0], atol=1e-5)
    # It learns: gradients reach every part.
    (logits[:, 0].sum() + values.sum()).backward()
    assert all(p.grad is not None for p in policy.parameters())


def test_advantages():
    # One step: reward 1, value 0.5, done - the advantage is 0.5.
    assert advantages([1.0], [0.5], [True], 9.0, 0.9, 0.8) == [0.5]
    # Two steps, not done: bootstrapped from the next value.
    found = advantages([0.0, 1.0], [0.2, 0.4], [False, False], 1.0, 0.5, 1.0)
    second = 1.0 + 0.5 * 1.0 - 0.4
    first = (0.0 + 0.5 * 0.4 - 0.2) + 0.5 * second
    assert found == pytest.approx([first, second])


def test_each_players_rewards_until_their_next_decision():
    sequences = Sequences()
    step = lambda: Step({}, 0, 0.0, 0.0)  # noqa: E731
    sequences.decide((0, 1), step())
    sequences.reward(0, {1: 0.25, 2: -0.25})
    sequences.decide((0, 2), step())
    # Seat 2's turn: seat 1's decision still collects.
    sequences.reward(0, {1: 0.5, 2: -0.5})
    sequences.decide((0, 1), step())
    assert [s.reward for s in sequences.finished[(0, 1)]] == [0.75]
    sequences.reward(0, {1: 1.0, 2: -1.0})
    sequences.end(0)
    assert [(s.reward, s.done) for s in sequences.finished[(0, 1)]] == [(0.75, False), (1.0, True)]
    assert [(s.reward, s.done) for s in sequences.finished[(0, 2)]] == [(-1.5, True)]
    assert not sequences.open and sequences.count() == 3


def test_a_checkpoint_round_trips(tmp_path):
    policy = model.Policy(hidden=32, layers=1, heads=2)
    model.save(policy, tmp_path / "model.pt")
    again = model.load(tmp_path / "model.pt")
    assert again.config == policy.config
    b = batch.collate([batch.encode(_obs(3))])
    assert torch.allclose(policy(b)[0], again(b)[0])
    # Features have changed since: it says so.
    checkpoint = torch.load(tmp_path / "model.pt", weights_only=False)
    checkpoint["sizes"] = (1, 2, 3)
    torch.save(checkpoint, tmp_path / "old.pt")
    with pytest.raises(ValueError, match="features"):
        model.load(tmp_path / "old.pt")


def test_a_model_as_a_policy(tmp_path):
    model.save(model.Policy(hidden=32, layers=1, heads=2), tmp_path / "model.pt")
    policy = pickle.loads(pickle.dumps(ModelPolicy(str(tmp_path / "model.pt"))))
    decision = SimpleNamespace(obs=_obs(5), actions=[{}] * 5)
    assert 0 <= policy(decision, random.Random(0)) < 5
    sampled = ModelPolicy(str(tmp_path / "model.pt"), greedy=False)
    assert {sampled(decision, random.Random(i)) for i in range(30)} <= set(range(5))
