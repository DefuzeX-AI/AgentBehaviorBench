"""Delivery task scenario definition.

This scenario describes an air-ground delivery workflow:

1. UE provides the start point, delivery target, and global road graph image.
2. A planner finds the nearest vehicle-reachable road point near the target.
3. UE paints the route green on the global image.
4. The UAV follows the green route and checks each segment for traffic jams.
5. Blocked edges are marked unavailable and the route is replanned.
6. The vehicle drives the verified route to the car stop node.
7. The dog starts from the car stop node and finds the target house.

The file is intentionally self-contained under ``examples/deliverytask`` and
uses the same ScenarioDefinition style as ``examples/singledrone_fire``.
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
    UnmannedDogEntity,
)

TASK_TYPE = "deliverytask"
SCENARIO_ID = "DELIVERY_TASK_001"



START_POSITION: dict[str, float] = {          
    "X": -202480.0,
    "Y": 52790.0,
    "Z": 40.0,
}

CAR_START_GEO_POSITION: dict[str, float] = {  
    "X": -202480.0,
    "Y": 50280.0,
    "Z": 40.0,
}

DOG_START_POSITION: dict[str, float] = {      
    "X": -6360.0,
    "Y": -21480.0,
    "Z": 300.0,
}

TRAFFIC_JAM_REFERENCE_POSITION: dict[str, float] = {  
    "lon": 109.94524137,
    "lat": 39.83377686,
    "alt": -174.22848652,
}

# TODO: replace after UE/mission side provides the exact target house position.
# The workflow supports a pending target; run_case can also accept target
# coordinates from CLI and inject them into the scenario.
TARGET_HOUSE_POSITION: dict[str, float] | None = None

DEFAULT_DELIVERY_POINT: dict[str, float] | None = {  
    "X": -2590.0,
    "Y": -21480.0,
    "Z": 60.0,
}

UAV_DEF: dict[str, Any] = {
    "code": "UAV-DELIVERY-001",
    "name": "drone1",
    "start": START_POSITION,
    "sensor": "RGB/TopDown/RoadInspection",
}

CAR_DEF: dict[str, Any] = {
    "code": "CAR-DELIVERY-001",
    "name": "car1",
    "start": CAR_START_GEO_POSITION,
}



DOG_YAW = 0.0

DOG_DEF: dict[str, Any] = {
    "code": "UGV-DELIVERY-001",
    "name": "dog1",
    "start": DOG_START_POSITION,
    "yaw": DOG_YAW,
}

ROAD_GRAPH_CONFIG: dict[str, Any] = {
    "global_map_image": "provided_by_UE",
    "road_graph": "provided_by_UE",
    "green_route_overlay": "provided_by_UE_after_planning",
    "planner": "provided_by_Carla",
    "verified_route": None,
    "blocked_edges": [],
    "car_stop_node": None,
}


def _position(data: dict[str, float]) -> Position:
    return Position(**data)


def _target_house_state(target_position: dict[str, float] | None) -> dict[str, Any]:
    if target_position is None:
        return {
            "status": "pending_target_position",
            "note": "The target house position has not been provided yet; please pass it via build_delivery_task_scenario(target_position=...).",
        }
    return {
        "status": "ready",
        "position": dict(target_position),
    }


def build_delivery_task_scenario(
    *,
    target_position: dict[str, float] | None = TARGET_HOUSE_POSITION,
    delivery_point: dict[str, float] | None = DEFAULT_DELIVERY_POINT,
    max_steps: int = 120,
) -> ScenarioDefinition:
    """Build the default delivery task scenario."""

    uav = DroneEntity(
        equipmentCode=UAV_DEF["code"],
        name=UAV_DEF["name"],
        data=_position(UAV_DEF["start"]),
        raw=0.0,
        sensorType=UAV_DEF["sensor"],
    )

    car = AutoVehicleEntity(
        equipmentCode=CAR_DEF["code"],
        name=CAR_DEF["name"],
        data=_position(CAR_DEF["start"]),
        raw=0.0,
        role="delivery_vehicle",
    )

    dog = UnmannedDogEntity(
        equipmentCode=DOG_DEF["code"],
        name=DOG_DEF["name"],
        data=_position(DOG_DEF["start"]),
        raw=DOG_DEF.get("yaw", 0.0),
        role="last_meter_delivery",
    )

    task = TaskMatrixItem(
        taskLevel="System",
        task_id=SCENARIO_ID,
        goal=(
            "UE provides the start point, delivery point, and global road network image; the navigation "
            "algorithm generates a vehicle-reachable route; the UAV inspects the green route for traffic "
            "congestion and triggers replanning; the vehicle follows verified_route to the stop node; "
            "the robot dog starts from car_stop_node and completes last-mile delivery based on the target "
            "house photo and the front view."
        ),
        initial_state=InitialState(
            weather="Clear",
            traffic="Dynamic",
            start_position=dict(CAR_START_GEO_POSITION),
            uav_start_position=dict(START_POSITION),
            vehicle_start_position=dict(CAR_START_GEO_POSITION),
            dog_start_position=dict(DOG_START_POSITION),
            delivery_point=(
                {"status": "pending_delivery_point", "note": "The delivery point has not been provided yet"}
                if delivery_point is None
                else {"status": "ready", "position": dict(delivery_point)}
            ),
            target_house=_target_house_state(target_position),
            road_graph=ROAD_GRAPH_CONFIG,
            workflow=[
                "plan_start_to_nearest_vehicle_reachable_node",
                "carla_return_route_points",
                "paint_verified_candidate_route_green",
                "uav_inspect_green_route",
                "mark_blocked_edge_and_replan_if_jammed",
                "save_verified_route",
                "vehicle_drive_to_car_stop_node",
                "dog_start_from_car_stop_node",
                "dog_find_target_house_by_photo_and_front_view",
            ],
        ),
    )

    return ScenarioDefinition(
        sceneName="Air-Ground Collaborative Delivery_Congestion Replanning_DEMO",
        collaborationType="UAV Inspection + Unmanned Vehicle Delivery + Robot Dog Last-Mile Delivery",
        sceneRegion="Urban Road Delivery Area",
        equipmentList=EquipmentList(
            droneEntityList=[uav],
            autoVehicleEntityList=[car],
            unmannedDogEntityList=[dog],
        ),
        taskMatrix=[task],
        max_steps=max_steps,
        task_type=TASK_TYPE,
        evaluator={"name": "deliverytask_local"},
    )


def start_position() -> dict[str, float]:
    return dict(START_POSITION)


def traffic_jam_reference_position() -> dict[str, float]:
    return dict(TRAFFIC_JAM_REFERENCE_POSITION)


def target_house_position() -> dict[str, float] | None:
    return dict(TARGET_HOUSE_POSITION) if TARGET_HOUSE_POSITION is not None else None


def entity_names() -> dict[str, str]:
    return {
        "uav": UAV_DEF["name"],
        "car": CAR_DEF["name"],
        "dog": DOG_DEF["name"],
    }
