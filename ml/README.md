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

Run everything from the project's root. Games start from saves in `saves/<game>/` (see `backend/app/engine/saves.py`). Make a game in the app: `saves/<game>/setup.json` is saved as it's made, before anything's deployed, so episodes from it learn deployment too (for example `saves/1/setup.json`). Its phase saves, such as `r1-s1-start_of_round.json`, start later, once the battle's under way.

To make a spread of games from your army lists - every pairing, each way round - run `python3 scripts/spread_games.py --games 3 > ml/data/spread.txt` with the app up, then pass `$(cat ml/data/spread.txt)` as the saves. Each episode starts from one of them at random.

## Training with PPO

```bash
ml/.venv/bin/python -m ml.ppo saves/1/setup.json --run first --envs 4
```

- `--opponent self` (the default) is self-play: one policy plays both players. `--opponent app.engine.env:random_policy`, `--opponent app.engine.scripted:scripted` (the scripted player: rules of thumb - see backend/app/engine/scripted.py), or any `module:function`, plays a fixed opponent, taking a random seat each game.
- `--eval-every 10 --eval-games 4` plays the policy against random play every 10 updates.
- `--init ml/runs/imitated/model.pt` starts from a checkpoint, for example one from imitation.
- `--resume` carries a run on from its `model.pt` (after a crash, say), at the update after the one it saved, with the same `--updates` total. The optimiser starts afresh.
- `--value-warmup 3` trains only the value head for the first 3 updates (at `--warmup-lr`), leaving the policy as it is. Use it when the checkpoint's value head learnt against a different opponent. Those updates' win rates are also the checkpoint's own.
- `--target-kl 0.02` stops an update's epochs early once the policy has moved that far (KL) from the one that played the games. The log's `kl` and `epochs` show how far it moved and how many epochs ran.
- Checkpoints go to `ml/runs/<run>/model.pt` (the latest), and every 5 updates to `model-<update>.pt` too (`--keep-every`), to go back to the best. Each finished game is a line in `games.jsonl`: `python3 scripts/list_win_rates.py ml/runs/<run>/games.jsonl` gives each list's win rate. Each update logs `vp_left`, the VP a player left on the table out of the 90 a battle gives. In self-play this can fall even though the win rate can't change. Each update also logs `points_left`, the points of a player's units still alive at the end. To watch the logs, run `ml/.venv/bin/tensorboard --logdir ml/runs`.
- `python -m ml.diagnose` plays games and sums up how each list plays: where its VP comes from, damage and kills by shooting and in melee, charges, stratagems, idle units, and VP left on the table: primary and secondary left, VP lost to the caps, tactical cards discarded and claimed, and VP on cards held but never claimed. It also gives the points of units still alive at the end (`ptsleft`) and of units destroyed (`ptslost`).

## Learning from a teacher

Record a policy's games, then train the model to choose as it did:

```bash
ml/.venv/bin/python -m ml.imitate record saves/1/setup.json \
    --teacher app.engine.scripted:scripted --games 200 --processes 4 --data ml/data/scripted
ml/.venv/bin/python -m ml.imitate train ml/data/scripted --run imitated
```

Each game is one gzipped file of about 60KB. Training reads a few files at a time, so the data doesn't need to fit in memory.

## Evaluating

```python
import ml
from app.engine.evaluate import evaluate
from ml.policy import ModelPolicy

print(evaluate(ModelPolicy("ml/runs/first/model.pt"), "saves/1/setup.json",
               games=20, processes=4).summary())
```

`ModelPolicy` can also be an opponent, in `--opponent` or `GameEnv(opponent=...)`.

## How it works

- **What the model sees** (`backend/app/engine/features.py`): game-wide numbers, one row per unit (yours first), and one row per legal action, each pointing at the units it involves. Attack options include their expected damage.
- **The model** (`model.py`): a small transformer over the units makes the state. Each action is scored from its own features, its units' and the state, so any number of actions can be scored. A value head estimates the player's return.
- **Rewards:** for VP as it's scored: 0.25 × primary VP ÷ 45, 0.25 × secondary VP ÷ 45 (counted up to 45), and 0.5 × the change in the VP lead ÷ 45. At the end, ±1 for winning or losing. Maxing out both kinds of VP (0.5) is worth less than a win, and damage and kills earn nothing in themselves (see `backend/app/engine/env.py`). A decision's reward is everything that happens to that player until their next decision, including the opponent's turns.
- **Parallel games:** envs aren't stepped in lockstep. Whichever are ready are decided for in one batch through the model.

## Memory

Each game process takes about 130MB, and the trainer a few hundred MB more. Training scripts import torch inside their functions, because the game processes import the script afresh and don't need it. A script of your own that makes a `VecEnv` needs `if __name__ == "__main__":`.

## Tests

```bash
ml/.venv/bin/python -m pytest ml/tests
```
