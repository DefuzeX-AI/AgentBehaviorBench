"""Pluggable scenario format adapters."""

from __future__ import annotations

from typing import Any

ADAPTER_REGISTRY: dict[str, type] = {}
_LOADED = False


def register_adapter(name: str):
    def decorator(cls: type) -> type:
        ADAPTER_REGISTRY[name] = cls
        return cls

    return decorator


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    from app.modules.envs.scenario_adapters import canonical, lingjing_legacy  # noqa: F401

    _LOADED = True


def detect_adapter(payload: dict[str, Any]) -> str:
    if "equipmentList" in payload and "taskMatrix" in payload:
        return "lingjing_legacy"
    if "task_type" in payload or "assets" in payload:
        return "canonical"
    return "canonical"


def get_adapter(name: str) -> type:
    _ensure_loaded()
    if name not in ADAPTER_REGISTRY:
        raise ValueError(f"Unknown scenario adapter: {name}")
    return ADAPTER_REGISTRY[name]
