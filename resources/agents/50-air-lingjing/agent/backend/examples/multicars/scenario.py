"""Scenario definition for multi-car task allocation.

The Carla side is expected to receive this scenario, compute every car's
distance to every task point, and return an ``allDistancesReport`` event.
"""

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

TASK_TYPE = "multicars"
SCENARIO_ID = "MULTICARS_TASK_ALLOCATION_001"

CAR_DEFS: list[dict[str, Any]] = [
    {
        "code": "CAR-001",
        "name": "car1",
        "start": {"lat": 39.83677715, "lon": 109.94554248, "alt": 0.0},
    },
    {
        "code": "CAR-002",
        "name": "car2",
        "start": {"lat": 39.82680549, "lon": 109.94491416, "alt": 0.0},
    },
    {
        "code": "CAR-003",
        "name": "car3",
        "start": {"lat": 39.82654341, "lon": 109.95030457, "alt": 0.0},
    },
]

# Placeholder task points. Replace these with the actual 10 target coordinates
# once the field team provides them, or pass --task-points-file to run_case.py.
TASK_POINTS: list[dict[str, Any]] = [
    {"id": "1", "lat": 39.82897557, "lon": 109.94390923, "alt": 0.0},
    {"id": "2", "lat": 39.82901655, "lon": 109.94475611, "alt": 0.0},
    {"id": "3", "lat": 39.82418630, "lon": 109.94317298, "alt": 0.0},
    {"id": "4", "lat": 39.82417560, "lon": 109.94506879, "alt": 0.0},
    {"id": "5", "lat": 39.82428639, "lon": 109.95044540, "alt": 0.0},
    {"id": "6", "lat": 39.82920454, "lon": 109.94956414, "alt": 0.0},
    {"id": "7", "lat": 39.83300698, "lon": 109.95702254, "alt": 0.0},
    {"id": "8", "lat": 39.83354666, "lon": 109.94426153, "alt": 0.0},
    {"id": "9", "lat": 39.83348227, "lon": 109.94510975, "alt": 0.0},
    {"id": "10", "lat": 39.84175286, "lon": 109.94632677, "alt": 0.0},
]


def build_multicars_scenario(
    *,
    task_points: list[dict[str, Any]] | None = None,
    max_steps: int = 30,
) -> ScenarioDefinition:
    """Build the default multi-car allocation scenario."""

    points = normalize_task_points(task_points or TASK_POINTS)
    cars = [
        AutoVehicleEntity(
            equipmentCode=car["code"],
            name=car["name"],
            data=Position(**car["start"]),
            raw=0.0,
            role="delivery_vehicle",
        )
        for car in CAR_DEFS
    ]

    task = TaskMatrixItem(
        taskLevel="System",
        task_id=SCENARIO_ID,
        goal=(
            "Three unmanned vehicles start from different spawn points; Carla returns a distance "
            "matrix from each vehicle to the 10 task points; the LLM assigns task points based on "
            "the distance matrix and generates each vehicle's task visiting order."
        ),
        initial_state=InitialState(
            weather="Clear",
            traffic="Dynamic",
            car_start_positions={car["code"]: dict(car["start"]) for car in CAR_DEFS},
            task_points=points,
            expected_engine_report={
                "commandType": "allDistancesReport",
                "data": [
                    {
                        "autocarId": car["code"],
                        "distances": {point["id"]: "distance_m" for point in points},
                    }
                    for car in CAR_DEFS
                ],
            },
            workflow=[
                "broadcast_scenario_to_all_engines",
                "wait_allDistancesReport",
                "llm_assign_task_points_to_cars",
                "dispatch_multi_car_task_routes",
            ],
        ),
    )

    return ScenarioDefinition(
        sceneName="Multi Unmanned Vehicle Task Point Allocation_DEMO",
        collaborationType="Multi Unmanned Vehicle Task Allocation",
        sceneRegion="Urban Road Multi-Point Delivery Area",
        equipmentList=EquipmentList(autoVehicleEntityList=cars),
        taskMatrix=[task],
        max_steps=max_steps,
        task_type=TASK_TYPE,
        evaluator={"name": "multicars_local"},
    )


def normalize_task_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize point IDs and lon/lat/alt values for scenario and actions."""

    if len(points) != 10:
        raise ValueError(f"multicars currently requires exactly 10 task points, received {len(points)}")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, point in enumerate(points, start=1):
        if not isinstance(point, dict):
            raise ValueError(f"Task point {index} must be a JSON object")
        point_id = str(point.get("id") or point.get("taskPointId") or index)
        if point_id in seen:
            raise ValueError(f"Duplicate task point id: {point_id}")
        seen.add(point_id)
        lon = point.get("lon")
        lat = point.get("lat")
        if lon is None or lat is None:
            raise ValueError(f"Task point {point_id} must contain lon/lat")
        normalized.append(
            {
                "id": point_id,
                "lon": float(lon),
                "lat": float(lat),
                "alt": float(point.get("alt") or 0.0),
            }
        )
    return normalized


def car_ids() -> list[str]:
    return [str(car["code"]) for car in CAR_DEFS]


def default_task_points() -> list[dict[str, Any]]:
    return [dict(point) for point in TASK_POINTS]
