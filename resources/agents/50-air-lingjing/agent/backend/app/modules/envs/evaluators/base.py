"""Evaluator interfaces and composite scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.scenario import ScenarioSpec

Observation = dict[str, Any]
Action = dict[str, Any]


@dataclass
class EvalStepInput:
    step: int
    observation: Observation
    action: Action
    next_observation: Observation
    info: dict[str, Any]
    scenario: ScenarioSpec
    interaction: InteractionConfig


@dataclass
class EvalStepOutput:
    reward: float = 0.0
    metric_deltas: dict[str, float] = field(default_factory=dict)
    terminated: bool | None = None
    truncated: bool | None = None
    notes: dict[str, Any] = field(default_factory=dict)


class BaseEvaluator(Protocol):
    name: str

    def on_reset(
        self,
        scenario: ScenarioSpec,
        initial_obs: Observation,
        interaction: InteractionConfig,
    ) -> None: ...

    def on_step(self, sample: EvalStepInput) -> EvalStepOutput: ...

    def on_done(self, trajectory: list[EvalStepInput]) -> dict[str, float]: ...


class CompositeEvaluator:
    """Combine multiple evaluators with weights."""

    def __init__(self, parts: list[tuple[BaseEvaluator, float]], name: str = "composite") -> None:
        self.name = name
        self.parts = parts

    def on_reset(
        self,
        scenario: ScenarioSpec,
        initial_obs: Observation,
        interaction: InteractionConfig,
    ) -> None:
        for evaluator, _ in self.parts:
            evaluator.on_reset(scenario, initial_obs, interaction)

    def on_step(self, sample: EvalStepInput) -> EvalStepOutput:
        total_reward = 0.0
        metrics: dict[str, float] = {}
        terminated: bool | None = None
        truncated: bool | None = None
        for evaluator, weight in self.parts:
            out = evaluator.on_step(sample)
            total_reward += out.reward * weight
            for key, value in out.metric_deltas.items():
                metrics[f"{evaluator.name}.{key}"] = value
            if out.terminated is not None:
                terminated = terminated or out.terminated
            if out.truncated is not None:
                truncated = truncated or out.truncated
        return EvalStepOutput(
            reward=total_reward,
            metric_deltas=metrics,
            terminated=terminated,
            truncated=truncated,
        )

    def on_done(self, trajectory: list[EvalStepInput]) -> dict[str, float]:
        merged: dict[str, float] = {}
        for evaluator, _ in self.parts:
            for key, value in evaluator.on_done(trajectory).items():
                merged[f"{evaluator.name}.{key}"] = value
        return merged
