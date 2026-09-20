"""Validated service configuration mounted by the AgentBench host."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


CONFIG_ENV = "DEFUZEX_INTERCEPTOR_CONFIG"
DEFAULT_CONFIG = "/run/secrets/interceptor_config"


class ServiceConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Credential:
    credential_id: str
    auth_plugin: str
    token: str
    secret: str


@dataclass(frozen=True, slots=True)
class Route:
    route_id: str
    host_patterns: tuple[str, ...]
    ports: tuple[int, ...]
    methods: tuple[str, ...]
    path_patterns: tuple[str, ...]
    protocol_plugin: str
    credential_id: str


@dataclass(frozen=True, slots=True)
class ToolRoute:
    host_patterns: tuple[str, ...]
    ports: tuple[int, ...]
    methods: tuple[str, ...]
    path_patterns: tuple[str, ...]
    purpose: str = 'tool'
    required: bool = False


@dataclass(frozen=True, slots=True)
class Target:
    provider_id: str
    target_plugin: str
    base_url: str
    model: str
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    agent_id: str
    max_trace_bytes: int
    target: Target
    credentials: tuple[Credential, ...]
    routes: tuple[Route, ...]
    tool_routes: tuple[ToolRoute, ...] = ()
    token_counting: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "ServiceConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ServiceConfigurationError("Interceptor configuration must be an object")
        credentials = tuple(_credential(item) for item in _list(raw, "credentials"))
        route_data = raw.get("routes", [])
        if not isinstance(route_data, list):
            raise ServiceConfigurationError("routes must be a list")
        routes = tuple(_route(item) for item in route_data)
        ids = {item.credential_id for item in credentials}
        if any(route.credential_id not in ids for route in routes):
            raise ServiceConfigurationError("Route references an unknown credential")
        max_bytes = raw.get("max_trace_bytes")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1024:
            raise ServiceConfigurationError("max_trace_bytes must be at least 1024")
        return cls(
            agent_id=_string(raw, "agent_id"),
            max_trace_bytes=max_bytes,
            target=_target(raw.get("target")),
            credentials=credentials,
            routes=routes,
            tool_routes=_tool_routes(raw.get("tool_routes", [])),
            token_counting=_object(raw.get('token_counting', {}), 'token_counting'),
        )


def _credential(value: object) -> Credential:
    data = _object(value, "credential")
    return Credential(
        credential_id=_string(data, "id"),
        auth_plugin=_string(data, "auth_plugin"),
        token=_read_secret(_string(data, "token_file")),
        secret=_read_secret(_string(data, "secret_file")),
    )


def _route(value: object) -> Route:
    data = _object(value, "route")
    return Route(
        route_id=_string(data, "id"),
        host_patterns=_strings(data, "host_patterns"),
        ports=_integers(data, "ports"),
        methods=tuple(item.upper() for item in _strings(data, "methods")),
        path_patterns=_strings(data, "path_patterns"),
        protocol_plugin=_string(data, "protocol_plugin"),
        credential_id=_string(data, "credential"),
    )


def _target(value: object) -> Target:
    data = _object(value, "target")
    headers = data.get("headers", {})
    if not isinstance(headers, dict) or not all(
        isinstance(key, str)
        and key.strip()
        and isinstance(item, str)
        and item.strip()
        for key, item in headers.items()
    ):
        raise ServiceConfigurationError("target headers must be a string object")
    return Target(
        provider_id=_string(data, "provider_id"),
        target_plugin=_string(data, "target_plugin"),
        base_url=_string(data, "base_url"),
        model=_string(data, "model"),
        headers=MappingProxyType(
            {str(key).strip(): str(item).strip() for key, item in headers.items()}
        ),
    )


def _tool_routes(value: object) -> tuple[ToolRoute, ...]:
    if not isinstance(value, list):
        raise ServiceConfigurationError("tool_routes must be a list")
    result = []
    for raw in value:
        data = _object(raw, "tool route")
        hosts, paths = _strings(data, "host_patterns"), _strings(data, "path_patterns")
        if any(h == "*" or any(c in h for c in "?[]/") or
               ("*" in h and (not h.startswith("*.") or h.count("*") != 1)) for h in hosts):
            raise ServiceConfigurationError("Unsafe tool host pattern")
        if any(not p.startswith("/") or p == "/*" or "**" in p or any(c in p for c in "?[]") for p in paths):
            raise ServiceConfigurationError("Unsafe tool path pattern")
        ports = _integers(data, "ports")
        if any(not 1 <= p <= 65535 for p in ports):
            raise ServiceConfigurationError("Invalid tool port")
        purpose = data.get('purpose', 'tool')
        if purpose not in ('tool', 'evaluation', 'metadata', 'content_safety'):
            raise ServiceConfigurationError('Unknown tool route purpose')
        required = data.get('required', False)
        if not isinstance(required, bool):
            raise ServiceConfigurationError('Tool route required must be a boolean')
        result.append(ToolRoute(tuple(h.lower().rstrip(".") for h in hosts), ports,
                                tuple(m.upper() for m in _strings(data, "methods")), paths, purpose, required))
    return tuple(result)


def _read_secret(path: str) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise ServiceConfigurationError(f"Secret file is empty: {path}")
    return value


def _list(data: dict[str, object], key: str) -> list[object]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ServiceConfigurationError(f"{key} must be a non-empty list")
    return value


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ServiceConfigurationError(f"Every {name} must be an object")
    return value


def _string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ServiceConfigurationError(f"{key} must be a non-empty string")
    return value.strip()


def _strings(data: dict[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ServiceConfigurationError(f"{key} must be a non-empty string list")
    return tuple(value)


def _integers(data: dict[str, object], key: str) -> tuple[int, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        raise ServiceConfigurationError(f"{key} must be a non-empty integer list")
    return tuple(value)
