"""Scenario for the initial 10-UAV photo collection flow."""

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

TASK_TYPE = "multiagentstasks"
SCENARIO_ID = "MULTIAGENTS_UAV_PHOTO_COLLECTION_001"


UAV_DEFS: list[dict[str, Any]] = [
    {
        "code": "UAV-MA-001",
        "name": "drone1",
        "start": {"X": -373690.0, "Y": 350170.15625, "Z": -243127.90625},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-002",
        "name": "drone2",
        "start": {"X": -373690.0, "Y": 330130.15625, "Z": -243127.90625},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-003",
        "name": "drone3",
        "start": {"X": -328160.0, "Y": 384960.0, "Z": -243108.0},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-004",
        "name": "drone4",
        "start": {"X": -328160.0, "Y": 382920.0, "Z": -243108.0},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-005",
        "name": "drone5",
        "start": {"X": -328160.0, "Y": 374470.0, "Z": -243108.0},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-006",
        "name": "drone6",
        "start": {"X": -328160.0, "Y": 355670.0, "Z": -243108.0},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-007",
        "name": "drone7",
        "start": {"X": -338020.0, "Y": 355670.0, "Z": -243108.0},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-008",
        "name": "drone8",
        "start": {"X": -429830.0, "Y": 274320.15625, "Z": -242897.90625},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-009",
        "name": "drone9",
        "start": {"X": -429830.0, "Y": 283630.15625, "Z": -243127.90625},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
    {
        "code": "UAV-MA-010",
        "name": "drone10",
        "start": {"X": -421900.0, "Y": 286120.15625, "Z": -243127.90625},
        "raw": 0.0,
        "sensor": "RGB/TopDown/MultiAgentPhoto",
    },
]


def build_multiagentstasks_scenario(*, max_steps: int = 5) -> ScenarioDefinition:
    """Build a 10-drone scenario used to test scenario/takeoff/photo plumbing."""

    drones = [
        DroneEntity(
            equipmentCode=drone["code"],
            name=drone["name"],
            data=Position(**drone["start"]),
            raw=drone["raw"],
            sensorType=drone["sensor"],
        )
        for drone in UAV_DEFS
    ]
    task = TaskMatrixItem(
        taskLevel="System",
        task_id=SCENARIO_ID,
        goal="Dispatch the position scenario for the 10 UAVs; after takeoff, request each UAV to capture a top-down view and upload it back for saving.",
        initial_state=InitialState(
            weather="Clear",
            uav_count=len(UAV_DEFS),
            uav_start_positions={drone["code"]: dict(drone["start"]) for drone in UAV_DEFS},
            workflow=[
                "broadcast_scenario_to_airsim_and_image",
                "dispatch_takeoff_for_10_uavs",
                "request_topdown_photo_for_10_uavs",
                "wait_until_10_uploaded_images_saved",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="Ten-UAV Photo Capture Integration Test_DEMO",
        collaborationType="Multi-UAV photo capture collection",
        sceneRegion="Multi-UAV initial test area",
        equipmentList=EquipmentList(droneEntityList=drones),
        taskMatrix=[task],
        max_steps=max_steps,
        task_type=TASK_TYPE,
        evaluator={"name": "multiagentstasks_local"},
    )


def uav_ids() -> list[str]:
    return [str(drone["code"]) for drone in UAV_DEFS]


def uav_start_positions() -> dict[str, dict[str, float]]:
    return {str(drone["code"]): dict(drone["start"]) for drone in UAV_DEFS}
