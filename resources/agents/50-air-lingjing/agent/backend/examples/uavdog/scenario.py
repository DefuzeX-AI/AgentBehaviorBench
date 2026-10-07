"""UAV-guided robot dog navigation scenario (UAV plans, ground robot dog executes).

A UAV holds altitude and, from its top-down view, recognizes the robot dog's heading and
position (marked by a green arrow / green dot) and plans a segmented, junction-by-junction path
for the dog toward the green house; the dog executes each path, the UAV re-checks by photo, and
on collision it re-plans from the dog's latest pose, until the dog reaches the green house.
"""

from __future__ import annotations

from typing import Any

from app.modules.envs.scenario_models import (
    DroneEntity,
    EquipmentList,
    InitialState,
    Position,
    ScenarioDefinition,
    TaskMatrixItem,
    UnmannedDogEntity,
)

TASK_TYPE = "uavdog"
SCENARIO_ID = "UAVDOG_PATH_PLANNING_001"

# UAV cruise/planning height (meters). The vision prompt (prompts/uavdog_path_planning.txt) also
# uses this height for pixel->world conversion, so keep them consistent.
UAV_HEIGHT_M = 280.0

UAV_DEF: dict[str, Any] = {
    "code": "UAV-UAVDOG-001",
    "name": "drone1",
    "start": {"X": -470864.375, "Y": 218871.25, "Z": -242872.501137},
    "raw": 0.0,
    "sensor": "RGB/TopDown/DogPathPlanning",
}

# The ground robot dog is placed with geographic coordinates (lon/lat/alt), as in the original scenario.
DOG_DEF: dict[str, Any] = {
    "code": "UGV-UAVDOG-001",
    "name": "dog1",
    "start": {"lon": 109.95065196, "lat": 39.82535188, "alt": -176.55242063},
}


def _position(data: dict[str, float]) -> Position:
    return Position(**data)


def build_uavdog_scenario(*, max_steps: int = 60) -> ScenarioDefinition:
    """Build the UAV-guided robot dog path-planning scenario (UAV overhead + dog on the ground)."""

    drone = DroneEntity(
        equipmentCode=UAV_DEF["code"],
        name=UAV_DEF["name"],
        data=_position(UAV_DEF["start"]),
        raw=UAV_DEF["raw"],
        sensorType=UAV_DEF["sensor"],
    )
    dog = UnmannedDogEntity(
        equipmentCode=DOG_DEF["code"],
        name=DOG_DEF["name"],
        data=_position(DOG_DEF["start"]),
        role="uav_guided_ground_dog",
    )
    task = TaskMatrixItem(
        taskLevel="System",
        task_id=SCENARIO_ID,
        goal=("The UAV holds a 280 m altitude and, from its top-down view, recognizes the robot dog's "
              "heading and position (shown by a green arrow / green dot), then plans a segmented, "
              "junction-by-junction path for the dog to the green house; after the dog executes, the UAV "
              "keeps taking photos to re-check, and if a collision occurs it re-plans from the dog's latest "
              "position and heading, until the dog reaches the green house."),
        initial_state=InitialState(
            weather="Clear",
            traffic="",
            coordinate_system="UE_XYZ",
            uav_start_position=dict(UAV_DEF["start"]),
            dog_start_position=dict(DOG_DEF["start"]),
            uav_height_m=UAV_HEIGHT_M,
            target_description="Green house / green roof or green-striped target building",
            visual_markers={
                "dog_heading": "A green arrow indicates the dog's head heading",
                "dog_position": "A green dot indicates the dog's current position",
            },
            workflow=[
                "dispatch_scenario_to_airsim_go2_image",
                "uav_takeoff_or_hold_280m",
                "request_uav_topdown_photo",
                "vlm_plan_dog_junction_waypoints",
                "dispatch_go2_pathplanning",
                "wait_dog_execution_completed_or_collision",
                "repeat_until_dog_arrives_green_house",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="UAV-Guided Robot Dog to the Green House_DEMO",
        collaborationType="High-altitude UAV top-down planning + ground robot dog execution",
        sceneRegion="Outdoor road and green house area",
        equipmentList=EquipmentList(droneEntityList=[drone], unmannedDogEntityList=[dog]),
        taskMatrix=[task],
        max_steps=max_steps,
        task_type=TASK_TYPE,
        taskType=TASK_TYPE,
        scenarioId=SCENARIO_ID,
        evaluator={"name": "uavdog_local"},
    )


def uav_id() -> str:
    return str(UAV_DEF["code"])


def dog_id() -> str:
    return str(DOG_DEF["code"])


def uav_start_position() -> dict[str, float]:
    return dict(UAV_DEF["start"])


def dog_start_position() -> dict[str, float]:
    return dict(DOG_DEF["start"])
