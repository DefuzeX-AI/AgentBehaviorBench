"""In-process mock engine for development and tests."""

from __future__ import annotations

import math
from typing import Any

from app.modules.envs.engine_bridge import register_bridge
from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.rewards import euclidean_2d
from app.modules.envs.scenario import ScenarioSpec


@register_bridge("mock")
class MockEngineBridge:
    """Simple 2D navigation simulator."""

    def __init__(self) -> None:
        self._pose: dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._goal: dict[str, float] = {}
        self._step = 0

    async def reset_scenario(self, spec: ScenarioSpec, cfg: InteractionConfig) -> dict[str, Any]:
        self._step = 0
        if spec.assets:
            pos = spec.assets[0].position
            if "x" in pos or "y" in pos:
                self._pose = {"x": pos.get("x", 0), "y": pos.get("y", 0), "z": pos.get("z", 0)}
            else:
                self._pose = {
                    "lon": pos.get("lon", 0),
                    "lat": pos.get("lat", 0),
                    "alt": pos.get("alt", 0),
                }
        if spec.targets:
            self._goal = dict(spec.targets[0].goal_position)
        elif spec.task_matrix:
            self._goal = dict(spec.task_matrix[0].initial_state.get("goalPosition") or {})
        return {"status": "reset", "pose": dict(self._pose), "goal": dict(self._goal)}

    async def request_observation(self, query: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]:
        modalities = cfg.observation.modalities
        obs: dict[str, Any] = {
            "step": self._step,
            "pose": dict(self._pose),
            "goal_position": dict(self._goal),
            "distance": euclidean_2d(self._pose, self._goal) if self._goal else 0.0,
        }
        if "camera_rgb" in modalities:
            obs["camera_rgb"] = ""
        if "minimap" in modalities:
            obs["minimap"] = ""
        return obs

    async def dispatch_action(self, action: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]:
        self._step += 1
        offset = action.get("offset") or action.get("location") or {}
        if isinstance(offset, (list, tuple)):
            dx = float(offset[0]) if len(offset) > 0 else 0.0
            dy = float(offset[1]) if len(offset) > 1 else 0.0
        elif isinstance(offset, dict):
            dx = float(offset.get("x", offset.get("dx", 0)))
            dy = float(offset.get("y", offset.get("dy", 0)))
        else:
            dx, dy = 0.0, 0.0
        if "x" in self._pose:
            self._pose["x"] = float(self._pose.get("x", 0)) + dx
            self._pose["y"] = float(self._pose.get("y", 0)) + dy
        else:
            scale = 1e-5
            self._pose["lon"] = float(self._pose.get("lon", 0)) + dx * scale
            self._pose["lat"] = float(self._pose.get("lat", 0)) + dy * scale
        speed = float(action.get("speed", action.get("command", {}).get("speed", 1.0) if isinstance(action.get("command"), dict) else 1.0))
        if speed > 1:
            if "x" in self._pose:
                self._pose["x"] += dx * (speed - 1)
                self._pose["y"] += dy * (speed - 1)
        return {"status": "ack", "pose": dict(self._pose)}

    async def call_custom(self, command_name: str, payload: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]:
        custom = cfg.engine_commands.custom.get(command_name, command_name)
        return {"command": custom, "payload": payload, "status": "ok"}

    async def close(self) -> None:
        return None
