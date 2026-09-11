"""Configuration for loading a registered LangGraph application."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]


class LangGraphConfigurationError(ValueError):
    """Raised when an agent's LangGraph adapter configuration is invalid."""


@dataclass(frozen=True)
class LangGraphAdapterConfig:
    agent_root: Path
    graph_id: str
    entrypoint: str
    input_key: str | None
    output_key: str | None
    mode: str
    binding: str | None = None
    context: dict[str, object] | None = None

    @property
    def source_root(self) -> Path:
        """Source checkout, separate from the outer ABB configuration directory."""
        return (self.agent_root / "agent").resolve()

    @classmethod
    def from_agent_dir(cls, agent_root: str | Path) -> "LangGraphAdapterConfig":
        """Read LangGraph settings from one agent folder."""
        root = Path(agent_root).resolve()
        manifest = _read_toml(root / "agent.toml")
        adapter = _required_mapping(manifest, "adapter")

        adapter_type = _required_string(adapter, "type")
        if adapter_type != "langgraph":
            raise LangGraphConfigurationError(
                f"Expected adapter type 'langgraph', got {adapter_type!r}"
            )

        mode = _optional_string(adapter, "mode") or "in_process"
        if mode != "in_process":
            raise LangGraphConfigurationError(
                f"Unsupported LangGraph execution mode: {mode!r}"
            )

        source_root = _resolve_inside(root, "agent")
        if not source_root.is_dir():
            raise LangGraphConfigurationError(
                f"Agent source directory does not exist: {source_root}"
            )
        config_name = _required_string(adapter, "config")
        config_path = _resolve_inside(source_root, config_name)
        langgraph_config = _read_json(config_path)
        graphs = _required_mapping(langgraph_config, "graphs")
        graph_id = _required_string(adapter, "graph_id")

        try:
            graph_definition = graphs[graph_id]
        except KeyError as exc:
            raise LangGraphConfigurationError(
                f"Graph {graph_id!r} is not declared in {config_path}"
            ) from exc

        entrypoint = _graph_entrypoint(graph_definition, graph_id)
        return cls(
            agent_root=root,
            graph_id=graph_id,
            entrypoint=entrypoint,
            input_key=_optional_string(adapter, "input_key"),
            output_key=_optional_string(adapter, "output_key"),
            mode=mode,
            binding=_optional_string(adapter, "binding"),
            context=_context(adapter),
        )


def _graph_entrypoint(definition: object, graph_id: str) -> str:
    """Read graph entrypoint from langgraph.json."""
    if isinstance(definition, str) and definition.strip():
        return definition
    if isinstance(definition, dict):
        path = definition.get("path")
        if isinstance(path, str) and path.strip():
            return path
    raise LangGraphConfigurationError(
        f"Graph {graph_id!r} must be a path string or an object with a path"
    )


def _read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file."""
    if not path.is_file():
        raise LangGraphConfigurationError(f"Configuration file does not exist: {path}")
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object file."""
    if not path.is_file():
        raise LangGraphConfigurationError(f"Configuration file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            value = json.load(stream)
    except json.JSONDecodeError as exc:
        raise LangGraphConfigurationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LangGraphConfigurationError(f"Configuration must be an object: {path}")
    return value


def _resolve_inside(root: Path, relative_path: str) -> Path:
    """Resolve a path inside the agent folder."""
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise LangGraphConfigurationError(f"Path escapes agent directory: {relative_path}")
    return path


def _required_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Read a required object field."""
    value = data.get(key)
    if not isinstance(value, dict):
        raise LangGraphConfigurationError(f"Field must be an object: {key}")
    return value


def _required_string(data: dict[str, Any], key: str) -> str:
    """Read a required string field."""
    value = _optional_string(data, key)
    if value is None:
        raise LangGraphConfigurationError(f"Field must be a non-empty string: {key}")
    return value


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    """Read an optional string field."""
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LangGraphConfigurationError(f"Field must be a non-empty string: {key}")
    return value


def _context(adapter):
    if "context" not in adapter:
        return None
    value = adapter["context"]
    if not isinstance(value, dict):
        raise LangGraphConfigurationError("Manifest [adapter.context] must be a table")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LangGraphConfigurationError("[adapter.context] must contain JSON-compatible data") from exc
    return deepcopy(value)
