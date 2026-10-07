"""Shared reward primitives for built-in evaluators."""

from __future__ import annotations

import math
from typing import Any


def euclidean_2d(a: dict[str, float], b: dict[str, float]) -> float:
    """Distance using x/y or lon/lat keys."""

    if "x" in a or "y" in a:
        ax, ay = float(a.get("x", 0)), float(a.get("y", 0))
        bx, by = float(b.get("x", 0)), float(b.get("y", 0))
        return math.hypot(ax - bx, ay - by)
    alon, alat = float(a.get("lon", 0)), float(a.get("lat", 0))
    blon, blat = float(b.get("lon", 0)), float(b.get("lat", 0))
    return math.hypot(alon - blon, alat - blat) * 111_000.0


def distance_delta_reward(prev_dist: float, curr_dist: float, scale: float = 0.01) -> float:
    return (prev_dist - curr_dist) * scale
