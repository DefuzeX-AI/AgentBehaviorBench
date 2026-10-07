"""Gym-style ``EpisodeHandle`` \u2014 \u628a BaseEnv \u548c\u5f53\u524d episode \u7684 ScenarioSpec \u7ed1\u5728\u4e00\u8d77.

\u63a5\u53e3 (gym v0.26+):
  * ``await handle.reset()`` -> ``(obs, info)``
  * ``await handle.step(action)`` -> ``(obs, reward, terminated, truncated, info)``
  * ``await handle.close()`` -> ``None``

\u4efb\u4f55\u5177\u4f53\u73af\u5883 (multi_drone_delivery / fire_rescue / \u536b\u661f\u89c2\u6d4b ...) \u90fd\u53ef\u4ee5\u5171\u7528\u672c handle.
"""

from __future__ import annotations

from typing import Any

from app.modules.envs.base import BaseEnv
from app.modules.envs.scenario import ScenarioSpec


class EpisodeHandle:
    """\u5355 episode \u5305\u88c5, \u4e0d\u518d\u7ed1\u6b7b\u5177\u4f53\u7684 env \u5b50\u7c7b."""

    def __init__(self, env: BaseEnv, scenario: ScenarioSpec) -> None:
        self.env = env
        self.scenario = scenario
        self.history: list[dict[str, Any]] = []
        self.task_id = scenario.task_id
        self._last_obs: dict[str, Any] = {}
        self._cumulative_reward: float = 0.0
        self.metrics: dict[str, float] = {}
        self.max_steps = int(scenario.termination.get("max_steps", 60))

    async def reset(self) -> tuple[dict[str, Any], dict[str, Any]]:
        self.history.clear()
        self._cumulative_reward = 0.0
        obs, info = await self.env.reset(self.scenario)
        self._last_obs = obs
        return obs, info

    async def step(
        self, action: dict[str, Any]
    ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        obs, reward, terminated, truncated, info = await self.env.step(action)
        self._last_obs = obs
        self._cumulative_reward += float(reward)
        self.history.append(
            {
                "step": info.get("step"),
                "action": action,
                "reward": reward,
                "terminated": terminated,
                "truncated": truncated,
            }
        )
        if terminated or truncated:
            self.metrics = info.get("final_metrics") or {}
        return obs, reward, terminated, truncated, info

    @property
    def cumulative_reward(self) -> float:
        return self._cumulative_reward

    @property
    def observation(self) -> dict[str, Any]:
        return self._last_obs

    async def close(self) -> None:
        await self.env.close()
