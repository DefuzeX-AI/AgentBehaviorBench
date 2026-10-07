"""Scenario for spawning five unmanned dogs only."""

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

SCENARIO_ID = "MULTIAGENTS_DOG_GENERATION_001"


DOG_DEFS: list[dict[str, Any]] = [
    {
        "code": "UGV-MA-001",
        "name": "dog1",
        "start": {"X": -373690.0, "Y": 350170.15625, "Z": -243127.90625},
        "role": "multi_dog_spawn_test",
    },
    {
        "code": "UGV-MA-002",
        "name": "dog2",
        "start": {"X": -373650.0, "Y": 350170.15625, "Z": -243127.90625},
        "role": "multi_dog_spawn_test",
    },
    {
        "code": "UGV-MA-003",
        "name": "dog3",
        "start": {"X": -373610.0, "Y": 350170.15625, "Z": -243127.90625},
        "role": "multi_dog_spawn_test",
    },
    {
        "code": "UGV-MA-004",
        "name": "dog4",
        "start": {"X": -373690.0, "Y": 350130.15625, "Z": -243127.90625},
        "role": "multi_dog_spawn_test",
    },
    {
        "code": "UGV-MA-005",
        "name": "dog5",
        "start": {"X": -373650.0, "Y": 350130.15625, "Z": -243127.90625},
        "role": "multi_dog_spawn_test",
    },
]


def build_multiagentstasks_dog_scenario(*, max_steps: int = 5) -> ScenarioDefinition:
    """Build a five-dog scenario for entity spawn integration tests."""

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
        goal="\u4e0b\u53d1 5 \u53ea\u673a\u5668\u72d7\u7684\u5b9e\u4f53\u751f\u6210\u60f3\u5b9a\uff0c\u7528\u4e8e\u9a8c\u8bc1 UE/Go2 \u4fa7\u591a\u72d7\u751f\u6210\u3002",
        initial_state=InitialState(
            weather="Clear",
            dog_count=len(DOG_DEFS),
            dog_start_positions={dog["code"]: dict(dog["start"]) for dog in DOG_DEFS},
            workflow=[
                "broadcast_scenario_to_all_engines",
                "verify_5_dogs_spawned",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="\u4e94\u673a\u5668\u72d7\u751f\u6210\u8054\u8c03_DEMO",
        collaborationType="\u591a\u673a\u5668\u72d7\u5b9e\u4f53\u751f\u6210",
        sceneRegion="\u591a\u667a\u80fd\u4f53\u521d\u59cb\u6d4b\u8bd5\u533a\u57df",
        equipmentList=EquipmentList(unmannedDogEntityList=dogs),
        taskMatrix=[task],
        max_steps=max_steps,
        commandType="resetScenario",
        task_type=TASK_TYPE,
        taskType=TASK_TYPE,
        scenarioId=SCENARIO_ID,
        evaluator={"name": "multiagentstasks_dog_local"},
    )


def dog_ids() -> list[str]:
    return [str(dog["code"]) for dog in DOG_DEFS]


def dog_start_positions() -> dict[str, dict[str, float]]:
    return {str(dog["code"]): dict(dog["start"]) for dog in DOG_DEFS}
