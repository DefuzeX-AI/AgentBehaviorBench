"""Adapter for legacy \u60f3\u5b9a JSON (sceneName / equipmentList / taskMatrix)."""

from __future__ import annotations

from typing import Any

from app.modules.envs.scenario import AssetSpec, ScenarioSpec, TargetSpec, TaskBlueprint
from app.modules.envs.scenario_adapters import register_adapter

ENTITY_KIND_MAP = {
    "droneEntityList": "uav",
    "unmannedDogEntityList": "robot_dog",
    "autoVehicleEntityList": "ugv",
    "satelliteEntityList": "satellite",
    "shipEntityList": "usv",
    "planeEntityList": "aircraft",
}


def _normalize_position(data: dict[str, Any]) -> dict[str, float]:
    if not data:
        return {}
    if "X" in data or "Y" in data or "Z" in data:
        pos = {
            "x": float(data.get("X", 0)),
            "y": float(data.get("Y", 0)),
            "z": float(data.get("Z", 0)),
        }
        # Mirror UE XYZ into lon/lat fields so mock engine and evaluators share one frame.
        pos.setdefault("lon", pos["x"])
        pos.setdefault("lat", pos["y"])
        pos.setdefault("alt", pos["z"])
        return pos
    if "lon" in data or "lat" in data:
        pos = {
            "lon": float(data.get("lon", 0)),
            "lat": float(data.get("lat", 0)),
            "alt": float(data.get("alt", data.get("Z", 0))),
        }
        pos.setdefault("x", pos["lon"])
        pos.setdefault("y", pos["lat"])
        return pos
    if "line1" in data or "line2" in data:
        return {
            "line1": str(data.get("line1", "")),
            "line2": str(data.get("line2", "")),
        }
    return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}


def _infer_task_type(collaboration: str, goal: str) -> str:
    text = f"{collaboration} {goal}".lower()
    if any(k in text for k in ("\u63a5\u529b", "relay", "\u6295\u9001", "\u7269\u8d44")):
        return "cross_terrain_relay"
    if any(k in text for k in ("\u536b\u661f", "satellite", "\u4e0b\u4f20", "\u89c2\u6d4b")):
        return "satellite_observation"
    if any(k in text for k in ("\u590d\u6838", "\u641c\u7d22", "\u76f2\u533a", "macro", "\u5fae\u89c2")):
        return "cross_domain_target_search"
    if any(k in text for k in ("\u95ee\u7b54", "vqa", "question")):
        return "embodied_vqa"
    if any(k in text for k in ("\u5e8f\u5217", "\u5b50\u4efb\u52a1", "sequence")):
        return "semantic_sequence_planning"
    if any(k in text for k in ("\u7ea6\u675f", "\u80fd\u91cf", "\u98ce\u9669", "constraint")):
        return "constraint_aware_planning"
    if any(k in text for k in ("\u5bfb\u627e", "\u5bfc\u822a", "navigate", "\u76ee\u6807")):
        return "open_vocab_navigation"
    return "open_vocab_navigation"


def _parse_assets(equipment_list: dict[str, Any]) -> list[AssetSpec]:
    assets: list[AssetSpec] = []
    for list_key, kind in ENTITY_KIND_MAP.items():
        for entity in equipment_list.get(list_key) or []:
            data = entity.get("data") or {}
            sensors_raw = entity.get("sensorType")
            sensors = (
                [s.strip() for s in str(sensors_raw).split("/") if s.strip()]
                if sensors_raw
                else []
            )
            heading = entity.get("raw") or entity.get("heading")
            assets.append(
                AssetSpec(
                    id=str(entity.get("equipmentCode") or entity.get("name") or kind),
                    kind=kind,
                    name=str(entity.get("name") or ""),
                    position=_normalize_position(data),
                    heading=float(heading) if heading is not None else None,
                    sensors=sensors,
                    side=entity.get("side"),
                    raw=entity,
                )
            )
    return assets


@register_adapter("lingjing_legacy")
class LingjingLegacyAdapter:
    @classmethod
    def can_parse(cls, payload: dict[str, Any]) -> bool:
        return "equipmentList" in payload and "taskMatrix" in payload

    @classmethod
    def parse(cls, payload: dict[str, Any], *, task_index: int = 0) -> ScenarioSpec:
        equipment = payload.get("equipmentList") or {}
        assets = _parse_assets(equipment)
        matrix = payload.get("taskMatrix") or []
        if not matrix:
            raise ValueError("taskMatrix is empty in legacy scenario")
        task_index = max(0, min(task_index, len(matrix) - 1))
        task = matrix[task_index]
        goal = str(task.get("goal") or "")
        initial = dict(task.get("initial_state") or {})
        goal_pos = dict(initial.get("goalPosition") or {})
        collaboration = str(payload.get("collaborationType") or "")
        task_type = str(payload.get("task_type") or _infer_task_type(collaboration, goal))
        target = TargetSpec(
            id=str(task.get("task_id", "target")),
            description=goal,
            goal_position=goal_pos,
            location_hint=str(payload.get("sceneRegion") or ""),
        )
        blueprints = [
            TaskBlueprint(
                task_id=str(item.get("task_id", f"task_{index}")),
                task_level=str(item.get("taskLevel", "Individual")),
                goal=str(item.get("goal", "")),
                initial_state=dict(item.get("initial_state") or {}),
            )
            for index, item in enumerate(matrix)
        ]
        return ScenarioSpec(
            scenario_id=str(task.get("task_id") or payload.get("sceneName") or "legacy_scenario"),
            task_type=task_type,
            scene_name=str(payload.get("sceneName") or ""),
            scene_code=str(payload.get("sceneCode") or payload.get("sceneName") or ""),
            description=goal,
            collaboration_type=collaboration,
            scene_region=str(payload.get("sceneRegion") or ""),
            assets=assets,
            targets=[target],
            task_matrix=blueprints,
            termination={
                "max_steps": int(payload.get("max_steps") or 50),
                "success_distance": float(payload.get("success_distance") or 5.0),
            },
            interaction=dict(payload.get("interaction") or {}),
            evaluator=dict(payload.get("evaluator") or {"name": "ovn_default"}),
            raw=payload,
        )
