"""Open-vocabulary target navigation environment."""

from __future__ import annotations

from typing import Any

from app.modules.envs.base import BaseEnv
from app.modules.envs.interaction import InteractionConfig, ObservationConfig
from app.modules.envs.spaces import Box, DictSpace, ImageSpace, TextSpace


class OpenVocabNavEnv(BaseEnv):
    name = "open_vocab_navigation"
    task_type = "open_vocab_navigation"

    @classmethod
    def default_interaction(cls) -> InteractionConfig:
        return InteractionConfig(
            bridge="mock",
            observation=ObservationConfig(
                modalities=["camera_rgb", "pose", "minimap"],
                timeout_sec=5.0,
            ),
        )

    def observation_space_dict(self) -> dict[str, Any]:
        return DictSpace(
            {
                "pose": Box(-1e6, 1e6, (3,)),
                "camera_rgb": ImageSpace(),
                "goal_position": Box(-1e6, 1e6, (3,)),
                "distance": Box(0, 1e9, (1,)),
                "instruction": TextSpace(),
            }
        ).to_dict()

    def action_space_dict(self) -> dict[str, Any]:
        return DictSpace(
            {
                "offset": Box(-1000, 1000, (2,)),
                "speed": Box(0, 100, (1,)),
                "status": TextSpace(32),
            }
        ).to_dict()
