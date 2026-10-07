"""Scenario specification and loading."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.scenario_adapters import detect_adapter, get_adapter

if TYPE_CHECKING:
    from app.modules.envs.scenario_models import ScenarioDefinition


def strip_json_comments(text: str) -> str:
    """Remove ``//`` line comments so legacy \u60f3\u5b9a files can be parsed."""

    lines = []
    for line in text.splitlines():
        if "//" in line:
            in_string = False
            escaped = False
            cut = len(line)
            for index, char in enumerate(line):
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if not in_string and line[index : index + 2] == "//":
                    cut = index
                    break
            lines.append(line[:cut].rstrip())
        else:
            lines.append(line)
    return "\n".join(lines)


@dataclass
class AssetSpec:
    id: str
    kind: str
    name: str
    position: dict[str, float] = field(default_factory=dict)
    heading: float | None = None
    sensors: list[str] = field(default_factory=list)
    side: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetSpec:
    id: str
    description: str = ""
    goal_position: dict[str, float] = field(default_factory=dict)
    location_hint: str = ""


@dataclass
class TaskBlueprint:
    task_id: str
    task_level: str
    goal: str
    initial_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioSpec:
    """Normalized scenario consumed by all env implementations."""

    scenario_id: str
    task_type: str
    scene_name: str = ""
    scene_code: str = ""
    description: str = ""
    collaboration_type: str = ""
    scene_region: str = ""
    assets: list[AssetSpec] = field(default_factory=list)
    targets: list[TargetSpec] = field(default_factory=list)
    task_matrix: list[TaskBlueprint] = field(default_factory=list)
    termination: dict[str, Any] = field(default_factory=dict)
    interaction: InteractionConfig | dict[str, Any] = field(default_factory=InteractionConfig)
    evaluator: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    task_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if isinstance(self.interaction, InteractionConfig):
            data["interaction"] = self.interaction.to_dict()
        return data

    def to_engine_payload(self) -> dict[str, Any]:
        """Render the JSON pushed over WebSocket to LJ-ENGINE on reset.

        When the scenario originated from the legacy \u60f3\u5b9a JSON, the original
        payload is forwarded verbatim with the runtime task_id stamped in.
        Otherwise a synthesised legacy-style envelope is generated from the
        normalized fields so the engine always receives a consistent shape.
        """

        if self.raw and "equipmentList" in self.raw and "taskMatrix" in self.raw:
            payload: dict[str, Any] = json.loads(json.dumps(self.raw))
            payload["taskId"] = self.task_id
            payload["scenarioId"] = self.scenario_id
            payload["taskType"] = self.task_type
            return payload

        equipment: dict[str, list[dict[str, Any]]] = {
            "droneEntityList": [],
            "unmannedDogEntityList": [],
            "autoVehicleEntityList": [],
            "satelliteEntityList": [],
            "shipEntityList": [],
            "planeEntityList": [],
        }
        kind_to_list = {
            "uav": "droneEntityList",
            "robot_dog": "unmannedDogEntityList",
            "ugv": "autoVehicleEntityList",
            "satellite": "satelliteEntityList",
            "usv": "shipEntityList",
            "aircraft": "planeEntityList",
        }
        for asset in self.assets:
            bucket = kind_to_list.get(asset.kind, "droneEntityList")
            entry = {
                "equipmentCode": asset.id,
                "name": asset.name or asset.id,
                "data": dict(asset.position),
            }
            if asset.heading is not None:
                entry["raw" if bucket in {"droneEntityList", "autoVehicleEntityList"} else "heading"] = asset.heading
            if asset.sensors:
                entry["sensorType"] = "/".join(asset.sensors)
            if asset.side:
                entry["side"] = asset.side
            equipment[bucket].append(entry)

        task_matrix: list[dict[str, Any]] = []
        for blueprint in self.task_matrix:
            task_matrix.append(
                {
                    "taskLevel": blueprint.task_level,
                    "task_id": blueprint.task_id,
                    "goal": blueprint.goal,
                    "initial_state": dict(blueprint.initial_state),
                }
            )
        if not task_matrix and self.targets:
            target = self.targets[0]
            task_matrix.append(
                {
                    "taskLevel": "Individual",
                    "task_id": self.scenario_id,
                    "goal": target.description,
                    "initial_state": {"goalPosition": dict(target.goal_position)},
                }
            )

        return {
            "taskId": self.task_id,
            "scenarioId": self.scenario_id,
            "taskType": self.task_type,
            "sceneName": self.scene_name or self.scenario_id,
            "collaborationType": self.collaboration_type,
            "sceneRegion": self.scene_region,
            "equipmentList": equipment,
            "taskMatrix": task_matrix,
        }

    @classmethod
    def from_obj(cls, payload: dict[str, Any], *, task_index: int = 0) -> ScenarioSpec:
        adapter_name = detect_adapter(payload)
        adapter = get_adapter(adapter_name)
        spec = adapter.parse(payload, task_index=task_index)
        spec.task_index = task_index
        return spec

    @classmethod
    def from_definition(
        cls, definition: "ScenarioDefinition", *, task_index: int = 0
    ) -> ScenarioSpec:
        """Build a spec from the user-facing Pydantic ``ScenarioDefinition``."""

        return cls.from_obj(definition.to_engine_payload(), task_index=task_index)

    @classmethod
    def from_file(cls, path: str | Path, *, task_index: int = 0) -> ScenarioSpec:
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".json", ".txt", ".xml"}:
            payload = json.loads(strip_json_comments(text))
        else:
            try:
                import yaml

                payload = yaml.safe_load(text)
            except ImportError as exc:
                raise RuntimeError("PyYAML is required to load YAML scenario files") from exc
        return cls.from_obj(payload, task_index=task_index)

    @classmethod
    def from_text(cls, text: str, *, task_index: int = 0) -> ScenarioSpec:
        stripped = text.strip()
        if stripped.startswith("{"):
            payload = json.loads(strip_json_comments(text))
        else:
            try:
                import yaml

                payload = yaml.safe_load(text)
            except ImportError as exc:
                raise RuntimeError("PyYAML is required to load YAML scenario text") from exc
        return cls.from_obj(payload, task_index=task_index)
