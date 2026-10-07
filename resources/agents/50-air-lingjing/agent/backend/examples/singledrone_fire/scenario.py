"""Single-UAV fire visual search-and-rescue scenario (aligned with single UAV fire validation json.json).

Flow: UAV takes off -> setDestination flies first to the fire **range area** -> within the area
capture a top-down view (front view optional) and search for the fire source based on the **fire description**
-> use pixel offset + UAV altitude to compute the fire source world coordinates (cm), fly closer to the fire source
-> **when XY is close enough the engine reports a successful fire-extinguishing adjudication**.

Flight direction is no longer judged from a global map; the fire ground truth goalFirePosition (including
range/description) goes into the engine (rendering + adjudication) and is hidden from the agent's observation.
"""

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

SCENARIO_ID = "SINGLE_DRONE_FIRE_001"
UAV_NAME = "drone1"

# Coordinate unit = centimeters (cm).
UAV_DEF: dict[str, Any] = {
    "code": "UAV-FIRE-001",
    "name": UAV_NAME,
    "start": {"X": 61080.0, "Y": 6730.0, "Z": 40.0},
    "sensor": "RGB/TopDown/VLM",
}

# Fire ground truth (used by engine rendering + adjudication; hidden from the agent). description is the clue for the vision model to find the fire; range is the disclosable search area boundary.
FIRE_DEF: dict[str, Any] = {
    "fireId": "fire-01",
    "X": -231330.0, "Y": 34660.0, "Z": 3390.0,
    "description": "Within the area there is a white gymnasium building with thick smoke and flames on top",
    "range": [
        {"X": -198310.0, "Y": 49890.0, "Z": 40.0},
        {"X": -258070.0, "Y": 37230.0, "Z": 40.0},
        {"X": -258070.0, "Y": 2700.0, "Z": 40.0},
        {"X": -198310.0, "Y": 2700.0, "Z": 40.0},
    ],
}

UAV_TAKEOFF_HEIGHT_M = 100.0   # Takeoff climb (the mile of takeoff, meters)
CAM_FOV_DEG = 90.0             # Down-facing camera field of view (estimate ground footprint -> convert pixel offset to cm)


def _bbox(corners: list[dict[str, float]]) -> tuple[float, float, float, float]:
    xs = [c["X"] for c in corners]; ys = [c["Y"] for c in corners]
    return min(xs), max(xs), min(ys), max(ys)


def range_center() -> dict[str, float]:
    """Center of the range bounding box (the UAV flies here first after takeoff, then starts searching); Z uses the range plane Z."""
    x0, x1, y0, y1 = _bbox(FIRE_DEF["range"])
    return {"X": round((x0 + x1) / 2, 1), "Y": round((y0 + y1) / 2, 1),
            "Z": float(FIRE_DEF["range"][0]["Z"])}


def range_bbox() -> dict[str, float]:
    x0, x1, y0, y1 = _bbox(FIRE_DEF["range"])
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1, "Z": float(FIRE_DEF["range"][0]["Z"])}


def build_single_drone_fire_scenario(max_steps: int = 60) -> ScenarioDefinition:
    """Single-UAV fire visual search-and-rescue scenario."""

    uav = DroneEntity(
        equipmentCode=UAV_DEF["code"], name=UAV_DEF["name"],
        data=Position(**UAV_DEF["start"]), raw=0.0, sensorType=UAV_DEF["sensor"],
    )
    task = TaskMatrixItem(
        taskLevel="Individual",
        task_id=SCENARIO_ID,
        goal=("UAV takes off -> setDestination flies to the fire range area -> within the area capture a top-down view "
              "(front view optional) and search for the fire source based on the fire description -> "
              "use pixel offset + altitude to compute the fire source coordinates and fly closer -> when XY is close enough "
              "the engine adjudicates successful fire extinguishing. Does not rely on a global map for direction."),
        initial_state=InitialState(
            weather="Dry", traffic="None", coordinate_system="UE_XYZ_cm",
            uav_id=UAV_DEF["code"], uav_start_position=dict(UAV_DEF["start"]),
            uav_takeoff_height_m=UAV_TAKEOFF_HEIGHT_M,
            goalFirePosition=[dict(FIRE_DEF)],            # Engine ground truth (includes range/description; the agent cannot see the coordinates)
            fire_count=1,
            target_description=FIRE_DEF["description"],   # Disclosed item: descriptive clue for finding the fire
            search_range=[dict(c) for c in FIRE_DEF["range"]],  # Disclosed item: search area boundary
            workflow=[
                "dispatch_scenario_to_airsim_and_image",
                "uav_takeoff -> setDestination_to_range_center",
                "topdown(+front)_photo -> vlm_find_fire_by_description -> move_toward_fire(px_offset+altitude)",
                "engine_extinguish_adjudication_when_xy_close",
            ],
        ),
    )
    return ScenarioDefinition(
        sceneName="Single-UAV Fire Visual Localization_DEMO",
        collaborationType="Single-agent visual localization",
        sceneRegion="Open flat test area",
        equipmentList=EquipmentList(droneEntityList=[uav]),
        taskMatrix=[task],
        max_steps=max_steps,
        commandType="resetScenario",
        scenarioId=SCENARIO_ID,
        task_type="singledrone_fire",
        taskType="singledrone_fire",
        evaluator={"name": "singledrone_fire_local"},
    )


# --------------------------------------------------------------------------- #
# Accessors -- disclosed items (may enter observation) vs hidden ground truth (harness only).
# --------------------------------------------------------------------------- #
def uav_name() -> str:
    return UAV_NAME


def uav_id() -> str:
    return str(UAV_DEF["code"])


def uav_start() -> dict[str, float]:
    return dict(UAV_DEF["start"])


def fire_id() -> str:                                   # hidden
    return str(FIRE_DEF["fireId"])


def fire_description() -> str:                          # disclosed item (fire-finding clue)
    return str(FIRE_DEF["description"])


def fire_range() -> list[dict[str, float]]:             # disclosed item (search area)
    return [dict(c) for c in FIRE_DEF["range"]]


def fire_coord() -> dict[str, float]:                   # hidden ground truth (for metrics/validation)
    return {"X": float(FIRE_DEF["X"]), "Y": float(FIRE_DEF["Y"]), "Z": float(FIRE_DEF["Z"])}


# --------------------------------------------------------------------------- #
# Backward-compatibility shims (the old local-simulation env/engines/evaluator still import these two; the new real-hardware flow does not use them).
# --------------------------------------------------------------------------- #
def fire_spots() -> list[dict[str, Any]]:
    f = FIRE_DEF
    return [{"id": f["fireId"], "x": f["X"], "y": f["Y"], "z": f["Z"], "intensity": 1.0}]


def image_config() -> dict[str, Any]:
    return {
        "topdown_width": 1920, "topdown_height": 1080,
        "topdown_ground_length_m": 400.0, "topdown_ground_width_m": 300.0,
        "topdown_meter_per_pixel_x": 1.0, "topdown_meter_per_pixel_y": 1.0,
        "topdown_side_length_m": 400.0, "localization_threshold_m": 8.0,
    }
