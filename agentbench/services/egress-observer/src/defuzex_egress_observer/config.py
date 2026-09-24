"""Validated observer configuration passed by the AgentBench host."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .policy import AllowList, AllowRule

CONFIG_ENV = "ABB_EGRESS_CONFIG"
DEFAULT_PORT = 3128


class ObserverConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObserverConfig:
    agent_id: str
    allow: AllowList
    listen_port: int = DEFAULT_PORT
    connect_timeout: float = 15.0

    @classmethod
    def from_environment(cls, environ=None) -> "ObserverConfig":
        raw = (os.environ if environ is None else environ).get(CONFIG_ENV)
        if not raw:
            raise ObserverConfigurationError(f"{CONFIG_ENV} is required")
        return cls.from_json(raw)

    @classmethod
    def from_json(cls, text: str) -> "ObserverConfig":
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ObserverConfigurationError("Observer configuration must be JSON") from exc
        if not isinstance(data, dict):
            raise ObserverConfigurationError("Observer configuration must be an object")
        agent_id = data.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ObserverConfigurationError("agent_id must be a non-empty string")
        port = data.get("listen_port", DEFAULT_PORT)
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            raise ObserverConfigurationError("listen_port must be an unprivileged port")
        allow = data.get("allow", [])
        if not isinstance(allow, list):
            raise ObserverConfigurationError("allow must be a list")
        return cls(agent_id=agent_id.strip(), listen_port=port,
                   allow=AllowList(tuple(_rule(item) for item in allow)))


def _rule(value: object) -> AllowRule:
    if not isinstance(value, dict):
        raise ObserverConfigurationError("Every allow rule must be an object")
    ports = value.get("ports")
    if not isinstance(ports, list) or not ports or any(
            isinstance(p, bool) or not isinstance(p, int) or not 1 <= p <= 65535 for p in ports):
        raise ObserverConfigurationError("Allow rule ports must be a non-empty port list")
    try:
        return AllowRule(value.get("host"), tuple(ports))
    except ValueError as exc:
        raise ObserverConfigurationError(str(exc)) from exc
