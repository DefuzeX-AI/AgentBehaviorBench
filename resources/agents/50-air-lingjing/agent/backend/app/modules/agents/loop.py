"""LangGraph closed-loop agent that drives a Gym-style environment."""

from __future__ import annotations

from typing import Any, TypedDict

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.policies.multimodal_llm_policy import MultimodalLlmPolicy
from app.modules.envs.episode import episode_store
from app.modules.envs.registry import get_env
from app.modules.envs.scenario import ScenarioSpec


class EnvLoopState(TypedDict, total=False):
    env_name: str
    scenario: dict[str, Any]
    task_index: int
    interaction: dict[str, Any]
    evaluator: dict[str, Any]
    max_steps: int
    episode_id: str
    trajectory: list[dict[str, Any]]
    cumulative_reward: float
    metrics: dict[str, float]
    metadata: dict[str, Any]


def build_graph():
    start, end, state_graph = import_langgraph()

    async def create_episode_node(state: EnvLoopState) -> dict[str, Any]:
        env_name = state.get("env_name") or "open_vocab_navigation"
        get_env(env_name)
        scenario_payload = state.get("scenario") or {}
        if isinstance(scenario_payload, dict) and scenario_payload.get("equipmentList"):
            spec = ScenarioSpec.from_obj(scenario_payload, task_index=int(state.get("task_index", 0)))
        else:
            spec = ScenarioSpec.from_obj(scenario_payload, task_index=int(state.get("task_index", 0)))
        record = await episode_store.create(
            env_name,
            spec,
            interaction_override=state.get("interaction"),
            evaluator_spec=state.get("evaluator"),
        )
        return {
            "episode_id": record.episode_id,
            "trajectory": [],
            "cumulative_reward": 0.0,
            "metadata": {
                **state.get("metadata", {}),
                "graph": "open_vocab_navigation_env_loop",
                "framework": "langgraph",
                "resolved_interaction": record.resolved_interaction.to_dict(),
            },
        }

    async def run_loop_node(state: EnvLoopState) -> dict[str, Any]:
        episode_id = state["episode_id"]
        record = episode_store.get(episode_id)
        policy = MultimodalLlmPolicy(task_type=record.scenario.task_type)
        max_steps = int(state.get("max_steps") or record.scenario.termination.get("max_steps", 50))
        trajectory: list[dict[str, Any]] = []
        obs = record.metadata.get("initial_observation") or {}
        for _ in range(max_steps):
            action = await policy.act(obs, record.scenario, trajectory)
            result = await episode_store.step(episode_id, action)
            trajectory.append({"action": action, **result})
            obs = result["observation"]
            if result["terminated"] or result["truncated"]:
                break
        record = episode_store.get(episode_id)
        metrics = trajectory[-1].get("info", {}).get("final_metrics", {}) if trajectory else {}
        return {
            "trajectory": trajectory,
            "cumulative_reward": record.cumulative_reward,
            "metrics": metrics,
        }

    graph = state_graph(EnvLoopState)
    graph.add_node("create_episode", create_episode_node)
    graph.add_node("run_loop", run_loop_node)
    graph.add_edge(start, "create_episode")
    graph.add_edge("create_episode", "run_loop")
    graph.add_edge("run_loop", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="open_vocab_navigation_env_loop",
    description="Closed-loop open-vocabulary navigation with Gym env observe-act-evaluate cycle.",
    builder=build_graph,
)
