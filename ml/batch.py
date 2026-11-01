from __future__ import annotations

import torch

from app.engine import features

# Observations (see backend/app/engine/features.py) as tensors: each one on
# its own (encode), then several as a batch (collate) - their action lists
# padded to the longest, with a mask saying which are real.


def encode(obs: dict) -> dict[str, torch.Tensor]:
    actions = obs["actions"]
    return {
        "global": torch.tensor(obs["global"], dtype=torch.float32),
        "units": torch.tensor(obs["units"], dtype=torch.float32),
        "unit_mask": torch.tensor(obs["unit_mask"], dtype=torch.bool),
        "actions": (
            torch.tensor(actions, dtype=torch.float32)
            if actions
            else torch.zeros((0, features.ACTION_SIZE), dtype=torch.float32)
        ),
        "action_units": torch.tensor(obs["action_units"], dtype=torch.long),
        "action_targets": torch.tensor(obs["action_targets"], dtype=torch.long),
    }


def collate(encoded: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
    size = len(encoded)
    longest = max(1, max(len(e["action_units"]) for e in encoded))
    actions = torch.zeros((size, longest, features.ACTION_SIZE))
    mask = torch.zeros((size, longest), dtype=torch.bool)
    units = torch.full((size, longest), -1, dtype=torch.long)
    targets = torch.full((size, longest), -1, dtype=torch.long)
    for i, e in enumerate(encoded):
        n = len(e["action_units"])
        if n:
            actions[i, :n] = e["actions"]
            mask[i, :n] = True
            units[i, :n] = e["action_units"]
            targets[i, :n] = e["action_targets"]
    return {
        "global": torch.stack([e["global"] for e in encoded]),
        "units": torch.stack([e["units"] for e in encoded]),
        "unit_mask": torch.stack([e["unit_mask"] for e in encoded]),
        "actions": actions,
        "action_mask": mask,
        "action_units": units,
        "action_targets": targets,
    }
