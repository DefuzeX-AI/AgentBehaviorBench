"""Select in-process or isolated execution from an agent manifest."""

from __future__ import annotations

from collections.abc import Callable

from agentbench.adapter import AdapterFactory, AgentAdapter, AgentDescriptor

from .agentcontainer import ContainerAgentAdapter, runtime_type
from .agentcontainer.adapter import ContainerCaller
from .contracts import AgentRuntime
from .docker import DockerRuntime


RuntimeBuilder = Callable[[], AgentRuntime]


class RuntimeFactoryError(RuntimeError):
    """Raised when a manifest requests an unsupported execution runtime."""


class RuntimeFactory:
    def __init__(
        self, docker_builder: RuntimeBuilder | None = None,
        *, container_caller: ContainerCaller | None = None,
    ) -> None:
        self._docker_builder = docker_builder or DockerRuntime
        self._container_caller = container_caller

    def create_adapter(
        self,
        agent: AgentDescriptor,
        *,
        adapter_factory: AdapterFactory,
    ) -> AgentAdapter:
        selected = runtime_type(agent.path)
        if selected == "in_process":
            return adapter_factory.create(agent)
        if selected == "docker":
            return ContainerAgentAdapter(
                agent, self._docker_builder(), caller=self._container_caller
            )
        raise RuntimeFactoryError(f"Unsupported agent runtime: {selected!r}")


DEFAULT_RUNTIME_FACTORY = RuntimeFactory()
