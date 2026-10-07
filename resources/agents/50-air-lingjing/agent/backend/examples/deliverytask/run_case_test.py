"""Small deliverytask UAV endpoint flight test.

This test only validates AirSim UAV takeoff at the endpoint:
1. Dispatch the deliverytask scenario to UE/image and AirSim.
2. Spawn the UAV at the endpoint UE coordinate.
3. Take off to 280m and hover/wait.

It intentionally skips Carla route planning, image upload/LLM analysis, vehicle
movement, and Go2 control.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.modules.envs.scenario import ScenarioSpec
from app.modules.envs.task_id import make_task_id
from examples._log_util import log_cmd, setup_console_logging
from examples.deliverytask.run_case import (
    HttpClient,
    ensure_sessions,
    safe_component,
    send_uav_takeoff,
)
from examples.deliverytask.scenario import UAV_DEF, build_delivery_task_scenario

CASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = CASE_DIR / "results"

# Default UE endpoint from the latest Carla route samples used in this task.
DEFAULT_ENDPOINT = {
    "x": -478410.53,
    "y": 225335.8,
}
DEFAULT_ENDPOINT_Z = -242578.446706


def build_test_scenario_payload(*, task_id: str, endpoint: dict[str, float]) -> dict[str, Any]:
    spec = ScenarioSpec.from_definition(build_delivery_task_scenario())
    spec.task_id = task_id
    payload = spec.to_engine_payload()
    payload["commandType"] = "resetScenario"
    drone_list = payload.get("equipmentList", {}).get("droneEntityList") or []
    if drone_list:
        drone_list[0]["data"] = {"X": endpoint["x"], "Y": endpoint["y"], "Z": endpoint["z"]}
    initial_state = payload.get("taskMatrix", [{}])[0].setdefault("initial_state", {})
    initial_state["test_mode"] = "uav_takeoff_at_endpoint_only"
    initial_state["uav_start_position"] = {"X": endpoint["x"], "Y": endpoint["y"], "Z": endpoint["z"]}
    initial_state["uav_endpoint_ue_xyz"] = dict(endpoint)
    return payload


def dispatch_test_scenario(
    client: HttpClient,
    *,
    task_id: str,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    responses: dict[str, Any] = {}
    for name, path in {
        "airsim": "/sim/engine/airsim/scenario",
        "image": "/sim/engine/image/scenario",
    }.items():
        log_cmd(f"LJ-ENGINE_{name}", "\u4e0b\u53d1\u573a\u666f scenario (resetScenario)")
        responses[name] = client.post_json(
            path,
            {
                "taskId": task_id,
                "scenario": scenario,
                "requireAck": False,
                "timeoutSec": 0,
            },
            timeout=10.0,
        )
    return responses


def run_endpoint_test(
    *,
    backend_url: str,
    task_id: str,
    endpoint_x: float,
    endpoint_y: float,
    endpoint_z: float,
    takeoff_height_m: float,
    takeoff_speed: float,
    dry_run: bool,
    skip_session_check: bool,
) -> dict[str, Any]:
    task_id = task_id or make_task_id(prefix="deliverytask_uav_endpoint_test")
    drone_id = UAV_DEF["code"]
    endpoint = {"x": float(endpoint_x), "y": float(endpoint_y), "z": float(endpoint_z)}
    scenario = build_test_scenario_payload(task_id=task_id, endpoint=endpoint)

    required_sessions = ["LJ-ENGINE_airsim", "LJ-ENGINE_image"]
    if dry_run:
        return {
            "status": "dry_run",
            "mode": "uav_takeoff_at_endpoint_only",
            "task_id": task_id,
            "drone_id": drone_id,
            "required_sessions": required_sessions,
            "scenario": scenario,
            "takeoff_command": {
                "taskId": task_id,
                "dronesId": drone_id,
                "instructionType": "takeoff",
                "mile": takeoff_height_m,
                "speed": takeoff_speed,
            },
            "endpoint": endpoint,
        }

    client = HttpClient(backend_url)
    sessions = {"skipped": True} if skip_session_check else ensure_sessions(client, required_sessions)
    scenario_response = dispatch_test_scenario(
        client,
        task_id=task_id,
        scenario=scenario,
    )
    takeoff_response = send_uav_takeoff(
        client,
        task_id=task_id,
        drone_id=drone_id,
        height_m=takeoff_height_m,
        speed=takeoff_speed,
    )
    payload = {
        "status": "ok",
        "mode": "uav_takeoff_at_endpoint_only",
        "task_id": task_id,
        "drone_id": drone_id,
        "backend_url": backend_url,
        "sessions": sessions,
        "scenario_response": scenario_response,
        "takeoff_response": takeoff_response,
        "endpoint": endpoint,
    }
    payload["result_path"] = str(write_result(task_id, payload))
    return payload


def write_result(task_id: str, payload: dict[str, Any]) -> Path:
    task_dir = RESULTS_DIR / safe_component(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = task_dir / f"run_case_test_{safe_component(task_id)}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def hold_after_takeoff(task_id: str, drone_id: str) -> None:
    print(
        json.dumps(
            {
                "status": "holding",
                "task_id": task_id,
                "drone_id": drone_id,
                "message": "UAV takeoff command has been sent. No further commands will be sent by this script. Press Ctrl+C to exit.",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "status": "stopped",
                    "task_id": task_id,
                    "drone_id": drone_id,
                    "message": "Hold loop stopped by user.",
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


def main() -> None:
    log_path = setup_console_logging(RESULTS_DIR, "deliverytask")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--task-id", default="deliverytask_uav_endpoint_test_001")
    parser.add_argument("--endpoint-x", type=float, default=DEFAULT_ENDPOINT["x"])
    parser.add_argument("--endpoint-y", type=float, default=DEFAULT_ENDPOINT["y"])
    parser.add_argument("--endpoint-z", type=float, default=DEFAULT_ENDPOINT_Z)
    parser.add_argument("--takeoff-height-m", type=float, default=280.0)
    parser.add_argument("--takeoff-speed", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--no-hold", action="store_true", help="Exit after sending takeoff instead of waiting.")
    args = parser.parse_args()

    try:
        result = run_endpoint_test(
            backend_url=args.backend_url,
            task_id=args.task_id,
            endpoint_x=args.endpoint_x,
            endpoint_y=args.endpoint_y,
            endpoint_z=args.endpoint_z,
            takeoff_height_m=args.takeoff_height_m,
            takeoff_speed=args.takeoff_speed,
            dry_run=args.dry_run,
            skip_session_check=args.skip_session_check,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if not args.dry_run and not args.no_hold:
            hold_after_takeoff(result["task_id"], result["drone_id"])
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
