"""Air-ground cooperative firefighting scenario builder.

Written directly as Python data using :class:`ScenarioDefinition` \u2014 the resulting object can
be fed to :func:`app.modules.envs.envs.fire_rescue_env.make_env` and can also be pushed to
LJ-ENGINE over WebSocket after ``model_dump()``.

The fire-spot positions are carried by ``initial_state.fire_spots`` and are used only inside
the env; the Pydantic submodels of ``ScenarioDefinition`` all enable ``extra="allow"``, so
these extra fields round-trip losslessly.
"""

from __future__ import annotations

from typing import Any

from app.modules.envs.scenario_models import (
    AutoVehicleEntity,
    DroneEntity,
    EquipmentList,
    InitialState,
    Position,
    ScenarioDefinition,
    TaskMatrixItem,
)


UAV_DEF: dict[str, Any] = {
    "code": "DRONE-001",
    "name": "drone1",
    "start": (0.0, 0.0, 80.0),
    "sensor": "EO/IR/Thermal",
}

UGV_FLEET: list[dict[str, Any]] = [
    {"code": "UGV-001", "name": "ugv1", "start": (-20.0, 0.0, 0.0)},
    {"code": "UGV-002", "name": "ugv2", "start": (20.0, 0.0, 0.0)},
]

FIRE_SPOTS: list[dict[str, Any]] = [
    {"id": "fire-01", "x": 90.0, "y": 60.0, "intensity": 1.0},
    {"id": "fire-02", "x": 120.0, "y": -30.0, "intensity": 1.2},
    {"id": "fire-03", "x": -70.0, "y": 50.0, "intensity": 0.8},
]

# UAV default patrol waypoints (clockwise loop). The policy follows this sequence by default,
# but the user may override it.
PATROL_WAYPOINTS: list[tuple[float, float, float]] = [
    (80.0, 0.0, 80.0),
    (60.0, 60.0, 80.0),
    (0.0, 80.0, 80.0),
    (-70.0, 60.0, 80.0),
    (-80.0, 0.0, 80.0),
    (-60.0, -50.0, 80.0),
    (0.0, -80.0, 80.0),
    (80.0, -30.0, 80.0),
]


def build_fire_rescue_scenario(max_steps: int = 80) -> ScenarioDefinition:
    """Urban fire alarm emergency: 1 UAV on patrol + 2 UGVs firefighting."""

    uav = DroneEntity(
        equipmentCode=UAV_DEF["code"],
        name=UAV_DEF["name"],
        data=Position(X=UAV_DEF["start"][0], Y=UAV_DEF["start"][1], Z=UAV_DEF["start"][2]),
        raw=0.0,
        sensorType=UAV_DEF["sensor"],
    )

    ugvs = [
        AutoVehicleEntity(
            equipmentCode=u["code"],
            name=u["name"],
            data=Position(X=u["start"][0], Y=u["start"][1], Z=u["start"][2]),
            raw=0.0,
        )
        for u in UGV_FLEET
    ]

    task_matrix = [
        TaskMatrixItem(
            taskLevel="System",
            task_id="FIRE_RESCUE_001",
            goal="The UAV patrols and locks onto the fire spots, and the UGVs cooperatively approach and extinguish all fire spots",
            initial_state=InitialState(
                weather="Dry",
                traffic="Sparse",
                # extra="allow" passes through to ScenarioSpec.raw -> read by MockFireRescueBridge
                fire_spots=FIRE_SPOTS,
                patrol_waypoints=[list(wp) for wp in PATROL_WAYPOINTS],
            ),
        ),
    ]

    return ScenarioDefinition(
        sceneName="Urban Fire Alarm Emergency_Air-Ground Cooperation_DEMO",
        collaborationType="Air-ground cooperative firefighting",
        sceneRegion="Urban outskirts",
        equipmentList=EquipmentList(
            droneEntityList=[uav],
            autoVehicleEntityList=ugvs,
        ),
        taskMatrix=task_matrix,
        # extra fields pass through -> used by the adapter in ScenarioSpec.termination/task_type
        max_steps=max_steps,
        task_type="fire_rescue",
        evaluator={"name": "fire_rescue_v1"},
    )


def uav_name() -> str:
    return UAV_DEF["name"]


def ugv_names() -> list[str]:
    return [u["name"] for u in UGV_FLEET]


def fire_spot_table() -> list[dict[str, Any]]:
    return list(FIRE_SPOTS)


def patrol_waypoints() -> list[dict[str, float]]:
    return [{"x": wp[0], "y": wp[1], "z": wp[2]} for wp in PATROL_WAYPOINTS]
