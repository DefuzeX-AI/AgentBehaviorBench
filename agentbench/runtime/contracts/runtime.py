"""Framework-neutral contracts for isolated agent runtimes."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentbench.adapter import AgentDescriptor


@runtime_checkable
class RuntimeSession(Protocol):
    """Process lifecycle only; native Agent communication belongs to a caller."""
    @property
    def is_running(self) -> bool:
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class AgentRuntime(Protocol):
    def start(self, agent: AgentDescriptor) -> RuntimeSession:
        ...
