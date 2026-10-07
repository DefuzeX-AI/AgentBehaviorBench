"""Single-dog visual navigation scenario."""

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

TASK_TYPE = "singledog"
SCENARIO_ID = "SINGLEDOG_NAVIGATION_001"

DOG_DEF: dict[str, Any] = {
    "code": "UGV-SINGLEDOG-001",
    "name": "dog1",
    "start": {
        "X": -6360.000000,
        "Y": -21460.000000,
        "Z": 50.0,
        "yaw": 180.0
    },
}

# Open-ended, vision-driven mission (single goal; the VLM decides one action per step from the front view).
SUBTASKS: list[str] = [
    "Starting from the current position, enter the residential community directly ahead. Inside the community, "
    "search for the target: a white building that has pedestrians standing or walking in front of it. Navigate to "
    "and approach that building \u2014 being close in front of it counts as success. Each step, choose a reasonable move "
    "distance (5-50 m: a larger stride when the target/path is far, a smaller stride when approaching) and a "
    "reasonable turn angle (small corrections for minor heading changes, larger turns only when sharply changing "
    "direction, e.g. turning into the community).",
]


def _position(data: dict[str, float]) -> Position:
    return Position(**data)


def build_singledog_scenario(*, max_steps: int = 140) -> ScenarioDefinition:
    """Build the default single-dog scenario."""

    dog = UnmannedDogEntity(
        equipmentCode=DOG_DEF["code"],
        name=DOG_DEF["name"],
        data=_position(DOG_DEF["start"]),
        role="visual_navigation_dog",
    )
    task = TaskMatrixItem(
        taskLevel="Individual",
        task_id=SCENARIO_ID,
        goal="From its front view, the robot dog enters the residential community ahead, finds the white building "
             "with pedestrians in front of it, and approaches that building; getting close to it counts as success.",
        initial_state=InitialState(
            weather="Clear",
            coordinate_system="UE_XYZ",
            dog_start_position=dict(DOG_DEF["start"]),
            target_description="A white building with pedestrians standing/walking in front of it, inside the residential community ahead.",
            subtasks=[{"index": index, "instruction": text} for index, text in enumerate(SUBTASKS, start=1)],
            workflow=[
                "dispatch_scenario",
                "request_dog_front_view",
                "vlm_decide_subtask_action",
                "dispatch_go2_pathfinding_action",
                "repeat_until_current_subtask_finished",
                "advance_to_next_subtask",
                "finish_after_all_subtasks",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="Robot Dog Community Navigation to the White Building_DEMO",
        collaborationType="Single robot dog front-view goal navigation",
        sceneRegion="Residential community with buildings and pedestrians",
        equipmentList=EquipmentList(unmannedDogEntityList=[dog]),
        taskMatrix=[task],
        max_steps=max_steps,
        task_type=TASK_TYPE,
        evaluator={"name": "singledog_local"},
    )


def dog_start_position() -> dict[str, float]:
    return dict(DOG_DEF["start"])


def dog_id() -> str:
    return str(DOG_DEF["code"])
