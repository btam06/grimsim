from __future__ import annotations

from pathlib import Path

import torch
from torch import nn

from app.engine import features

# The policy: a score for each legal action, and a guess at how the game's
# going (the value) - from what the player sees (see
# backend/app/engine/features.py).
#
# Units go through a small transformer (each unit seeing every other), and
# with the game-wide numbers make the state. Each action is scored from its
# own features, the units it's for and targets (by slot - see
# features.observe), and the state - so any number of actions, in any order,
# can be scored.


def _mlp(inputs: int, hidden: int, outputs: int) -> nn.Sequential:
    return nn.Sequential(nn.Linear(inputs, hidden), nn.ReLU(), nn.Linear(hidden, outputs))


class Policy(nn.Module):
    def __init__(self, hidden: int = 128, layers: int = 2, heads: int = 4) -> None:
        super().__init__()
        self.config = {"hidden": hidden, "layers": layers, "heads": heads}
        self.unit_in = _mlp(features.UNIT_SIZE, hidden, hidden)
        self.units = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(
                hidden, heads, dim_feedforward=2 * hidden, dropout=0.0, batch_first=True
            ),
            layers,
            enable_nested_tensor=False,
        )
        self.global_in = _mlp(features.GLOBAL_SIZE, hidden, hidden)
        self.state = _mlp(3 * hidden, hidden, hidden)
        self.action_in = _mlp(features.ACTION_SIZE, hidden, hidden)
        self.score = _mlp(4 * hidden, hidden, 1)
        self.value = _mlp(hidden, hidden, 1)

    def forward(self, b: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        # The batch's (see ml/batch.py collate) action scores - padding at
        # -inf - and values.
        mask = b["unit_mask"]
        units = self.units(self.unit_in(b["units"]), src_key_padding_mask=~mask)
        units = units * mask.unsqueeze(-1)
        half = features.MAX_UNITS

        def mean(part: torch.Tensor, part_mask: torch.Tensor) -> torch.Tensor:
            count = part_mask.sum(-1, keepdim=True).clamp(min=1)
            return part.sum(1) / count

        state = self.state(
            torch.cat(
                [
                    self.global_in(b["global"]),
                    mean(units[:, :half], mask[:, :half]),
                    mean(units[:, half:], mask[:, half:]),
                ],
                -1,
            )
        )

        def unit_at(slots: torch.Tensor) -> torch.Tensor:
            # Each action's unit (zeros for none).
            index = slots.clamp(min=0).unsqueeze(-1).expand(-1, -1, units.shape[-1])
            return units.gather(1, index) * (slots >= 0).unsqueeze(-1)

        actions = b["actions"]
        scored = torch.cat(
            [
                self.action_in(actions),
                unit_at(b["action_units"]),
                unit_at(b["action_targets"]),
                state.unsqueeze(1).expand(-1, actions.shape[1], -1),
            ],
            -1,
        )
        logits = self.score(scored).squeeze(-1).masked_fill(~b["action_mask"], float("-inf"))
        return logits, self.value(state).squeeze(-1)


def save(model: Policy, path: str | Path, **extra) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model": model.state_dict(),
            "config": model.config,
            # What it was trained on: a checkpoint is only good for the same
            # features.
            "sizes": (features.GLOBAL_SIZE, features.UNIT_SIZE, features.ACTION_SIZE),
            **extra,
        },
        path,
    )


def load(path: str | Path) -> Policy:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    sizes = (features.GLOBAL_SIZE, features.UNIT_SIZE, features.ACTION_SIZE)
    if tuple(checkpoint["sizes"]) != sizes:
        raise ValueError(
            f"{path} was trained on features of sizes {tuple(checkpoint['sizes'])}, "
            f"not today's {sizes} (see backend/app/engine/features.py)"
        )
    model = Policy(**checkpoint["config"])
    model.load_state_dict(checkpoint["model"])
    return model
