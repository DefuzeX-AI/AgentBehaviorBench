"""Scenario for spawning UAVs, cars, and unmanned dogs in one payload."""

from __future__ import annotations

from app.modules.envs.scenario_models import (
    AutoVehicleEntity,
    DroneEntity,
    EquipmentList,
    InitialState,
    Position,
    ScenarioDefinition,
    TaskMatrixItem,
    UnmannedDogEntity,
)

from examples.multiagentstasks.scenario import TASK_TYPE, UAV_DEFS
from examples.multiagentstasks.scenario2 import DOG_DEFS
from examples.multiagentstasks.scenario4 import CAR_XYZ_DEFS

SCENARIO_ID = "MULTIAGENTS_ALL_ENTITIES_GENERATION_001"


def build_multiagentstasks_all_entities_scenario(*, max_steps: int = 10) -> ScenarioDefinition:
    """Build one scenario containing all current UAV, car, and dog entities."""

    drones = [
        DroneEntity(
            equipmentCode=uav["code"],
            name=uav["name"],
            data=Position(**uav["start"]),
            raw=uav["raw"],
            sensorType=uav["sensor"],
        )
        for uav in UAV_DEFS
    ]
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
    dogs = [
        UnmannedDogEntity(
            equipmentCode=dog["code"],
            name=dog["name"],
            data=Position(**dog["start"]),
            role=dog["role"],
        )
        for dog in DOG_DEFS
    ]
    task = TaskMatrixItem(
        taskLevel="System",
        task_id=SCENARIO_ID,
        goal="\u4e00\u6b21\u6027\u4e0b\u53d1 10 \u67b6\u65e0\u4eba\u673a\u30013 \u8f86 UE XYZ \u65e0\u4eba\u8f66\u548c 5 \u53ea UE XYZ \u673a\u5668\u72d7\uff0c\u7528\u4e8e\u9a8c\u8bc1\u591a\u7c7b\u578b\u5b9e\u4f53\u540c\u65f6\u751f\u6210\u3002",
        initial_state=InitialState(
            weather="Clear",
            traffic="Dynamic",
            coordinate_system="UE_XYZ",
            uav_count=len(UAV_DEFS),
            car_count=len(CAR_XYZ_DEFS),
            dog_count=len(DOG_DEFS),
            uav_start_positions={uav["code"]: dict(uav["start"]) for uav in UAV_DEFS},
            car_start_positions={car["code"]: dict(car["start"]) for car in CAR_XYZ_DEFS},
            dog_start_positions={dog["code"]: dict(dog["start"]) for dog in DOG_DEFS},
            workflow=[
                "broadcast_scenario_to_all_engines",
                "verify_10_uavs_spawned",
                "verify_3_cars_spawned",
                "verify_5_dogs_spawned",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="\u591a\u65e0\u4eba\u673a\u591a\u8f66\u591a\u673a\u5668\u72d7\u751f\u6210\u8054\u8c03_DEMO",
        collaborationType="\u591a\u65e0\u4eba\u673a + \u591a\u65e0\u4eba\u8f66 + \u591a\u673a\u5668\u72d7\u5b9e\u4f53\u751f\u6210",
        sceneRegion="\u591a\u667a\u80fd\u4f53\u7efc\u5408\u6d4b\u8bd5\u533a\u57df",
        equipmentList=EquipmentList(
            droneEntityList=drones,
            autoVehicleEntityList=cars,
            unmannedDogEntityList=dogs,
        ),
        taskMatrix=[task],
        max_steps=max_steps,
        commandType="resetScenario",
        task_type=TASK_TYPE,
        taskType=TASK_TYPE,
        scenarioId=SCENARIO_ID,
        evaluator={"name": "multiagentstasks_all_entities_local"},
    )
