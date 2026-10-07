"""Base environment classes."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from app.modules.envs.engine_bridge import get_bridge
from app.modules.envs.engine_bridge.base import EngineBridge
from app.modules.envs.evaluators.base import BaseEvaluator, EvalStepInput
from app.modules.envs.interaction import InteractionConfig, resolve_interaction, build_observation_query
from app.modules.envs.scenario import ScenarioSpec

Observation = dict[str, Any]
Action = dict[str, Any]


class BaseEnv(ABC):
    name: str = "base"
    task_type: str = "base"

    def __init__(
        self,
        bridge: EngineBridge | None = None,
        interaction: InteractionConfig | None = None,
        evaluator: BaseEvaluator | None = None,
    ) -> None:
        self.bridge = bridge
        self.interaction = interaction or self.default_interaction()
        self.evaluator = evaluator
        self._scenario: ScenarioSpec | None = None
        self._trajectory: list[EvalStepInput] = []
        self._step_count = 0
        self._last_obs: Observation = {}

    @classmethod
    def default_interaction(cls) -> InteractionConfig:
        return InteractionConfig()

    def _ensure_bridge(self) -> EngineBridge:
        if self.bridge is None:
            self.bridge = get_bridge(self.interaction.bridge)
        return self.bridge

    @abstractmethod
    def observation_space_dict(self) -> dict[str, Any]: ...

    @abstractmethod
    def action_space_dict(self) -> dict[str, Any]: ...

    def _persist(self, payload: dict[str, Any]) -> None:
        """Persist a record into sim_data tagged with the scenario task_id."""

        if not self._scenario or not getattr(self._scenario, "task_id", ""):
            return
        try:
            from app.modules.realtime.manager import realtime_manager

            realtime_manager.persist_task_data(self._scenario.task_id, payload)
        except Exception:  # noqa: BLE001
            pass

    async def reset(self, scenario: ScenarioSpec) -> tuple[Observation, dict[str, Any]]:
        self._scenario = scenario
        self._trajectory = []
        self._step_count = 0
        if self.interaction is None:
            self.interaction = resolve_interaction(
                self.default_interaction(),
                scenario.to_dict() if hasattr(scenario, "to_dict") else scenario,
            )
        self._ensure_bridge()
        if self.evaluator is None:
            from app.modules.envs.evaluators import build_evaluator

            self.evaluator = build_evaluator(scenario.evaluator)
        reset_ack = await self.bridge.reset_scenario(scenario, self.interaction)
        obs = await self.bridge.request_observation(
            build_observation_query(
                {"phase": "reset", "task_id": scenario.task_id},
                self.interaction,
                observation_schema=self.observation_space_dict(),
            ),
            self.interaction,
        )
        self._last_obs = obs
        self.evaluator.on_reset(scenario, obs, self.interaction)
        self._persist(
            {
                "phase": "reset",
                "task_id": scenario.task_id,
                "scenario_id": scenario.scenario_id,
                "task_type": scenario.task_type,
                "engine_ack": reset_ack,
                "initial_observation": obs,
            }
        )
        return obs, {
            "scenario_id": scenario.scenario_id,
            "task_type": scenario.task_type,
            "task_id": scenario.task_id,
        }

    async def step(self, action: Action) -> tuple[Observation, float, bool, bool, dict[str, Any]]:
        if self._scenario is None or self.evaluator is None:
            raise RuntimeError("Environment not reset")
        bridge = self._ensure_bridge()
        action_with_task = dict(action)
        action_with_task.setdefault("task_id", self._scenario.task_id)
        engine_ack = await bridge.dispatch_action(action_with_task, self.interaction)
        interval = float(self.interaction.step_interval_sec or 0.0)
        if interval > 0:
            await asyncio.sleep(interval)
        next_obs = await bridge.request_observation(
            build_observation_query(
                {"phase": "step", "task_id": self._scenario.task_id},
                self.interaction,
                observation_schema=self.observation_space_dict(),
            ),
            self.interaction,
        )
        self._step_count += 1
        sample = EvalStepInput(
            step=self._step_count,
            observation=self._last_obs,
            action=action,
            next_observation=next_obs,
            info={},
            scenario=self._scenario,
            interaction=self.interaction,
        )
        eval_out = self.evaluator.on_step(sample)
        self._trajectory.append(sample)
        self._last_obs = next_obs
        terminated = bool(eval_out.terminated) if eval_out.terminated is not None else False
        truncated = bool(eval_out.truncated) if eval_out.truncated is not None else False
        info = {
            "metric_deltas": eval_out.metric_deltas,
            "notes": eval_out.notes,
            "step": self._step_count,
            "task_id": self._scenario.task_id,
        }
        if terminated or truncated:
            info["final_metrics"] = self.evaluator.on_done(self._trajectory)
        self._persist(
            {
                "phase": "step",
                "task_id": self._scenario.task_id,
                "step": self._step_count,
                "action": action,
                "engine_ack": engine_ack,
                "observation": next_obs,
                "reward": eval_out.reward,
                "terminated": terminated,
                "truncated": truncated,
            }
        )
        return next_obs, eval_out.reward, terminated, truncated, info

    async def close(self) -> None:
        if self.bridge:
            await self.bridge.close()

    def get_trajectory(self) -> list[EvalStepInput]:
        return list(self._trajectory)
