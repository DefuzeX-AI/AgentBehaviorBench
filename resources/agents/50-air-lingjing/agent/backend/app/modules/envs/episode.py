"""In-memory episode lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.envs.base import BaseEnv
from app.modules.envs.evaluators import build_evaluator
from app.modules.envs.evaluators.base import EvalStepInput
from app.modules.envs.interaction import InteractionConfig, resolve_interaction
from app.modules.envs.registry import create_env
from app.modules.envs.scenario import ScenarioSpec
from app.modules.envs.task_id import beijing_iso, make_task_id

Observation = dict[str, Any]
Action = dict[str, Any]


@dataclass
class EpisodeRecord:
    episode_id: str
    env_name: str
    env: BaseEnv
    scenario: ScenarioSpec
    resolved_interaction: InteractionConfig
    resolved_evaluator_name: str
    task_id: str = ""
    created_at_beijing: str = ""
    cumulative_reward: float = 0.0
    status: str = "running"
    metadata: dict[str, Any] = field(default_factory=dict)


class EpisodeStore:
    def __init__(self) -> None:
        self._episodes: dict[str, EpisodeRecord] = {}

    async def create(
        self,
        env_name: str,
        scenario: ScenarioSpec,
        *,
        interaction_override: dict[str, Any] | None = None,
        evaluator_spec: dict[str, Any] | None = None,
    ) -> EpisodeRecord:
        env = create_env(env_name)
        if evaluator_spec is not None:
            env.evaluator = build_evaluator(evaluator_spec)
        elif scenario.evaluator:
            env.evaluator = build_evaluator(scenario.evaluator)

        resolved = resolve_interaction(
            env.default_interaction(),
            scenario.to_dict(),
            interaction_override,
        )
        env.interaction = resolved

        if not scenario.task_id:
            scenario.task_id = make_task_id(prefix=scenario.task_type or "task")

        initial_obs, info = await env.reset(scenario)
        eval_name = (
            str(evaluator_spec.get("name"))
            if evaluator_spec and evaluator_spec.get("name")
            else str((scenario.evaluator or {}).get("name", "ovn_default"))
        )
        record = EpisodeRecord(
            episode_id=scenario.task_id,
            env_name=env_name,
            env=env,
            scenario=scenario,
            resolved_interaction=resolved,
            resolved_evaluator_name=eval_name,
            task_id=scenario.task_id,
            created_at_beijing=beijing_iso(),
            metadata={"initial_info": info, "initial_observation": initial_obs},
        )
        self._episodes[scenario.task_id] = record
        return record

    def get(self, episode_id: str) -> EpisodeRecord:
        if episode_id not in self._episodes:
            raise ValueError(f"Episode not found: {episode_id}")
        return self._episodes[episode_id]

    async def step(self, episode_id: str, action: Action) -> dict[str, Any]:
        record = self.get(episode_id)
        obs, reward, terminated, truncated, info = await record.env.step(action)
        record.cumulative_reward += reward
        if terminated or truncated:
            record.status = "done"
        return {
            "observation": obs,
            "reward": reward,
            "terminated": terminated,
            "truncated": truncated,
            "info": info,
            "cumulative_reward": record.cumulative_reward,
        }

    async def close(self, episode_id: str) -> None:
        record = self.get(episode_id)
        await record.env.close()
        record.status = "closed"
        self._episodes.pop(episode_id, None)

    async def rescore(self, episode_id: str, evaluator_spec: dict[str, Any]) -> dict[str, float]:
        record = self.get(episode_id)
        evaluator = build_evaluator(evaluator_spec)
        trajectory = record.env.get_trajectory()
        if trajectory:
            evaluator.on_reset(record.scenario, trajectory[0].observation, record.resolved_interaction)
            for sample in trajectory:
                evaluator.on_step(sample)
        return evaluator.on_done(trajectory)


episode_store = EpisodeStore()
