"""Engine bridge protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from app.modules.envs.interaction import InteractionConfig

if TYPE_CHECKING:
    from app.modules.envs.scenario import ScenarioSpec


class EngineBridge(Protocol):
    async def reset_scenario(self, spec: ScenarioSpec, cfg: InteractionConfig) -> dict[str, Any]: ...
    async def request_observation(self, query: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]: ...
    async def dispatch_action(self, action: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]: ...
    async def call_custom(self, command_name: str, payload: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]: ...
    async def close(self) -> None: ...
