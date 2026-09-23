"""Image, container policy and configuration of the egress observer service.

The observer is a separate container on the run's egress network. The model
interceptor hands it every request that is neither a model nor a tool route; it
admits allowlisted destinations (package registries by default), refuses the rest,
and records both on its own event stream. See services/egress-observer/README.md.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from agentbench.runtime.contracts.execution import Deadline
from agentbench.runtime.interception import InterceptorImageProvider, StaticInterceptorImageProvider

from .image_builder import DockerImageBuilder
from .policy import EgressSettings

EGRESS_OBSERVER_IMAGE_ENV = "DEFUZEX_EGRESS_OBSERVER_IMAGE"
EGRESS_PREFIX = "DEFUZEX_EGRESS "
OBSERVER_PORT = 3128


@dataclass(frozen=True, slots=True)
class LocalEgressObserverImageProvider:
    builder: DockerImageBuilder
    context: Path

    def resolve_image(self, *, deadline: Deadline | None = None,
                      log_directory: Path | None = None) -> str:
        return self.builder.build(
            context=self.context,
            dockerfile=self.context / "Dockerfile",
            repository="egress-observer",
            deadline=deadline,
            log_directory=log_directory,
        )


def default_egress_observer_image_provider(
    builder: DockerImageBuilder,
    environ: Mapping[str, str],
) -> InterceptorImageProvider:
    configured = environ.get(EGRESS_OBSERVER_IMAGE_ENV, "").strip()
    if configured:
        return StaticInterceptorImageProvider(configured)
    context = Path(__file__).resolve().parents[2] / "services" / "egress-observer"
    return LocalEgressObserverImageProvider(builder, context)


@dataclass(frozen=True, slots=True)
class EgressObserverPolicy:
    """Unprivileged: the observer only accepts and opens ordinary TCP connections."""

    memory: str = "256m"
    cpus: float = 0.5
    pids_limit: int = 64
    dns_servers: tuple[str, ...] = ()

    def run_arguments(self) -> tuple[str, ...]:
        arguments = (
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={self.pids_limit}",
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
        )
        return (*arguments, *(argument for server in self.dns_servers for argument in ("--dns", server)))


def observer_configuration(agent_id: str, settings: EgressSettings) -> str:
    return json.dumps({"agent_id": agent_id, "listen_port": OBSERVER_PORT, "allow": settings.rules()},
                      ensure_ascii=False)


@dataclass(slots=True)
class RunningEgressObserver:
    container_name: str
    port: int = OBSERVER_PORT
    _close: Callable[[Deadline | None], None] = field(default=lambda deadline=None: None, repr=False)

    def close(self, *, deadline: Deadline | None = None) -> None:
        self._close(deadline)
