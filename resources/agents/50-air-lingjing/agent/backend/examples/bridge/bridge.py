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
            "\u65e0\u4eba\u673a\u8d77\u98de\u5230 200m \u540e\u62cd\u6444\u4fef\u89c6\u56fe\uff0c\u5148\u786e\u8ba4\u6865\u6881\u4f4d\u7f6e\uff0c"
            "\u518d\u79fb\u52a8\u5230\u6865\u6881\u9644\u8fd1\u8fdb\u884c\u7ec6\u67e5\uff0c\u53d1\u73b0\u6865\u6881\u65ad\u88c2\u90e8\u5206\u540e\u62a5\u544a\u4efb\u52a1\u5b8c\u6210\uff1b"
            "\u82e5\u89c2\u6d4b\u8fc7\u7a0b\u4e2d\u6865\u6881\u6d88\u5931\u6216\u65e0\u6cd5\u7ee7\u7eed\u5b9a\u4f4d\u6865\u6881\uff0c\u5219\u4efb\u52a1\u5931\u8d25\u3002"
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
                "move_towards_bridge_or_along_bridge",
                "repeat_until_fracture_found_or_bridge_lost",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="\u6865\u6881\u65ad\u88c2\u65e0\u4eba\u673a\u5de1\u68c0_DEMO",
        collaborationType="\u5355\u65e0\u4eba\u673a\u6865\u6881\u5de1\u68c0",
        sceneRegion="\u6865\u6881\u9053\u8def\u533a\u57df",
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

