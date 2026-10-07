"""\u7a7a\u5730\u534f\u540c\u706d\u706b\u4efb\u52a1\u7684\u8bc4\u4f30\u5668 ``fire_rescue_v1``.

shaped reward \u7ec4\u6210:

* ``step_penalty``       \u2014 \u6bcf\u6b65\u5c0f\u8d1f\u5206, \u9f13\u52b1\u65e9\u5b8c\u5de5
* ``detection_bonus``    \u2014 UAV \u6bcf\u6b21 *\u9996\u6b21* \u53d1\u73b0\u4e00\u4e2a\u706b\u70b9
* ``progress_bonus``     \u2014 UGV \u6bcf\u6b21\u63a8\u8fdb\u706d\u706b\u8fdb\u5ea6 +1
* ``extinguish_bonus``   \u2014 \u4e00\u4e2a\u706b\u5f7b\u5e95\u7184\u706d
* ``safety_penalty``     \u2014 \u5355\u6b65\u4f4d\u79fb > \u9608\u503c (\u7a7f\u6a21)

on_done \u6307\u6807:

* ``SR``                  \u706d\u6389\u7684\u706b\u6570 / \u603b\u706b\u6570
* ``detection_coverage``  UAV \u63a2\u6d4b\u5230\u7684\u706b\u6570 / \u603b\u706b\u6570
* ``mean_response_time``  \u4ece\u63a2\u6d4b\u5230\u6251\u706d\u7684\u5e73\u5747\u6b65\u6570
* ``safety_score``        1 \u2212 \u5927\u5e45\u8df3\u52a8\u5360\u6bd4
"""

from __future__ import annotations

import math
from typing import Any

from app.modules.envs.evaluators import register_evaluator
from app.modules.envs.evaluators.base import EvalStepInput, EvalStepOutput
from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.scenario import ScenarioSpec

Observation = dict[str, Any]


@register_evaluator("fire_rescue_v1")
class FireRescueEvaluator:
    name = "fire_rescue_v1"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.step_penalty = float(cfg.get("step_penalty", -0.02))
        self.detection_bonus = float(cfg.get("detection_bonus", 1.0))
        self.progress_bonus = float(cfg.get("progress_bonus", 0.4))
        self.extinguish_bonus = float(cfg.get("extinguish_bonus", 5.0))
        self.safety_penalty = float(cfg.get("safety_penalty", -0.5))
        self.large_jump_threshold = float(cfg.get("large_jump_threshold", 60.0))

        self._step = 0
        self._jumps = 0
        self._fires: dict[str, dict[str, Any]] = {}
        self._fire_total = 0
        self._first_detected: set[str] = set()
        self._prev_progress: dict[str, int] = {}
        self._prev_pose: dict[str, dict[str, float]] = {}
        self._path_length: dict[str, float] = {}

    def on_reset(
        self,
        scenario: ScenarioSpec,
        initial_obs: Observation,
        interaction: InteractionConfig,
    ) -> None:
        self._step = 0
        self._jumps = 0
        self._first_detected = set()
        self._prev_progress = {}
        self._prev_pose = {}
        self._path_length = {}

        agents_obs = initial_obs.get("agents") or {}
        for name, view in agents_obs.items():
            pose = view.get("pose") or {}
            self._prev_pose[name] = dict(pose)
            self._path_length[name] = 0.0

        self._fires = {}
        for fire in initial_obs.get("fires") or []:
            fid = fire.get("id")
            if not fid:
                continue
            self._fires[fid] = {
                "detected_step": None,
                "extinguished_step": None,
                "first_extinguisher": None,
            }
        self._fire_total = len(self._fires)

    def on_step(self, sample: EvalStepInput) -> EvalStepOutput:
        self._step += 1
        reward = self.step_penalty
        deltas: dict[str, float] = {}
        obs = sample.next_observation

        for fire in (obs.get("agents", {}).get("drone1", {}) or {}).get("visible_fires", []) or []:
            fid = fire.get("id")
            if fid and fid not in self._first_detected:
                self._first_detected.add(fid)
                if fid in self._fires:
                    self._fires[fid]["detected_step"] = self._step
                reward += self.detection_bonus
                deltas[f"detection.{fid}"] = 1.0

        for fire in obs.get("fires") or []:
            fid = fire.get("id")
            if not fid:
                continue
            progress = int(fire.get("progress", 0))
            prev = self._prev_progress.get(fid, 0)
            if progress > prev:
                reward += self.progress_bonus * (progress - prev)
            self._prev_progress[fid] = progress
            if (
                fire.get("status") == "extinguished"
                and self._fires.get(fid, {}).get("extinguished_step") is None
            ):
                self._fires[fid]["extinguished_step"] = self._step
                reward += self.extinguish_bonus
                deltas[f"extinguish.{fid}"] = 1.0

        for name, view in (obs.get("agents") or {}).items():
            pose = view.get("pose") or {}
            if not pose:
                continue
            prev_pose = self._prev_pose.get(name) or pose
            step_len = math.hypot(
                float(pose.get("x", 0)) - float(prev_pose.get("x", 0)),
                float(pose.get("y", 0)) - float(prev_pose.get("y", 0)),
            )
            self._path_length[name] = self._path_length.get(name, 0.0) + step_len
            if step_len > self.large_jump_threshold:
                self._jumps += 1
                reward += self.safety_penalty
            self._prev_pose[name] = dict(pose)

        all_done = bool(self._fires) and all(
            f["extinguished_step"] is not None for f in self._fires.values()
        )
        max_steps = int(sample.scenario.termination.get("max_steps", 60))
        terminated = all_done
        truncated = self._step >= max_steps and not terminated

        return EvalStepOutput(
            reward=reward,
            metric_deltas=deltas,
            terminated=terminated if terminated else None,
            truncated=truncated if truncated else None,
        )

    def on_done(self, trajectory: list[EvalStepInput]) -> dict[str, float]:
        if self._fire_total == 0:
            return {"SR": 0.0, "steps": float(self._step)}
        extinguished = [f for f in self._fires.values() if f["extinguished_step"] is not None]
        detected = [f for f in self._fires.values() if f["detected_step"] is not None]
        sr = len(extinguished) / self._fire_total
        detection_coverage = len(detected) / self._fire_total
        response_times = [
            f["extinguished_step"] - f["detected_step"]
            for f in self._fires.values()
            if f["extinguished_step"] is not None and f["detected_step"] is not None
        ]
        mean_response = (
            sum(response_times) / len(response_times) if response_times else float(self._step)
        )
        safety_score = max(0.0, 1.0 - self._jumps / max(self._step, 1))

        return {
            "SR": sr,
            "fire_total": float(self._fire_total),
            "fires_extinguished": float(len(extinguished)),
            "detection_coverage": detection_coverage,
            "mean_response_time": float(mean_response),
            "steps": float(self._step),
            "safety_score": safety_score,
        }
