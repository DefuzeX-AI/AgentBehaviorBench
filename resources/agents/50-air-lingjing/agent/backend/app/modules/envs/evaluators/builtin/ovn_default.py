"""Default evaluator for open-vocabulary navigation."""

from __future__ import annotations

from typing import Any

from app.modules.envs.evaluators import register_evaluator
from app.modules.envs.evaluators.base import EvalStepInput, EvalStepOutput
from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.rewards import distance_delta_reward, euclidean_2d
from app.modules.envs.scenario import ScenarioSpec

Observation = dict[str, Any]


@register_evaluator("ovn_default")
class OpenVocabNavEvaluator:
    name = "ovn_default"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.step_penalty = float(cfg.get("step_penalty", -0.01))
        self.success_bonus = float(cfg.get("success_bonus", 1.0))
        self.success_distance = float(cfg.get("success_distance", 5.0))
        self._goal: dict[str, float] = {}
        self._prev_dist: float | None = None
        self._steps = 0
        self._success = False

    def on_reset(
        self,
        scenario: ScenarioSpec,
        initial_obs: Observation,
        interaction: InteractionConfig,
    ) -> None:
        self._steps = 0
        self._success = False
        self._prev_dist = None
        term = scenario.termination or {}
        self.success_distance = float(term.get("success_distance", self.success_distance))
        if scenario.targets:
            self._goal = dict(scenario.targets[0].goal_position)
        elif scenario.task_matrix:
            initial = scenario.task_matrix[0].initial_state
            self._goal = dict(initial.get("goalPosition") or {})
        else:
            self._goal = dict(initial_obs.get("goal_position") or {})

    def on_step(self, sample: EvalStepInput) -> EvalStepOutput:
        self._steps += 1
        pose = sample.next_observation.get("pose") or {}
        dist = euclidean_2d(pose, self._goal) if self._goal else 0.0
        reward = self.step_penalty
        if self._prev_dist is not None:
            reward += distance_delta_reward(self._prev_dist, dist)
        self._prev_dist = dist
        terminated = False
        if self._goal and dist <= self.success_distance:
            reward += self.success_bonus
            self._success = True
            terminated = True
        max_steps = int(sample.scenario.termination.get("max_steps", 50))
        truncated = self._steps >= max_steps and not terminated
        return EvalStepOutput(
            reward=reward,
            metric_deltas={"distance": dist, "step": float(self._steps)},
            terminated=terminated if terminated else None,
            truncated=truncated if truncated else None,
        )

    def on_done(self, trajectory: list[EvalStepInput]) -> dict[str, float]:
        return {
            "SR": 1.0 if self._success else 0.0,
            "steps": float(self._steps),
            "SPL": 1.0 / max(self._steps, 1) if self._success else 0.0,
        }
