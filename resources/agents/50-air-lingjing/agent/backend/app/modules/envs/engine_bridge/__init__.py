"""Engine bridge registry."""

from __future__ import annotations

import importlib
import os
from typing import Any

from app.modules.envs.engine_bridge.base import EngineBridge
from app.modules.envs.interaction import InteractionConfig

BRIDGE_REGISTRY: dict[str, type] = {}


def register_bridge(name: str):
    def decorator(cls: type) -> type:
        BRIDGE_REGISTRY[name] = cls
        return cls

    return decorator


def get_bridge(name: str) -> EngineBridge:
    if name not in BRIDGE_REGISTRY:
        raise ValueError(f"Unknown engine bridge: {name}")
    return BRIDGE_REGISTRY[name]()  # type: ignore[call-arg, no-any-return]


def list_bridges() -> list[str]:
    return sorted(BRIDGE_REGISTRY.keys())


def _discover_external() -> None:
    package = os.environ.get("ENV_BRIDGE_USER_PACKAGE", "").strip()
    if package:
        importlib.import_module(package)


from app.modules.envs.engine_bridge import mock_bridge, realtime_bridge  # noqa: E402,F401

_discover_external()
