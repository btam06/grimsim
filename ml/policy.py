from __future__ import annotations

import random

# A trained model as a policy for the engine (see backend/app/engine/env.py
# Policy) - to evaluate it, or play against it:
#
#     from app.engine.evaluate import evaluate
#     evaluate(ModelPolicy("ml/runs/first/model.pt"), saves, games=20)
#
# It's picklable (the model's loaded when first used), so it works in
# evaluate's processes and as a VecEnv opponent.


class ModelPolicy:
    def __init__(self, path: str, greedy: bool = True) -> None:
        # `greedy`: always the best-scored action - otherwise one at random,
        # by the model's probabilities.
        self.path = path
        self.greedy = greedy
        self._model = None

    def __getstate__(self) -> dict:
        return {"path": self.path, "greedy": self.greedy, "_model": None}

    def __call__(self, decision, rng: random.Random) -> int:
        import torch

        from ml import batch, model

        if self._model is None:
            torch.set_num_threads(1)
            self._model = model.load(self.path).eval()
        with torch.no_grad():
            logits, _ = self._model(batch.collate([batch.encode(decision.obs)]))
        logits = logits[0, : len(decision.actions)]
        if self.greedy:
            return int(logits.argmax())
        probabilities = torch.softmax(logits, -1).tolist()
        return rng.choices(range(len(probabilities)), weights=probabilities)[0]
