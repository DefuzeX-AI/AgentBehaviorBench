"""Declarative transparent model interception configuration."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]


class InterceptionConfigurationError(ValueError):
    """Raised when an Agent interception manifest is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class CredentialConfig:
    credential_id: str
    agent_env: str
    auth_plugin: str


@dataclass(frozen=True, slots=True)
class RouteConfig:
    route_id: str
    host_patterns: tuple[str, ...]
    ports: tuple[int, ...]
    methods: tuple[str, ...]
    path_patterns: tuple[str, ...]
    protocol_plugin: str
    credential_id: str

    def matches(self, *, host: str, port: int, method: str, path: str) -> bool:
        normalized_host = host.rstrip(".").lower()
        return (
            port in self.ports
            and method.upper() in self.methods
            and any(
                fnmatch.fnmatchcase(normalized_host, pattern)
                for pattern in self.host_patterns
            )
            and any(fnmatch.fnmatchcase(path, pattern) for pattern in self.path_patterns)
        )


@dataclass(frozen=True, slots=True)
class ToolRouteConfig:
    """Explicit non-model HTTP egress; no credential substitution."""
    host_patterns: tuple[str, ...]
    ports: tuple[int, ...]
    methods: tuple[str, ...]
    path_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InterceptionConfig:
    required: bool
    trust_plugin: str
    environment: Mapping[str, str]
    credentials: tuple[CredentialConfig, ...]
    routes: tuple[RouteConfig, ...]
    tool_routes: tuple[ToolRouteConfig, ...] = ()

    @classmethod
    def from_agent_dir(cls, agent_root: str | Path) -> "InterceptionConfig | None":
        root = Path(agent_root).resolve()
        with (root / "agent.toml").open("rb") as stream:
            manifest = tomllib.load(stream)
        section = manifest.get("llm_interception")
        if section is None:
            return None
        if manifest.get("schema_version") != "defuzex-bench.agent.v2":
            raise InterceptionConfigurationError(
                "[llm_interception] requires schema_version 'defuzex-bench.agent.v2'"
            )
        if not isinstance(section, dict):
            raise InterceptionConfigurationError(
                "Manifest field [llm_interception] must be a table"
            )

        environment = _string_mapping(section.get("environment", {}), "environment")
        credentials = _credentials(section.get("credentials"))
        routes = _routes(section.get("routes"), credentials)
        agent_envs = [item.agent_env for item in credentials]
        if len(set(agent_envs)) != len(agent_envs):
            raise InterceptionConfigurationError(
                "Interception credential agent_env values must be unique"
            )
        overlap = set(environment).intersection(agent_envs)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise InterceptionConfigurationError(
                f"Interception environment cannot override credential variables: {names}"
            )

        return cls(
            required=_boolean(section, "required", default=True),
            trust_plugin=_required_string(section, "trust_plugin"),
            environment=MappingProxyType(environment),
            credentials=credentials,
            routes=routes,
            tool_routes=_tool_routes(section.get("tool_routes", [])),
        )


def _tool_routes(value: object) -> tuple[ToolRouteConfig, ...]:
    if not isinstance(value, list):
        raise InterceptionConfigurationError("tool_routes must be a table array")
    result = []
    for raw in value:
        if not isinstance(raw, dict):
            raise InterceptionConfigurationError("Every tool route must be a table")
        result.append(ToolRouteConfig(
            host_patterns=_patterns(raw, "host_patterns", host=True),
            ports=_ports(raw.get("ports", [443])),
            methods=tuple(v.upper() for v in _string_list(raw, "methods")),
            path_patterns=_patterns(raw, "path_patterns", host=False),
        ))
    return tuple(result)


