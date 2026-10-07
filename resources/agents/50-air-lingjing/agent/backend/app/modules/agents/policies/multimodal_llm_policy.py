"""Multimodal LLM policy using the existing AI analysis service."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.responses import AppError
from app.modules.ai.service import analysis, parse_model_json

Observation = dict[str, Any]
Action = dict[str, Any]


def _read_env_prompt(task_type: str) -> str:
    settings = get_settings()
    path = Path(settings.prompt_dir) / "envs" / f"{task_type}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "You are controlling an embodied agent in a simulation. "
        "Given the observation JSON, output a single JSON action with keys "
        '`offset` (list of two numbers x,y), `speed` (number), and optional `status`. '
        "Move toward the goal to reduce distance."
    )


class MultimodalLlmPolicy:
    def __init__(self, task_type: str = "open_vocab_navigation") -> None:
        self.task_type = task_type

    async def act(
        self,
        observation: Observation,
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> Action:
        prompt = _read_env_prompt(self.task_type)
        obs_text = json.dumps(observation, ensure_ascii=False)
        goal = scenario.description or (scenario.targets[0].description if scenario.targets else "")
        user_text = (
            f"{prompt}\n\n"
            f"Mission goal: {goal}\n"
            f"Current observation: {obs_text}\n"
            f"History steps: {len(history)}\n"
            "Respond with JSON only."
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        if observation.get("camera_rgb"):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": observation["camera_rgb"], "detail": "auto"},
                }
            )
        messages = [{"role": "user", "content": content}]
        try:
            response = await analysis(messages)
            parsed = parse_model_json(response)
            if "offset" in parsed or "location" in parsed:
                return parsed
        except (AppError, ValueError):
            pass
        return self._heuristic_action(observation)

    @staticmethod
    def _heuristic_action(observation: Observation) -> Action:
        """Fallback when LLM is unavailable: step toward goal."""

        pose = observation.get("pose") or {}
        goal = observation.get("goal_position") or {}
        if "x" in pose and "x" in goal:
            dx = float(goal.get("x", 0)) - float(pose.get("x", 0))
            dy = float(goal.get("y", 0)) - float(pose.get("y", 0))
            norm = math.hypot(dx, dy) or 1.0
            scale = min(10.0, norm)
            return {"offset": [dx / norm * scale, dy / norm * scale], "speed": 25.0, "status": "continue"}
        if "lon" in pose and "lon" in goal:
            dlon = float(goal.get("lon", 0)) - float(pose.get("lon", 0))
            dlat = float(goal.get("lat", 0)) - float(pose.get("lat", 0))
            norm = math.hypot(dlon, dlat) or 1e-9
            return {
                "offset": [dlon / norm * 0.001, dlat / norm * 0.001],
                "speed": 25.0,
                "status": "continue",
            }
        return {"offset": [1.0, 0.0], "speed": 1.0, "status": "continue"}
