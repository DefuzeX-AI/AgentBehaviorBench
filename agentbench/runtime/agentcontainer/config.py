"""Validated container build and launch settings from agent.toml."""

from __future__ import annotations

import os
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbench.runtime.interception.providers import ModelTargetConfig, ModelTargetProvider

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]

from agentbench.runtime.contracts import SecretResolver


class ContainerConfigurationError(ValueError):
    """Raised when a Docker agent declaration is invalid."""


def validated_memory(value: object) -> str | None:
    """Validate an explicit Agent-only Docker memory limit; None preserves policy."""
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*[bkmg]?", value, re.IGNORECASE | re.ASCII):
        raise ContainerConfigurationError("runtime.memory must be a positive integral Docker size, such as '2g'")
    normalized = value.lower()
    suffix = normalized[-1] if normalized[-1].isalpha() else ''
    digits = normalized[:-1] if suffix else normalized
    if len(digits) > 19:
        raise ContainerConfigurationError("runtime.memory must fit Docker's signed 64-bit byte limit")
    size = int(digits) * {'': 1, 'b': 1, 'k': 1024, 'm': 1024**2, 'g': 1024**3}[suffix]
    if size > 2**63 - 1:
        raise ContainerConfigurationError("runtime.memory must fit Docker's signed 64-bit byte limit")
    if size < 6 * 1024**2:
        raise ContainerConfigurationError("runtime.memory must be at least Docker's minimum of 6m")
    return normalized


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
    model_target: ModelTargetConfig | None = None
    model_metadata_paths: tuple[str, ...] = ()
    replacement_model_provider: ModelTargetProvider | None = None
    memory: str | None = None

    @classmethod
    def from_agent_dir(
        cls,
        agent_root: str | Path,
        *,
        secret_resolver: SecretResolver,
        environ: Mapping[str, str] | None = None,
        model_provider=None,
        resolve_model: bool = True,
    ) -> "AgentContainerConfig":
        root = Path(agent_root).resolve()
        with (root / "agent.toml").open("rb") as stream:
            manifest = tomllib.load(stream)
        runtime = _required_table(manifest, "runtime")
        memory = validated_memory(runtime.get('memory'))
        context, dockerfile, argv_value = docker_structure(root, manifest)
        launch = _required_table(manifest, "launch")

        values = os.environ if environ is None else environ
        environment: dict[str, str] = {}
        # Worker control-plane keys are forwarded to the container, but are not
        # Agent-declared env_keys and are never inherited by an ACP subprocess.
        for key in (*_string_list(runtime, "env_keys"), *_string_list(runtime, "worker_env_keys")):
            if key in values:
                environment[key] = values[key]
        for key in _string_list(runtime, "secret_env_keys"):
            environment[key] = secret_resolver.require(key)

        for key in _string_list(runtime, 'optional_secret_env_keys'):
            if values.get(key):
                environment[key] = secret_resolver.require(key)

        from agentbench.runtime.interception.native_model import (
            model_declaration, resolve_shared_model, model_environment, select_model_provider,
        )
        source, metadata_paths = model_declaration(manifest)
        replacement_provider = (select_model_provider(manifest, values, model_provider)
                                if resolve_model and source == "replace" else None)
        target = resolve_shared_model(manifest, values, model_provider) if resolve_model else None
        if target is not None:
            environment.update(model_environment(target, secret_resolver))

        timeout = runtime.get("timeout_sec", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
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
            model_target=target,
            model_metadata_paths=metadata_paths,
            replacement_model_provider=replacement_provider,
            memory=memory,
        )


def runtime_type(agent_root: str | Path) -> str:
    with (Path(agent_root).resolve() / "agent.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    return manifest_runtime_type(manifest)


def manifest_runtime_type(manifest):
    runtime = manifest.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ContainerConfigurationError("Manifest field [runtime] must be a table")
    selected = _optional_string(runtime, "type") or "in_process"
    if selected not in {"in_process", "docker"}:
        raise ContainerConfigurationError(f"Unsupported agent runtime: {selected!r}")
    return selected


def execution_strategy(agent_root: str | Path) -> str:
    with (Path(agent_root) / "agent.toml").open("rb") as stream:
        value = tomllib.load(stream).get("runtime", {}).get("execution", "native")
    if value not in {"native", "oneshot"}:
        raise ContainerConfigurationError(f"Unsupported runtime.execution: {value}")
    return value


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


def docker_structure(root: Path, manifest):
    """Validate build paths and launch without resolving environment or secrets."""
    from agentbench.sdk.common.workspace import workspace_policy
    workspace_policy(manifest)
    if manifest_runtime_type(manifest) != "docker":
        raise ContainerConfigurationError("Expected Docker runtime")
    build = _required_table(manifest, "build")
    launch = _required_table(manifest, "launch")
    context = _resolve_inside(root, _required_string(build, "context"))
    if not context.is_dir():
        raise ContainerConfigurationError(f"build.context directory does not exist: {context}")
    dockerfile = _resolve_inside(context, _required_string(build, "dockerfile"))
    if not dockerfile.is_file():
        raise FileNotFoundError(f"Dockerfile does not exist: {dockerfile}")
    argv = launch.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise ContainerConfigurationError("launch.argv must be a non-empty string list")
    return context, dockerfile, argv
