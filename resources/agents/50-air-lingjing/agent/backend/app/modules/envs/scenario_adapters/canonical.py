"""Adapter for the canonical flat YAML/JSON scenario format."""

from __future__ import annotations

from typing import Any

from app.modules.envs.interaction import InteractionConfig, _nested_from_dict
from app.modules.envs.scenario import AssetSpec, ScenarioSpec, TargetSpec, TaskBlueprint
from app.modules.envs.scenario_adapters import register_adapter


def _asset_from_dict(item: dict[str, Any]) -> AssetSpec:
    spawn = item.get("spawn") or item.get("position") or {}
    return AssetSpec(
        id=str(item.get("id") or item.get("equipmentCode") or "asset"),
        kind=str(item.get("kind") or item.get("type") or "unknown"),
        name=str(item.get("name") or ""),
        position={k: float(v) for k, v in spawn.items() if isinstance(v, (int, float))},
        heading=float(item["heading"]) if item.get("heading") is not None else None,
        sensors=list(item.get("sensors") or []),
        side=item.get("side"),
        raw=item,
    )


@register_adapter("canonical")
class CanonicalAdapter:
    @classmethod
    def can_parse(cls, payload: dict[str, Any]) -> bool:
        return "task_type" in payload or "assets" in payload

    @classmethod
    def parse(cls, payload: dict[str, Any], *, task_index: int = 0) -> ScenarioSpec:
        interaction_raw = payload.get("interaction")
        interaction = (
            _nested_from_dict(InteractionConfig, interaction_raw)
            if interaction_raw
            else InteractionConfig()
        )
        assets = [_asset_from_dict(a) for a in payload.get("assets") or []]
        targets = [
            TargetSpec(
                id=str(t.get("id", "target")),
                description=str(t.get("description", "")),
                goal_position=dict(t.get("goal_position") or {}),
                location_hint=str(t.get("location_hint", "")),
            )
            for t in payload.get("targets") or []
        ]
        matrix = payload.get("task_matrix") or []
        task_blueprints = [
            TaskBlueprint(
                task_id=str(t.get("task_id", "task")),
                task_level=str(t.get("task_level", "Individual")),
                goal=str(t.get("goal", "")),
                initial_state=dict(t.get("initial_state") or {}),
            )
            for t in matrix
        ]
        return ScenarioSpec(
            scenario_id=str(payload.get("scenario_id") or payload.get("scene_code") or "scenario"),
            task_type=str(payload.get("task_type") or "open_vocab_navigation"),
            scene_name=str(payload.get("scene_name") or payload.get("sceneName") or ""),
            scene_code=str(payload.get("scene_code") or ""),
            description=str(payload.get("description") or ""),
            assets=assets,
            targets=targets,
            task_matrix=task_blueprints,
            termination=dict(payload.get("termination") or {}),
            interaction=interaction,
            evaluator=dict(payload.get("evaluator") or {}),
            raw=payload,
        )
