"""Local evaluator for the single-drone fire visual localization case.

This module deliberately does not register with ``app.modules.envs.evaluators``.
``run_case.py`` instantiates it directly so the example remains confined to
``examples/singledrone_fire``.
"""

from __future__ import annotations

import math
from typing import Any

from app.modules.envs.evaluators.base import EvalStepInput, EvalStepOutput
from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.scenario import ScenarioSpec

Observation = dict[str, Any]


def _distance_xy(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.hypot(
        float(a.get("x", 0.0)) - float(b.get("x", 0.0)),
        float(a.get("y", 0.0)) - float(b.get("y", 0.0)),
    )


class SingleDroneFireEvaluator:
    """Score localization or fire-report completion for this local example."""

    name = "singledrone_fire_local"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.step_penalty = float(cfg.get("step_penalty", -0.01))
        self.localization_bonus = float(cfg.get("localization_bonus", 5.0))
        self.safety_penalty = float(cfg.get("safety_penalty", -0.5))
        self.large_jump_threshold = float(cfg.get("large_jump_threshold", 80.0))
        self.default_threshold_m = float(cfg.get("threshold_m", 8.0))

        self._step = 0
        self._jumps = 0
        self._target: dict[str, Any] | None = None
        self._threshold_m = self.default_threshold_m
        self._prev_pose: dict[str, Any] = {}
        self._localized = False
        self._fire_detected = False
        self._fire_reported = False
        self._best_error: float | None = None
        self._last_estimate: dict[str, Any] | None = None

    def on_reset(
        self,
        scenario: ScenarioSpec,
        initial_obs: Observation,
        interaction: InteractionConfig,
    ) -> None:
        self._step = 0
        self._jumps = 0
        self._localized = False
        self._fire_detected = False
        self._fire_reported = False
        self._best_error = None
        self._last_estimate = None

        self._target = None
        for blueprint in scenario.task_matrix:
            image_cfg = blueprint.initial_state.get("image_config") or {}
            if image_cfg.get("localization_threshold_m") is not None:
                self._threshold_m = float(image_cfg["localization_threshold_m"])
            spots = blueprint.initial_state.get("fire_spots") or []
            if spots:
                first = spots[0]
                self._target = {
                    "id": first.get("id", "fire-01"),
                    "x": float(first.get("x", 0.0)),
                    "y": float(first.get("y", 0.0)),
                    "z": float(first.get("z", 0.0)),
                }
                break

        if self._target is None:
            self._target = {"id": "fire-01", "x": 0.0, "y": 0.0, "z": 0.0}

        agent_obs = (initial_obs.get("agents") or {}).get("drone1") or {}
        self._prev_pose = dict(agent_obs.get("pose") or {})

    def on_step(self, sample: EvalStepInput) -> EvalStepOutput:
        self._step += 1
        reward = self.step_penalty
        deltas: dict[str, float] = {}

        agent_obs = (sample.next_observation.get("agents") or {}).get("drone1") or {}
        pose = agent_obs.get("pose") or {}
        if pose and self._prev_pose:
            step_len = _distance_xy(pose, self._prev_pose)
            if step_len > self.large_jump_threshold:
                self._jumps += 1
                reward += self.safety_penalty
        if pose:
            self._prev_pose = dict(pose)

        agent_action = (sample.action.get("agents") or {}).get("drone1") or {}
        fire_detected = bool(agent_action.get("fire_detected"))
        status = str(agent_action.get("status") or "")
        if fire_detected:
            self._fire_detected = True
            deltas["fire_detected"] = 1.0
        if fire_detected and status == "stop":
            self._fire_reported = True
            deltas["fire_reported"] = 1.0
            reward += self.localization_bonus

        estimate = (
            agent_action.get("fire_estimate_world")
            or sample.action.get("fire_estimate_world")
        )
        if isinstance(estimate, dict) and self._target is not None:
            self._last_estimate = dict(estimate)
            error = _distance_xy(estimate, self._target)
            self._best_error = error if self._best_error is None else min(self._best_error, error)
            within = error <= self._threshold_m
            self._localized = self._localized or within
            deltas["localization_error_m"] = error
            deltas["within_threshold"] = float(within)
            if within:
                reward += self.localization_bonus

        max_steps = int(sample.scenario.termination.get("max_steps", 40))
        terminated = bool(self._localized or self._fire_reported)
        truncated = self._step >= max_steps and not terminated
        return EvalStepOutput(
            reward=reward,
            metric_deltas=deltas,
            terminated=terminated if terminated else None,
            truncated=truncated if truncated else None,
        )

    def on_done(self, trajectory: list[EvalStepInput]) -> dict[str, float]:
        error = self._best_error if self._best_error is not None else float("inf")
        success = self._localized or self._fire_reported
        return {
            "SR": 1.0 if success else 0.0,
            "localization_error_m": float(error),
            "within_threshold": 1.0 if self._localized else 0.0,
            "fire_detected": 1.0 if self._fire_detected else 0.0,
            "fire_reported": 1.0 if self._fire_reported else 0.0,
            "threshold_m": float(self._threshold_m),
            "steps": float(self._step),
            "safety_score": max(0.0, 1.0 - self._jumps / max(self._step, 1)),
        }
