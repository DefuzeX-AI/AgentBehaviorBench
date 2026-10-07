"""Bridge fracture inspection scenario."""

from __future__ import annotations

from typing import Any

from app.modules.envs.scenario_models import (
    DroneEntity,
    EquipmentList,
    InitialState,
    Position,
    ScenarioDefinition,
    TaskMatrixItem,
)

TASK_TYPE = "bridge"
SCENARIO_ID = "BRIDGE_INSPECTION_001"

UAV_DEF: dict[str, Any] = {
    "code": "UAV-BRIDGE-001",
    "name": "drone1",
    "start": {
        "X": -94580.0,
        "Y": 51950.0,
        "Z": 70.0,
        "yaw": 90.0
    },
    "sensor": "RGB/TopDown/BridgeInspection",
}


def _position(data: dict[str, float]) -> Position:
    return Position(**data)


def build_bridge_scenario(*, max_steps: int = 40) -> ScenarioDefinition:
    """Build the default bridge inspection scenario."""

    uav = DroneEntity(
        equipmentCode=UAV_DEF["code"],
        name=UAV_DEF["name"],
        data=_position(UAV_DEF["start"]),
        raw=0.0,
        sensorType=UAV_DEF["sensor"],
    )
    task = TaskMatrixItem(
        taskLevel="Individual",
        task_id=SCENARIO_ID,
        goal=(
            "The UAV takes off to 200m and captures a top-down view, first confirming the bridge location "
            "(the broken bridge spans over the sea, so search toward the open water), "
            "then moves close to the bridge for detailed inspection, and reports the task complete after finding the fractured section of the bridge; "
            "when the bridge is not in view, the UAV keeps searching toward the sea using its forward view."
        ),
        initial_state=InitialState(
            weather="Clear",
            uav_start_position=dict(UAV_DEF["start"]),
            takeoff_height_m=200,
            workflow=[
                "dispatch_scenario_to_airsim_and_image",
                "takeoff_to_200m",
                "request_topdown_photo",
                "vlm_bridge_inspection",
                "if_bridge_lost_use_front_view_to_head_toward_the_sea",
                "move_towards_bridge_or_along_bridge",
                "repeat_until_fracture_found",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="Bridge Fracture UAV Inspection_DEMO",
        collaborationType="Single-UAV bridge inspection",
        sceneRegion="Bridge road area",
        equipmentList=EquipmentList(droneEntityList=[uav]),
        taskMatrix=[task],
        max_steps=max_steps,
        task_type=TASK_TYPE,
        evaluator={"name": "bridge_local"},
    )


def uav_id() -> str:
    return str(UAV_DEF["code"])


def uav_start_position() -> dict[str, float]:
    return dict(UAV_DEF["start"])

