"""Evaluator registry with auto-discovery."""

from __future__ import annotations

import importlib
import os
from pkgutil import iter_modules
from typing import Any

from app.modules.envs.evaluators.base import BaseEvaluator, CompositeEvaluator

EVALUATOR_REGISTRY: dict[str, type] = {}


def register_evaluator(name: str):
    def decorator(cls: type) -> type:
        EVALUATOR_REGISTRY[name] = cls
        cls.name = name  # type: ignore[attr-defined]
        return cls

    return decorator


def _discover_builtin() -> None:
    from app.modules.envs.evaluators.builtin import ovn_default  # noqa: F401


def _discover_user() -> None:
    try:
        from app.modules.envs.evaluators import user as user_pkg

        for module_info in iter_modules(user_pkg.__path__):
            if not module_info.ispkg and module_info.name != "__init__":
                importlib.import_module(f"{user_pkg.__name__}.{module_info.name}")
    except ImportError:
        pass


def _discover_external_packages() -> None:
    packages = os.environ.get("EVALUATOR_USER_PACKAGES", "").strip()
    if not packages:
        return
    for package in packages.split(","):
        package = package.strip()
        if package:
            importlib.import_module(package)


def build_evaluator(spec: dict[str, Any] | None) -> BaseEvaluator:
    """Instantiate an evaluator from scenario or episode config."""

    if not spec:
        return get_evaluator("ovn_default", {})

    if "composite" in spec:
        parts: list[tuple[BaseEvaluator, float]] = []
        for item in spec["composite"]:
            parts.append(
                (
                    get_evaluator(str(item["name"]), dict(item.get("config") or {})),
                    float(item.get("weight", 1.0)),
                )
            )
        return CompositeEvaluator(parts)

    return get_evaluator(str(spec.get("name", "ovn_default")), dict(spec.get("config") or {}))


def get_evaluator(name: str, config: dict[str, Any]) -> BaseEvaluator:
    if name not in EVALUATOR_REGISTRY:
        raise ValueError(f"Unknown evaluator: {name}")
    cls = EVALUATOR_REGISTRY[name]
    return cls(config)  # type: ignore[call-arg, no-any-return]


def list_evaluators() -> list[dict[str, str]]:
    return [{"name": name, "class": cls.__name__} for name, cls in EVALUATOR_REGISTRY.items()]


_discover_builtin()
_discover_user()
_discover_external_packages()
