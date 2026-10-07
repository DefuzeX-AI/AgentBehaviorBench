"""\u591a\u65e0\u4eba\u673a\u914d\u9001\u4efb\u52a1\u7684\u81ea\u5b9a\u4e49\u8bc4\u4f30\u5668 ``delivery_v1``.

\u88ab :class:`app.modules.envs.evaluators._discover_user` \u5728\u542f\u52a8\u65f6\u81ea\u52a8 import.

shaped reward = ``-step_penalty + \u62b5\u8fd1\u5956\u52b1 + \u6295\u9012\u6210\u529f\u5956\u52b1 - \u5b89\u5168\u60e9\u7f5a``;
on_done \u6307\u6807: ``SR / mean_steps_to_deliver / path_efficiency / safety_score``.
"""

from __future__ import annotations

import math
from typing import Any

from app.modules.envs.evaluators import register_evaluator
from app.modules.envs.evaluators.base import EvalStepInput, EvalStepOutput
from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.scenario import ScenarioSpec

Observation = dict[str, Any]


def _eucl(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(
        float(a.get("x", 0)) - float(b.get("x", 0)),
        float(a.get("y", 0)) - float(b.get("y", 0)),
    )


@register_evaluator("delivery_v1")
class MultiDroneDeliveryEvaluator:
    """\u9010\u673a\u8ddf\u8e2a\u914d\u9001\u8fdb\u5ea6\u7684\u8bc4\u4f30\u5668."""

    name = "delivery_v1"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.step_penalty = float(cfg.get("step_penalty", -0.02))
        self.approach_scale = float(cfg.get("approach_scale", 0.05))
        self.delivery_bonus = float(cfg.get("delivery_bonus", 5.0))
        self.success_distance = float(cfg.get("success_distance", 6.0))
        self.large_jump_threshold = float(cfg.get("large_jump_threshold", 60.0))
        self.safety_penalty = float(cfg.get("safety_penalty", -0.5))

        self._targets: dict[str, dict[str, float]] = {}
        self._initial_dist: dict[str, float] = {}
        self._prev_dist: dict[str, float] = {}
        self._delivered: dict[str, int] = {}
        self._steps: int = 0
        self._jumps: int = 0
        self._path_length: dict[str, float] = {}
        self._prev_pose: dict[str, dict[str, float]] = {}

    def on_reset(
        self,
        scenario: ScenarioSpec,
        initial_obs: Observation,
        interaction: InteractionConfig,
    ) -> None:
        self._steps = 0
        self._jumps = 0
        self._delivered = {}
        self._prev_dist = {}
        self._path_length = {}
        self._prev_pose = {}

        targets: dict[str, dict[str, float]] = {}
        drone_names = [a.name for a in scenario.assets if a.kind == "uav" and a.name]
        for index, blueprint in enumerate(scenario.task_matrix):
            drone_name = drone_names[index] if index < len(drone_names) else blueprint.task_id
            goal = blueprint.initial_state.get("goalPosition") or {}
            targets[drone_name] = {
                "x": float(goal.get("lon", goal.get("x", 0))),
                "y": float(goal.get("lat", goal.get("y", 0))),
                "z": float(goal.get("alt", goal.get("z", 0))),
            }
        if not targets:
            targets = dict(initial_obs.get("delivery_targets") or {})
        self._targets = targets

        drones_obs = initial_obs.get("drones") or {}
        for name, target in self._targets.items():
            pose = (drones_obs.get(name) or {}).get("pose") or {}
            d0 = _eucl(pose, target) if pose else 0.0
            self._initial_dist[name] = d0
            self._prev_dist[name] = d0
            self._path_length[name] = 0.0
            self._prev_pose[name] = dict(pose)
            self._delivered[name] = 0

    def on_step(self, sample: EvalStepInput) -> EvalStepOutput:
        self._steps += 1
        reward = self.step_penalty
        deltas: dict[str, float] = {}

        drones_obs = sample.next_observation.get("drones") or {}
        for name, target in self._targets.items():
            drone = drones_obs.get(name) or {}
            pose = drone.get("pose") or {}
            if not pose:
                continue
            dist = _eucl(pose, target)
            prev_dist = self._prev_dist.get(name, dist)

            reward += self.approach_scale * (prev_dist - dist)

            prev_pose = self._prev_pose.get(name) or pose
            step_len = _eucl(pose, prev_pose)
            self._path_length[name] = self._path_length.get(name, 0.0) + step_len
            if step_len > self.large_jump_threshold:
                self._jumps += 1
                reward += self.safety_penalty

            if not self._delivered.get(name) and dist <= self.success_distance:
                reward += self.delivery_bonus
                self._delivered[name] = self._steps

            deltas[f"{name}.distance"] = dist
            deltas[f"{name}.delivered"] = float(bool(self._delivered.get(name)))
            self._prev_dist[name] = dist
            self._prev_pose[name] = dict(pose)

        all_done = bool(self._targets) and all(self._delivered.get(n) for n in self._targets)
        max_steps = int(sample.scenario.termination.get("max_steps", 60))
        terminated = all_done
        truncated = self._steps >= max_steps and not terminated

        return EvalStepOutput(
            reward=reward,
            metric_deltas=deltas,
            terminated=terminated if terminated else None,
            truncated=truncated if truncated else None,
        )

    def on_done(self, trajectory: list[EvalStepInput]) -> dict[str, float]:
        if not self._targets:
            return {"SR": 0.0, "steps": float(self._steps)}
        delivered_count = sum(1 for v in self._delivered.values() if v)
        sr = delivered_count / len(self._targets)

        finish_steps = [v for v in self._delivered.values() if v]
        mean_steps = sum(finish_steps) / len(finish_steps) if finish_steps else float(self._steps)

        efficiencies: list[float] = []
        for name, d0 in self._initial_dist.items():
            traveled = self._path_length.get(name, 0.0)
            if d0 > 1e-3 and traveled > 1e-3:
                efficiencies.append(min(1.0, d0 / traveled))
        path_efficiency = sum(efficiencies) / len(efficiencies) if efficiencies else 0.0

        safety_score = max(0.0, 1.0 - self._jumps / max(self._steps, 1))

        return {
            "SR": sr,
            "delivered_count": float(delivered_count),
            "fleet_size": float(len(self._targets)),
            "steps": float(self._steps),
            "mean_steps_to_deliver": float(mean_steps),
            "path_efficiency": float(path_efficiency),
            "safety_score": float(safety_score),
        }
