"""Create framework adapters from explicit framework registrations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib.metadata import entry_points
from pathlib import Path

from .base import AgentAdapter, AgentDescriptor
from .langgraph import LangGraphAdapter
from .acp import ACPAdapter


AdapterBuilder = Callable[[Path], AgentAdapter]
ADAPTER_ENTRY_POINT_GROUP = "defuzex_agentbench.adapters"


class AdapterFactoryError(RuntimeError):
    """Base error for adapter registration and construction."""


class UnsupportedAdapterError(AdapterFactoryError):
    """Raised when no adapter is registered for an agent framework."""


class AdapterFactory:
    """Registry-backed factory for framework adapter strategies."""

    def __init__(
        self, builders: Mapping[str, AdapterBuilder] | None = None,
        *, entry_point_group: str | None = None,
    ) -> None:
        self._builders: dict[str, AdapterBuilder] = {}
        # Frameworks absent from ``builders`` are looked up lazily in this
        # entry-point group, so an adapter package needs no edit to ABB. Built-ins
        # stay registered in code: the evaluation container runs this package from
        # source, without the distribution metadata entry points come from.
        self._entry_point_group = entry_point_group
        for framework, builder in (builders or {}).items():
            self.register(framework, builder)

    def register(
        self,
        framework: str,
        builder: AdapterBuilder,
        *,
        replace: bool = False,
    ) -> None:
        key = _normalize_framework(framework)
        if key in self._builders and not replace:
            raise AdapterFactoryError(f"Adapter is already registered: {key}")
        self._builders[key] = builder

    def create(self, agent: AgentDescriptor) -> AgentAdapter:
        framework = _normalize_framework(agent.framework)
        builder = self._builders.get(framework) or self._entry_point_builder(framework)
        if builder is None:
            supported = ", ".join(self.frameworks()) or "none"
            raise UnsupportedAdapterError(
                f"Unsupported agent framework {agent.framework!r}; supported: {supported}"
            )

        adapter = builder(agent.path)
        if not isinstance(adapter, AgentAdapter):
            raise AdapterFactoryError(
                f"Builder for {framework!r} did not return an AgentAdapter"
            )
        return adapter

    def frameworks(self) -> tuple[str, ...]:
        names = set(self._builders)
        if self._entry_point_group is not None:
            names.update(_normalize_framework(entry.name)
                         for entry in entry_points(group=self._entry_point_group))
        return tuple(sorted(names))

    def build_requirements(self, framework: str) -> Path | None:
        """Optional adapter-owned dependency file; never instantiate an Agent."""
        key = _normalize_framework(framework)
        builder = self._builders.get(key) or self._entry_point_builder(key)
        owner = getattr(builder, '__self__', builder)
        return getattr(owner, 'build_requirements', None)

    def _entry_point_builder(self, framework: str) -> AdapterBuilder | None:
        if self._entry_point_group is None:
            return None
        for entry in entry_points(group=self._entry_point_group):
            if _normalize_framework(entry.name) == framework:
                loaded = entry.load()
                # An adapter class exposes from_agent_dir; a plain builder is used as is.
                builder = getattr(loaded, "from_agent_dir", loaded)
                if not callable(builder):
                    raise AdapterFactoryError(f"Entry point for {framework!r} is not an adapter builder")
                self.register(framework, builder)
                return builder
        return None


def _normalize_framework(framework: str) -> str:
    if not isinstance(framework, str) or not framework.strip():
        raise AdapterFactoryError("Framework must be a non-empty string")
    return framework.strip().lower()


DEFAULT_ADAPTER_FACTORY = AdapterFactory(
    {"langgraph": LangGraphAdapter.from_agent_dir, "acp": ACPAdapter.from_agent_dir},
    entry_point_group=ADAPTER_ENTRY_POINT_GROUP,
)


def create_adapter(
    agent: AgentDescriptor,
    *,
    factory: AdapterFactory = DEFAULT_ADAPTER_FACTORY,
) -> AgentAdapter:
    """Create the registered adapter for one benchmark agent."""

    return factory.create(agent)
