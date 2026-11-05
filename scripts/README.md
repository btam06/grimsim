# Scripts

Odd jobs, run from the project's root.

- `spread_games.py`: makes games from every pairing of the army lists (each way round, a few of each) through the running app, and prints their `setup.json` saves' paths, to train from - see `ml/README.md`. `--dry-run` lists the pairings first.
- `list_win_rates.py`: each army list's win rate (and each pairing's) from a training run's `ml/runs/<run>/games.jsonl`, which `ml.ppo` writes as games finish. `--since N` counts only games from update N on.
