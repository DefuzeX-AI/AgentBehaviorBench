"""Validated container build and launch settings from agent.toml."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]

from agentbench.runtime.contracts import SecretResolver


class ContainerConfigurationError(ValueError):
    """Raised when a Docker agent declaration is invalid."""


@dataclass(frozen=True, slots=True)
class AgentContainerConfig:
    agent_root: Path
    agent_id: str
    build_context: Path
    dockerfile: Path
    argv: tuple[str, ...]
    workdir: str
    timeout_sec: float
    environment: Mapping[str, str]

    @classmethod
    def from_agent_dir(
        cls,
        agent_root: str | Path,
        *,
        secret_resolver: SecretResolver,
        environ: Mapping[str, str] | None = None,
    ) -> "AgentContainerConfig":
        root = Path(agent_root).resolve()
        with (root / "agent.toml").open("rb") as stream:
            manifest = tomllib.load(stream)
        build = _required_table(manifest, "build")
        launch = _required_table(manifest, "launch")
        runtime = _required_table(manifest, "runtime")

        runtime_type = _optional_string(runtime, "type") or "in_process"
        if runtime_type != "docker":
            raise ContainerConfigurationError(
                f"Expected Docker runtime, got {runtime_type!r}"
            )
        context = _resolve_inside(root, _required_string(build, "context"))
        dockerfile = _resolve_inside(context, _required_string(build, "dockerfile"))
        if not dockerfile.is_file():
            raise ContainerConfigurationError(f"Dockerfile does not exist: {dockerfile}")

        argv_value = launch.get("argv")
        if (
            not isinstance(argv_value, list)
            or not argv_value
            or not all(isinstance(item, str) and item for item in argv_value)
        ):
            raise ContainerConfigurationError("launch.argv must be a non-empty string list")

        values = os.environ if environ is None else environ
        environment: dict[str, str] = {}
        for key in _string_list(runtime, "env_keys"):
            if key in values:
                environment[key] = values[key]
        for key in _string_list(runtime, "secret_env_keys"):
            environment[key] = secret_resolver.require(key)

        timeout = runtime.get("timeout_sec", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ContainerConfigurationError("runtime.timeout_sec must be positive")

        return cls(
            agent_root=root,
            agent_id=_required_string(manifest, "agent_id"),
            build_context=context,
            dockerfile=dockerfile,
            argv=tuple(argv_value),
            workdir=_optional_string(launch, "workdir") or "/opt/agent",
            timeout_sec=float(timeout),
            environment=environment,
        )


def runtime_type(agent_root: str | Path) -> str:
    with (Path(agent_root).resolve() / "agent.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    runtime = manifest.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ContainerConfigurationError("Manifest field [runtime] must be a table")
    return _optional_string(runtime, "type") or "in_process"


def _required_table(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ContainerConfigurationError(f"Manifest field [{key}] must be a table")
    return value


def _required_string(data: dict[str, object], key: str) -> str:
    value = _optional_string(data, key)
    if value is None:
        raise ContainerConfigurationError(f"Manifest field must be non-empty: {key}")
    return value


def _optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContainerConfigurationError(f"Manifest field must be non-empty: {key}")
    return value.strip()


def _string_list(data: dict[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ContainerConfigurationError(f"Manifest field must be a string list: {key}")
    return tuple(item.strip() for item in value)


def _resolve_inside(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ContainerConfigurationError(f"Path escapes agent directory: {value}")
    return path
