# Machine learning

Training policies on the game engine (`backend/app/engine/`) with PyTorch. Games are played from saves, in their own processes, with no database or server.

## Setup

```bash
uv venv ml/.venv --python 3.14
uv pip install --python ml/.venv/bin/python -r ml/requirements.txt \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match
```

That's PyTorch's CPU build: the models are small, and the bottleneck is playing the games.

Run everything from the project's root. Games start from saves in `saves/<game>/` (see `backend/app/engine/saves.py`). Make a game in the app, and once it's under way its phase saves can be used, for example `saves/1/r1-s2-start_of_round.json`.

## Training with PPO

```bash
ml/.venv/bin/python -m ml.ppo saves/1/r1-s2-start_of_round.json --run first --envs 4
```

- `--opponent self` (the default) is self-play: one policy plays both players. `--opponent app.engine.env:random_policy`, or any `module:function`, plays a fixed opponent, taking a random seat each game.
- `--eval-every 10 --eval-games 4` plays the policy against random play every 10 updates.
- `--init ml/runs/imitated/model.pt` starts from a checkpoint, for example one from imitation.
- Checkpoints go to `ml/runs/<run>/model.pt`. To watch the logs, run `ml/.venv/bin/tensorboard --logdir ml/runs`.

## Learning from a teacher

Record a policy's games, then train the model to choose as it did:

```bash
ml/.venv/bin/python -m ml.imitate record saves/1/r1-s2-start_of_round.json \
    --teacher mypackage.policies:scripted --games 200 --processes 4 --data ml/data/scripted
ml/.venv/bin/python -m ml.imitate train ml/data/scripted --run imitated
```

Each game is one gzipped file of about 60KB. Training reads a few files at a time, so the data doesn't need to fit in memory.

## Evaluating

```python
import ml
from app.engine.evaluate import evaluate
from ml.policy import ModelPolicy

print(evaluate(ModelPolicy("ml/runs/first/model.pt"), "saves/1/r1-s2-start_of_round.json",
               games=20, processes=4).summary())
```

`ModelPolicy` can also be an opponent, in `--opponent` or `GameEnv(opponent=...)`.

## How it works

- **What the model sees** (`backend/app/engine/features.py`): game-wide numbers, one row per unit (yours first), and one row per legal action, each pointing at the units it involves. Attack options include their expected damage.
- **The model** (`model.py`): a small transformer over the units makes the state. Each action is scored from its own features, its units' and the state, so any number of actions can be scored. A value head estimates the player's return.
- **Rewards:** the change in a player's VP lead ÷ 100, plus ±1 for winning or losing. A decision's reward is everything that happens to that player until their next decision, including the opponent's turns.
- **Parallel games:** envs aren't stepped in lockstep. Whichever are ready are decided for in one batch through the model.

## Memory

Each game process takes about 130MB, and the trainer a few hundred MB more. Training scripts import torch inside their functions, because the game processes import the script afresh and don't need it. A script of your own that makes a `VecEnv` needs `if __name__ == "__main__":`.

## Tests

```bash
ml/.venv/bin/python -m pytest ml/tests
```
