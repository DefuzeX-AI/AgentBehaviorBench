"""Scenario for spawning three unmanned dogs with UE XYZ coordinates."""

from __future__ import annotations

from typing import Any

from app.modules.envs.scenario_models import (
    EquipmentList,
    InitialState,
    Position,
    ScenarioDefinition,
    TaskMatrixItem,
    UnmannedDogEntity,
)

from examples.multiagentstasks.scenario import TASK_TYPE

SCENARIO_ID = "MULTIAGENTS_XYZ_DOGS_GENERATION_001"

DOG_XYZ_DEFS: list[dict[str, Any]] = [
    {
        "code": "UGV-MA-101",
        "name": "dog1",
        "start": {"X": -475360.0, "Y": 225030.0, "Z": -242728.0},
        "role": "xyz_spawn_test_dog",
    },
    {
        "code": "UGV-MA-102",
        "name": "dog2",
        "start": {"X": -473390.0, "Y": 225030.0, "Z": -242728.0},
        "role": "xyz_spawn_test_dog",
    },
    {
        "code": "UGV-MA-103",
        "name": "dog3",
        "start": {"X": -470830.0, "Y": 225000.0, "Z": -242728.0},
        "role": "xyz_spawn_test_dog",
    },
]


def build_multiagentstasks_xyz_dogs_scenario(*, max_steps: int = 5) -> ScenarioDefinition:
    """Build a three-dog scenario using UE XYZ coordinates."""

    dogs = [
        UnmannedDogEntity(
            equipmentCode=dog["code"],
            name=dog["name"],
            data=Position(**dog["start"]),
            role=dog["role"],
        )
        for dog in DOG_XYZ_DEFS
    ]
    task = TaskMatrixItem(
        taskLevel="System",
        task_id=SCENARIO_ID,
        goal="\u4e0b\u53d1 3 \u53ea\u673a\u5668\u72d7\u7684 UE XYZ \u5750\u6807\u60f3\u5b9a\uff0c\u7528\u4e8e\u9a8c\u8bc1 UE/Go2 \u4fa7\u6309 XYZ \u751f\u6210\u591a\u72d7\u5b9e\u4f53\u3002",
        initial_state=InitialState(
            weather="Clear",
            dog_count=len(DOG_XYZ_DEFS),
            coordinate_system="UE_XYZ",
            dog_start_positions={dog["code"]: dict(dog["start"]) for dog in DOG_XYZ_DEFS},
            workflow=[
                "broadcast_scenario_to_all_engines",
                "verify_3_xyz_dogs_spawned",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="\u4e09\u673a\u5668\u72d7XYZ\u751f\u6210\u8054\u8c03_DEMO",
        collaborationType="\u591a\u673a\u5668\u72d7\u5b9e\u4f53\u751f\u6210",
        sceneRegion="\u591a\u72d7 XYZ \u751f\u6210\u6d4b\u8bd5\u533a\u57df",
        equipmentList=EquipmentList(unmannedDogEntityList=dogs),
        taskMatrix=[task],
        max_steps=max_steps,
        commandType="resetScenario",
        task_type=TASK_TYPE,
        taskType=TASK_TYPE,
        scenarioId=SCENARIO_ID,
        evaluator={"name": "multiagentstasks_xyz_dogs_local"},
    )


def dog_ids() -> list[str]:
    return [str(dog["code"]) for dog in DOG_XYZ_DEFS]


def dog_start_positions() -> dict[str, dict[str, float]]:
    return {str(dog["code"]): dict(dog["start"]) for dog in DOG_XYZ_DEFS}
