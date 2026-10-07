"""Multi-UAV delivery scenario builder.

Written directly as Python code using the ``ScenarioDefinition`` class \u2014 the resulting object
can be fed directly to :func:`examples.full_case.multi_drone_env.make_env` and can also be
serialized via ``.to_engine_payload()`` and pushed to LJ-ENGINE over WebSocket.
"""

from __future__ import annotations

from typing import Any

from app.modules.envs.scenario_models import (
    DroneEntity,
    EquipmentList,
    GoalPosition,
    InitialState,
    Position,
    ScenarioDefinition,
    TaskMatrixItem,
)


DELIVERY_FLEET: list[dict[str, Any]] = [
    {
        "code": "DRONE-001",
        "name": "drone1",
        "start": (0.0, 0.0, 60.0),
        "delivery": (120.0, 20.0, 60.0),
        "parcel": "medical_kit",
    },
    {
        "code": "DRONE-002",
        "name": "drone2",
        "start": (0.0, 30.0, 60.0),
        "delivery": (80.0, 80.0, 60.0),
        "parcel": "food_supply",
    },
    {
        "code": "DRONE-003",
        "name": "drone3",
        "start": (0.0, -30.0, 60.0),
        "delivery": (150.0, -40.0, 60.0),
        "parcel": "drone_battery",
    },
]


def build_delivery_scenario() -> ScenarioDefinition:
    """Assemble the "urban multi-UAV delivery" scenario: 3 UAVs each flying to one delivery point."""

    drones = [
        DroneEntity(
            equipmentCode=d["code"],
            name=d["name"],
            data=Position(X=d["start"][0], Y=d["start"][1], Z=d["start"][2]),
            raw=0.0,
            sensorType="EO/IR",
        )
        for d in DELIVERY_FLEET
    ]

    task_matrix = [
        TaskMatrixItem(
            taskLevel="Group",
            task_id=f"DELIVERY_{d['code']}",
            goal=f"{d['name']} carries {d['parcel']}, approaches the delivery point, and completes the drop-off",
            initial_state=InitialState(
                weather="Clear",
                traffic="Light",
                goalPosition=GoalPosition(
                    lon=d["delivery"][0], lat=d["delivery"][1], alt=d["delivery"][2]
                ),
            ),
        )
        for d in DELIVERY_FLEET
    ]

    return ScenarioDefinition(
        sceneName="Urban Multi-UAV Delivery_DEMO",
        collaborationType="Multi-UAV cooperative delivery",
        sceneRegion="Urban open area",
        equipmentList=EquipmentList(droneEntityList=drones),
        taskMatrix=task_matrix,
    )


def delivery_targets() -> dict[str, dict[str, float]]:
    """The "delivery target point" mapping shared by env / evaluator / mock engine."""

    return {
        d["name"]: {
            "x": float(d["delivery"][0]),
            "y": float(d["delivery"][1]),
            "z": float(d["delivery"][2]),
        }
        for d in DELIVERY_FLEET
    }


def delivery_parcels() -> dict[str, str]:
    return {d["name"]: d["parcel"] for d in DELIVERY_FLEET}


def fleet_names() -> list[str]:
    return [d["name"] for d in DELIVERY_FLEET]
