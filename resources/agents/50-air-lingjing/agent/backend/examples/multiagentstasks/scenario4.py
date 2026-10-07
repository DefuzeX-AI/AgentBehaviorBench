"""Scenario for spawning three cars with UE XYZ coordinates."""

from __future__ import annotations

from typing import Any

from app.modules.envs.scenario_models import (
    AutoVehicleEntity,
    EquipmentList,
    InitialState,
    Position,
    ScenarioDefinition,
    TaskMatrixItem,
)

from examples.multiagentstasks.scenario import TASK_TYPE

SCENARIO_ID = "MULTIAGENTS_XYZ_CARS_GENERATION_001"


def _xyz(x: float, y: float, z: float) -> dict[str, float]:
    """Carry UE coordinates using the agreed upper-case X/Y/Z keys."""

    return {"X": x, "Y": y, "Z": z}


CAR_XYZ_DEFS: list[dict[str, Any]] = [
    {
        "code": "CAR-MA-001",
        "name": "car1",
        "start": _xyz(-513132.327357, 43946.801517, -242361.903785),
        "role": "xyz_spawn_test_vehicle",
    },
    {
        "code": "CAR-MA-002",
        "name": "car2",
        "start": _xyz(-477150.0, 176220.0, -242418.0),
        "role": "xyz_spawn_test_vehicle",
    },
    {
        "code": "CAR-MA-003",
        "name": "car3",
        "start": _xyz(-498890.0, 69480.0, -242298.0),
        "role": "xyz_spawn_test_vehicle",
    },
]


def build_multiagentstasks_xyz_cars_scenario(*, max_steps: int = 5) -> ScenarioDefinition:
    """Build a three-car scenario using UE XYZ coordinates."""

    cars = [
        AutoVehicleEntity(
            equipmentCode=car["code"],
            name=car["name"],
            data=Position(**car["start"]),
            raw=0.0,
            role=car["role"],
        )
        for car in CAR_XYZ_DEFS
    ]
    task = TaskMatrixItem(
        taskLevel="System",
        task_id=SCENARIO_ID,
        goal="\u4e0b\u53d1 3 \u8f86\u65e0\u4eba\u8f66\u7684 UE XYZ \u5750\u6807\u60f3\u5b9a\uff0c\u7528\u4e8e\u9a8c\u8bc1 Carla/UE \u4fa7\u6309 XYZ \u751f\u6210\u591a\u8f66\u5b9e\u4f53\u3002",
        initial_state=InitialState(
            weather="Clear",
            traffic="Static",
            car_count=len(CAR_XYZ_DEFS),
            coordinate_system="UE_XYZ",
            car_start_positions={car["code"]: dict(car["start"]) for car in CAR_XYZ_DEFS},
            workflow=[
                "broadcast_scenario_to_all_engines",
                "verify_3_xyz_cars_spawned",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="\u4e09\u65e0\u4eba\u8f66XYZ\u751f\u6210\u8054\u8c03_DEMO",
        collaborationType="\u591a\u65e0\u4eba\u8f66\u5b9e\u4f53\u751f\u6210",
        sceneRegion="\u591a\u8f66 XYZ \u751f\u6210\u6d4b\u8bd5\u533a\u57df",
        equipmentList=EquipmentList(autoVehicleEntityList=cars),
        taskMatrix=[task],
        max_steps=max_steps,
        commandType="resetScenario",
        task_type=TASK_TYPE,
        taskType=TASK_TYPE,
        scenarioId=SCENARIO_ID,
        evaluator={"name": "multiagentstasks_xyz_cars_local"},
    )


def car_ids() -> list[str]:
    return [str(car["code"]) for car in CAR_XYZ_DEFS]


def car_start_positions() -> dict[str, dict[str, float]]:
    return {str(car["code"]): dict(car["start"]) for car in CAR_XYZ_DEFS}
