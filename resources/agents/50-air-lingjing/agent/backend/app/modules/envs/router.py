"""HTTP API for Gym-style environment episodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile
from pydantic import ValidationError

from app.core.responses import AppError, json_success
from app.modules.envs.engine_bridge import list_bridges
from app.modules.envs.episode import episode_store
from app.modules.envs.evaluators import list_evaluators
from app.modules.envs.registry import get_env, list_envs
from app.modules.envs.scenario import ScenarioSpec
from app.modules.envs.scenario_models import ScenarioDefinition

router = APIRouter(prefix="/api/envs")


def _coerce_definition(payload: dict[str, Any]) -> ScenarioSpec | None:
    """Detect the user-facing ScenarioDefinition shape and validate it."""

    if not (payload.get("equipmentList") or payload.get("taskMatrix")):
        return None
    try:
        definition = ScenarioDefinition.model_validate(payload)
    except ValidationError as exc:
        raise AppError(f"\u60f3\u5b9a\u6587\u4ef6\u4e0d\u7b26\u5408 ScenarioDefinition \u7c7b\u7ea6\u675f: {exc.errors()[:3]}") from exc
    return ScenarioSpec.from_definition(definition)


def _parse_scenario_payload(payload: dict[str, Any]) -> ScenarioSpec:
    task_index = int(payload.get("task_index", 0))
    if "scenario_text" in payload:
        return ScenarioSpec.from_text(str(payload["scenario_text"]), task_index=task_index)
    if "scenario_path" in payload:
        return ScenarioSpec.from_file(payload["scenario_path"], task_index=task_index)
    if "definition" in payload and isinstance(payload["definition"], dict):
        try:
            definition = ScenarioDefinition.model_validate(payload["definition"])
        except ValidationError as exc:
            raise AppError(f"\u60f3\u5b9a\u6587\u4ef6\u4e0d\u7b26\u5408 ScenarioDefinition \u7c7b\u7ea6\u675f: {exc.errors()[:3]}") from exc
        return ScenarioSpec.from_definition(definition, task_index=task_index)
    scenario = payload.get("scenario")
    if isinstance(scenario, dict):
        coerced = _coerce_definition(scenario)
        if coerced is not None:
            coerced.task_index = task_index
            return coerced
        return ScenarioSpec.from_obj(scenario, task_index=task_index)
    if isinstance(scenario, str) and Path(scenario).exists():
        return ScenarioSpec.from_file(scenario, task_index=task_index)
    raise AppError("scenario, scenario_text, scenario_path \u6216 definition \u81f3\u5c11\u9700\u63d0\u4f9b\u4e00\u4e2a")


@router.get("")
def get_envs():
    return json_success(list_envs())


@router.get("/bridges")
def get_bridges():
    return json_success(list_bridges())


@router.get("/evaluators")
def get_evaluators():
    return json_success(list_evaluators())


@router.post("/{env_name}/episodes")
async def create_episode(env_name: str, payload: dict[str, Any]):
    get_env(env_name)
    scenario = _parse_scenario_payload(payload)
    record = await episode_store.create(
        env_name,
        scenario,
        interaction_override=payload.get("interaction"),
        evaluator_spec=payload.get("evaluator"),
    )
    return json_success(
        {
            "episode_id": record.episode_id,
            "task_id": record.task_id,
            "created_at_beijing": record.created_at_beijing,
            "engine_scenario_payload": record.scenario.to_engine_payload(),
            "initial_observation": record.metadata.get("initial_observation"),
            "resolved_interaction": record.resolved_interaction.to_dict(),
            "resolved_evaluator": record.resolved_evaluator_name,
            "metadata": record.metadata,
        }
    )


@router.post("/scenarios/upload")
async def upload_scenario(file: UploadFile):
    """Upload a \u60f3\u5b9a file and return parsed scenario previews."""

    text = (await file.read()).decode("utf-8")
    spec = ScenarioSpec.from_text(text, task_index=0)
    matrix_len = len(spec.task_matrix)
    previews = []
    for index in range(max(matrix_len, 1)):
        item = ScenarioSpec.from_text(text, task_index=index)
        previews.append(
            {
                "task_index": index,
                "scenario_id": item.scenario_id,
                "task_type": item.task_type,
                "goal": item.description,
            }
        )
    return json_success({"previews": previews, "task_count": matrix_len or 1})


@router.post("/episodes/{episode_id}/step")
async def step_episode(episode_id: str, payload: dict[str, Any]):
    action = payload.get("action") or {}
    return json_success(await episode_store.step(episode_id, action))


@router.post("/episodes/{episode_id}/run")
async def run_episode(episode_id: str, payload: dict[str, Any] | None = None):
    from app.modules.agents.policies.multimodal_llm_policy import MultimodalLlmPolicy

    payload = payload or {}
    record = episode_store.get(episode_id)
    policy = MultimodalLlmPolicy(task_type=record.scenario.task_type)
    max_steps = int(payload.get("max_steps") or record.scenario.termination.get("max_steps", 50))
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
    final_metrics = {}
    if trajectory:
        final_metrics = trajectory[-1].get("info", {}).get("final_metrics", {})
    return json_success(
        {
            "trajectory": trajectory,
            "cumulative_reward": record.cumulative_reward,
            "metrics": final_metrics,
            "status": record.status,
        }
    )


@router.get("/episodes/{episode_id}")
def get_episode(episode_id: str):
    record = episode_store.get(episode_id)
    return json_success(
        {
            "episode_id": record.episode_id,
            "task_id": record.task_id,
            "created_at_beijing": record.created_at_beijing,
            "env_name": record.env_name,
            "status": record.status,
            "cumulative_reward": record.cumulative_reward,
            "resolved_interaction": record.resolved_interaction.to_dict(),
            "resolved_evaluator": record.resolved_evaluator_name,
            "scenario": record.scenario.to_dict(),
        }
    )


@router.get("/scenarios/schema")
def get_scenario_schema():
    """Return the JSON schema of the user-facing ScenarioDefinition class."""

    return json_success(ScenarioDefinition.model_json_schema())


@router.post("/episodes/{episode_id}/rescore")
async def rescore_episode(episode_id: str, payload: dict[str, Any]):
    evaluator_spec = payload.get("evaluator") or {"name": "ovn_default"}
    metrics = await episode_store.rescore(episode_id, evaluator_spec)
    return json_success({"metrics": metrics})


@router.delete("/episodes/{episode_id}")
async def delete_episode(episode_id: str):
    await episode_store.close(episode_id)
    return json_success("closed")