def _credentials(value: object) -> tuple[CredentialConfig, ...]:
    if not isinstance(value, list) or not value:
        raise InterceptionConfigurationError(
            "llm_interception.credentials must be a non-empty table array"
        )
    items: list[CredentialConfig] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise InterceptionConfigurationError(
                "Every interception credential must be a table"
            )
        items.append(
            CredentialConfig(
                credential_id=_required_string(raw, "id"),
                agent_env=_required_string(raw, "agent_env"),
                auth_plugin=_required_string(raw, "auth_plugin"),
            )
        )
    _require_unique((item.credential_id for item in items), "credential id")
    return tuple(items)


def _routes(
    value: object, credentials: tuple[CredentialConfig, ...]
) -> tuple[RouteConfig, ...]:
    if not isinstance(value, list) or not value:
        raise InterceptionConfigurationError(
            "llm_interception.routes must be a non-empty table array"
        )
    credential_ids = {item.credential_id for item in credentials}
    items: list[RouteConfig] = []
    signatures: set[tuple[object, ...]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise InterceptionConfigurationError("Every interception route must be a table")
        credential_id = _required_string(raw, "credential")
        if credential_id not in credential_ids:
            raise InterceptionConfigurationError(
                f"Interception route references unknown credential: {credential_id}"
            )
        host_patterns = _patterns(raw, "host_patterns", host=True)
        path_patterns = _patterns(raw, "path_patterns", host=False)
        ports = _ports(raw.get("ports", [443]))
        methods = tuple(item.upper() for item in _string_list(raw, "methods"))
        item = RouteConfig(
            route_id=_required_string(raw, "id"),
            host_patterns=host_patterns,
            ports=ports,
            methods=methods,
            path_patterns=path_patterns,
            protocol_plugin=_required_string(raw, "protocol_plugin"),
            credential_id=credential_id,
        )
        signature = (host_patterns, ports, methods, path_patterns)
        if signature in signatures:
            raise InterceptionConfigurationError(
                "Interception routes cannot declare identical match patterns"
            )
        signatures.add(signature)
        items.append(item)
    _require_unique((item.route_id for item in items), "route id")
    return tuple(items)


def _patterns(data: Mapping[str, object], key: str, *, host: bool) -> tuple[str, ...]:
    values = _string_list(data, key)
    normalized: list[str] = []
    for value in values:
        pattern = value.rstrip(".").lower() if host else value
        if pattern in {"*", "/*"} or any(marker in pattern for marker in ("?", "[", "]", "**")):
            raise InterceptionConfigurationError(
                f"Unsafe interception pattern in {key}: {value!r}"
            )
        if host and "*" in pattern and not pattern.startswith("*."):
            raise InterceptionConfigurationError(
                f"Host wildcard must be a leading '*.' pattern: {value!r}"
            )
        if host and pattern.count("*") > 1:
            raise InterceptionConfigurationError(
                f"Host pattern contains too many wildcards: {value!r}"
            )
        if not host and not pattern.startswith("/"):
            raise InterceptionConfigurationError(
                f"Path pattern must start with '/': {value!r}"
            )
        normalized.append(pattern)
    return tuple(normalized)


def _ports(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise InterceptionConfigurationError("Interception ports must be a non-empty list")
    ports: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 65535:
            raise InterceptionConfigurationError(f"Invalid interception port: {item!r}")
        ports.append(item)
    return tuple(ports)


def _string_mapping(value: object, name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise InterceptionConfigurationError(
            f"llm_interception.{name} must be a string table"
        )
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, str):
            raise InterceptionConfigurationError(
                f"llm_interception.{name} must contain string keys and values"
            )
        result[key.strip()] = item
    return result


def _string_list(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise InterceptionConfigurationError(f"{key} must be a non-empty string list")
    return tuple(item.strip() for item in value)


def _required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InterceptionConfigurationError(f"Interception field must be non-empty: {key}")
    return value.strip()


def _boolean(data: Mapping[str, object], key: str, *, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise InterceptionConfigurationError(f"Interception field must be boolean: {key}")
    return value


def _require_unique(values: object, label: str) -> None:
    items = tuple(values)  # type: ignore[arg-type]
    if len(set(items)) != len(items):
        raise InterceptionConfigurationError(f"Interception {label} values must be unique")
