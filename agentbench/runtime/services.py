"""Shared coordination for a single Suite; Docker sessions remain job-owned."""

from __future__ import annotations

import os
from collections.abc import Mapping
from types import MappingProxyType

from .contracts.execution import DockerCleanupError, RuntimeLimits
from .docker.build_coordinator import BuildCoordinator
from .docker.resources import ResourceRegistry


class RuntimeServices:
    def __init__(self, *, environ: Mapping[str, str] | None = None,
                 limits: RuntimeLimits | None = None) -> None:
        self.environ = MappingProxyType(dict(os.environ if environ is None else environ))
        # Historical callers may provide only Agent secrets. Preserve the host
        # CLI essentials, frozen once per Suite rather than reread per worker.
        client_environment = dict(os.environ)
        client_environment.update(self.environ)
        self.command_environ = MappingProxyType(client_environment)
        self.limits = limits or RuntimeLimits()
        self.build_coordinator = BuildCoordinator()
        self.resource_registry = ResourceRegistry()

    def create_docker_runtime(self, **kwargs):
        from .docker.runtime import DockerRuntime
        kwargs.setdefault("environ", self.environ)
        kwargs.setdefault("command_environ", self.command_environ)
        kwargs.setdefault("limits", self.limits)
        kwargs.setdefault("build_coordinator", self.build_coordinator)
        kwargs.setdefault("resource_registry", self.resource_registry)
        return DockerRuntime(**kwargs)

    def close(self) -> None:
        remaining = [item for item in self.resource_registry.snapshot() if item["status"] != "removed"]
        if remaining:
            names = ", ".join(str(item["name"]) for item in remaining)
            raise DockerCleanupError(f"Suite resources were not confirmed removed: {names}")
