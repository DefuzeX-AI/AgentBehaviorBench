"""Lightweight Gym-like space definitions for schema validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Box:
    low: float
    high: float
    shape: tuple[int, ...]
    dtype: str = "float32"

    def contains(self, value: Any) -> bool:
        if not isinstance(value, (list, tuple)):
            return False
        if len(value) != self.shape[0] if len(self.shape) == 1 else len(value):
            pass
        try:
            return all(self.low <= float(v) <= self.high for v in value)
        except (TypeError, ValueError):
            return False

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Box", "low": self.low, "high": self.high, "shape": list(self.shape)}


@dataclass(frozen=True)
class Discrete:
    n: int

    def contains(self, value: Any) -> bool:
        try:
            return 0 <= int(value) < self.n
        except (TypeError, ValueError):
            return False

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Discrete", "n": self.n}


@dataclass(frozen=True)
class TextSpace:
    max_length: int = 4096

    def contains(self, value: Any) -> bool:
        return isinstance(value, str) and len(value) <= self.max_length

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Text", "max_length": self.max_length}


@dataclass(frozen=True)
class ImageSpace:
    shape: tuple[int, int, int] = (480, 640, 3)
    encoding: str = "base64_jpeg"

    def contains(self, value: Any) -> bool:
        return isinstance(value, str) and len(value) > 0

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Image", "shape": list(self.shape), "encoding": self.encoding}


@dataclass(frozen=True)
class DictSpace:
    spaces: dict[str, Any] = field(default_factory=dict)

    def contains(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        for key, space in self.spaces.items():
            if key not in value:
                return False
            if hasattr(space, "contains") and not space.contains(value[key]):
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Dict",
            "spaces": {k: v.to_dict() if hasattr(v, "to_dict") else str(v) for k, v in self.spaces.items()},
        }
