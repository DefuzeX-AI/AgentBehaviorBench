"""Policy interface for closed-loop agents."""

from __future__ import annotations

from typing import Any, Protocol

from app.modules.envs.scenario import ScenarioSpec

Observation = dict[str, Any]
Action = dict[str, Any]


class BasePolicy(Protocol):
    async def act(
        self,
        observation: Observation,
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> Action: ...
