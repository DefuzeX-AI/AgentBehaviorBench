"""Invocation handle for a loaded benchmark agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentbench.adapter import AdapterInvocation, AgentAdapter

from ..errors import AgentNotRunningError
from ..registry import AgentRegistration


@dataclass(slots=True)
class RunningAgent:
    """
    A loaded agent and its framework-neutral invocation handle.
    using to control each agent we are running

    "already running" means the agent has been loaded and is ready to accept
    invocations.
    """

    registration: AgentRegistration
    adapter: AgentAdapter
    _stopped: bool = field(default=False, repr=False)

    @property
    def agent_id(self) -> str:
        return self.registration.agent_id

    @property
    def adapter_name(self) -> str:
        return type(self.adapter).__name__

    @property
    def is_running(self) -> bool:
        return not self._stopped and self.adapter.is_loaded

    def invoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        if not self.is_running:
            raise AgentNotRunningError(f"Agent is not running: {self.agent_id}")
        return self.adapter.invoke(value, run_config=run_config)

    async def ainvoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        if not self.is_running:
            raise AgentNotRunningError(f"Agent is not running: {self.agent_id}")
        return await self.adapter.ainvoke(value, run_config=run_config)

    def stop(self) -> None:
        if self._stopped:
            return
        self.adapter.close()
        self._stopped = True

    def __enter__(self) -> "RunningAgent":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        if self._stopped:
            return
        try:
            close = getattr(self.adapter, "aclose", None)
            if callable(close):
                await close()
            else:
                self.adapter.close()
        finally:
            self._stopped = True
