"""Run the route-driven single-drone fire reconnaissance case.

Formal realtime loop:
1. Send scenario to AirSim and image engine.
2. Take off, request photos, and wait for uploaded global/topdown images.
3. Analyze topdown image through /sim/uav/fire/analyze-topdown.
4. If fire is found, report result to UE/AirSim and wait for validation.
5. Otherwise plan next offset through /sim/uav/fire/plan, send it to AirSim,
   wait for executionCompleted, and repeat.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.modules.envs.task_id import make_task_id
from examples._log_util import setup_console_logging, log_cmd, brief_cmd
from examples.singledrone_fire.engines import run_mock_smoke
from examples.singledrone_fire.run_case_test import (
    HttpClient,
    build_scenario_payload,
    ensure_sessions,
    request_topdown_photo,
    safe_component,
    send_scenario,
    send_takeoff,
)

CASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = CASE_DIR / "uploads"
RESULTS_DIR = CASE_DIR / "results"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


async def run_case(
    *,
    backend_url: str = "http://127.0.0.1:9909",
    task_id: str = "",
    airsim_session_key: str = "LJ-ENGINE_airsim",
    image_session_key: str = "LJ-ENGINE_image",
    drone_id: str = "UAV-FIRE-001",
    airsim_speed: float = 20.0,
    initial_takeoff_m: float = 300.0,
    scenario_timeout_sec: float = 30.0,
    action_timeout_sec: float = 180.0,
    image_wait_timeout_sec: float = 420.0,
    validation_timeout_sec: float = 120.0,
    max_steps: int = 50,
    skip_session_check: bool = False,
    wait_fire_validation: bool = True,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _run_case_sync,
        backend_url=backend_url,
        task_id=task_id,
        airsim_session_key=airsim_session_key,
        image_session_key=image_session_key,
        drone_id=drone_id,
        airsim_speed=airsim_speed,
        initial_takeoff_m=initial_takeoff_m,
        scenario_timeout_sec=scenario_timeout_sec,
        action_timeout_sec=action_timeout_sec,
        image_wait_timeout_sec=image_wait_timeout_sec,
        validation_timeout_sec=validation_timeout_sec,
        max_steps=max_steps,
        skip_session_check=skip_session_check,
        wait_fire_validation=wait_fire_validation,
    )


def _run_case_sync(
    *,
    backend_url: str,
    task_id: str,
    airsim_session_key: str,
    image_session_key: str,
    drone_id: str,
    airsim_speed: float,
    initial_takeoff_m: float,
    scenario_timeout_sec: float,
    action_timeout_sec: float,
    image_wait_timeout_sec: float,
    validation_timeout_sec: float,
    max_steps: int,
    skip_session_check: bool,
    wait_fire_validation: bool,
) -> dict[str, Any]:
    client = HttpClient(backend_url)
    task_id = task_id or make_task_id(prefix="singledrone_fire")
    started_at = datetime.now().isoformat(timespec="seconds")
    trajectory: list[dict[str, Any]] = []

    sessions = (
        {"skipped": True}
        if skip_session_check
        else ensure_sessions(
            client,
            airsim_session_key=airsim_session_key,
            image_session_key=image_session_key,
        )
    )
    scenario = build_scenario_payload(task_id)
    scenario_response = send_scenario(
        client,
        task_id=task_id,
        scenario=scenario,
        airsim_session_key=airsim_session_key,
        image_session_key=image_session_key,
        timeout_sec=scenario_timeout_sec,
    )
    takeoff_response = send_takeoff(
        client,
        task_id=task_id,
        airsim_session_key=airsim_session_key,
        drone_id=drone_id,
        height_m=initial_takeoff_m,
        speed=airsim_speed,
        timeout_sec=action_timeout_sec,
    )

    final_report: dict[str, Any] | None = None
    fire_detected = False
    validation_error_m: float | None = None

    for step in range(1, max_steps + 1):
        requested_at = time.time()
        photo_response = request_topdown_photo(
            client,
            task_id=task_id,
            image_session_key=image_session_key,
            drone_id=drone_id,
            step_index=step,
        )
        topdown_path = wait_uploaded_image(
            task_id=task_id,
            drone_id=drone_id,
            image_type="topdown_rgb",
            requested_at=requested_at,
            timeout_sec=image_wait_timeout_sec,
        )
        recognition_response = analyze_topdown(client, topdown_path)
        recognition = recognition_response["result"]
        step_record: dict[str, Any] = {
            "step": step,
            "photo_response": photo_response,
            "topdown_path": str(topdown_path),
            "recognition": recognition_response,
        }

        if recognition.get("fire_detected") is True:
            fire_detected = True
            report_response = report_fire_result(
                client,
                task_id=task_id,
                drone_id=drone_id,
                recognition=recognition,
                airsim_session_key=airsim_session_key,
                validation_timeout_sec=validation_timeout_sec,
                wait_validation=wait_fire_validation,
            )
            validation_error_m = _extract_error_m(report_response.get("validation"))
            if validation_error_m is None:
                validation_error_m = _extract_error_m(report_response)
            step_record["report_response"] = report_response
            trajectory.append(step_record)
            final_report = report_response
            break

        global_path = wait_uploaded_image(
            task_id=task_id,
            drone_id=drone_id,
            image_type="global_rgb",
            requested_at=requested_at,
            timeout_sec=image_wait_timeout_sec,
        )
        plan_response = plan_next_offset(
            client,
            global_path=global_path,
            topdown_path=topdown_path,
            recognition=recognition,
        )
        plan_result = plan_response["result"]
        offset = plan_result.get("offset")
        action_response = send_offset_action(
            client,
            task_id=task_id,
            airsim_session_key=airsim_session_key,
            drone_id=drone_id,
            offset=offset,
            speed=airsim_speed,
            timeout_sec=action_timeout_sec,
        )
        step_record.update(
            {
                "global_path": str(global_path),
                "plan": plan_response,
                "action": action_response,
            }
        )
        trajectory.append(step_record)

    steps = len(trajectory)
    success = fire_detected and final_report is not None
    localization_accuracy = None
    if validation_error_m is not None:
        localization_accuracy = 1.0 if validation_error_m <= 8.0 else 0.0
    summary = {
        "status": "completed" if success else "max_steps_reached",
        "task_id": task_id,
        "started_at": started_at,
        "steps": steps,
        "max_steps": max_steps,
        "fire_detected": 1.0 if fire_detected else 0.0,
        "fire_reported": 1.0 if final_report is not None else 0.0,
        "localization_error_m": validation_error_m,
        "target_coord_accuracy": localization_accuracy,
        "sessions": sessions,
        "scenario_response": scenario_response,
        "takeoff_response": takeoff_response,
        "final_report": final_report,
    }
    result_path = write_results(task_id, summary, trajectory)
    summary["result_path"] = str(result_path)
    return summary


def wait_uploaded_image(
    *,
    task_id: str,
    drone_id: str,
    image_type: str,
    requested_at: float,
    timeout_sec: float,
) -> Path:
    deadline = time.time() + timeout_sec
    task_dir = UPLOAD_ROOT / safe_component(task_id)
    last_status = f"{task_dir} \u4e0d\u5b58\u5728"
    while time.time() < deadline:
        candidates = find_uploaded_candidates(task_dir, drone_id, image_type, requested_at)
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)
        if task_dir.exists():
            last_status = f"{task_dir} \u5b58\u5728\uff0c\u4f46\u672a\u53d1\u73b0\u8bf7\u6c42\u540e\u7684 {image_type} \u539f\u56fe"
        time.sleep(0.5)
    raise RuntimeError(
        f"\u7b49\u5f85 {image_type} \u4e0a\u4f20\u8d85\u65f6: {timeout_sec:.1f}s\uff1b"
        f"taskId={task_id}, droneId={drone_id}\u3002\u6700\u540e\u72b6\u6001: {last_status}"
    )


def find_uploaded_candidates(
    task_dir: Path,
    drone_id: str,
    image_type: str,
    requested_at: float,
) -> list[Path]:
    if not task_dir.exists():
        return []
    roots = [
        task_dir / safe_component(drone_id) / image_type,
        task_dir / "drone1" / image_type,
    ]
    roots.extend(path / image_type for path in task_dir.iterdir() if path.is_dir())
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root in seen or not root.exists():
            continue
        seen.add(root)
        for path in root.iterdir():
            if (
                path.is_file()
                and "_preview" not in path.stem
                and path.suffix.lower() in IMAGE_SUFFIXES
                and path.stat().st_mtime >= requested_at - 1.0
            ):
                candidates.append(path)
    return candidates


def analyze_topdown(client: HttpClient, topdown_path: Path) -> dict[str, Any]:
    return client.post_file("/sim/uav/fire/analyze-topdown", "file", topdown_path, timeout=240.0)


def plan_next_offset(
    client: HttpClient,
    *,
    global_path: Path,
    topdown_path: Path,
    recognition: dict[str, Any],
) -> dict[str, Any]:
    return client.post_multipart(
        "/sim/uav/fire/plan",
        fields={"recognition": json.dumps(recognition, ensure_ascii=False)},
        files={"globalFile": global_path, "topdownFile": topdown_path},
        timeout=240.0,
    )


def send_offset_action(
    client: HttpClient,
    *,
    task_id: str,
    airsim_session_key: str,
    drone_id: str,
    offset: Any,
    speed: float,
    timeout_sec: float,
) -> dict[str, Any]:
    dx, dy = _numeric_pair(offset, "offset")
    distance = math.hypot(dx, dy)
    if distance <= 0.001:
        instruction_type = "stop"
        command = {"mile": 0, "raw": 0, "speed": speed}
    else:
        instruction_type = "forward"
        command = {
            "mile": distance,
            "raw": (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0,
            "speed": speed,
        }
    log_cmd(drone_id, f"{instruction_type}  {brief_cmd(command)}".strip())
    return client.post_json(
        "/sim/uav/airsim/action",
        {
            "taskId": task_id,
            "engineSessionKey": airsim_session_key,
            "broadcast": False,
            "requireAck": False,
            "waitExecutionCompleted": True,
            "executionTimeoutSec": timeout_sec,
            "waitDroneId": drone_id,
            "dronesId": drone_id,
            "instructionType": instruction_type,
            "actionCommand": command,
        },
        timeout=timeout_sec + 5.0,
    )


def report_fire_result(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    recognition: dict[str, Any],
    airsim_session_key: str,
    validation_timeout_sec: float,
    wait_validation: bool,
) -> dict[str, Any]:
    log_cmd(drone_id, "report-result  \u4e0a\u62a5\u706b\u70b9\u5b9a\u4f4d\u7ed3\u679c(stop)")
    return client.post_json(
        "/sim/uav/fire/report-result",
        {
            "taskId": task_id,
            "droneId": drone_id,
            "engineSessionKey": airsim_session_key,
            "status": "stop",
            "offset": recognition.get("offset_from_center_m") or [0, 0],
            "recognition": recognition,
            "waitValidation": wait_validation,
            "validationTimeoutSec": validation_timeout_sec,
        },
        timeout=validation_timeout_sec + 10.0,
    )


def _numeric_pair(value: Any, field_name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field_name} \u5fc5\u987b\u662f\u957f\u5ea6\u4e3a 2 \u7684\u6570\u7ec4: {value}")
    return float(value[0]), float(value[1])


def _extract_error_m(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ("validation_error_m", "error_m", "errorM", "localization_error_m", "distance_m"):
        if payload.get(key) is not None:
            return float(payload[key])
    return None


def write_results(task_id: str, summary: dict[str, Any], trajectory: list[dict[str, Any]]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"single_drone_fire_{safe_component(task_id)}_{timestamp}.json"
    payload = {"summary": summary, "trajectory": trajectory}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--airsim-session-key", default="LJ-ENGINE_airsim")
    parser.add_argument("--image-session-key", default="LJ-ENGINE_image")
    parser.add_argument("--drone-id", default="UAV-FIRE-001")
    parser.add_argument("--airsim-speed", type=float, default=20.0)
    parser.add_argument("--initial-takeoff-m", type=float, default=300.0)
    parser.add_argument("--scenario-timeout-sec", type=float, default=30.0)
    parser.add_argument("--action-timeout-sec", type=float, default=180.0)
    parser.add_argument("--image-wait-timeout-sec", type=float, default=420.0)
    parser.add_argument("--validation-timeout-sec", type=float, default=120.0)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--no-wait-fire-validation", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="run local mock smoke test")
    args = parser.parse_args()

    log_path = setup_console_logging(RESULTS_DIR, "singledrone_fire")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)

    try:
        if args.smoke:
            result = asyncio.run(run_mock_smoke())
        else:
            result = asyncio.run(
                run_case(
                    backend_url=args.backend_url,
                    task_id=args.task_id,
                    airsim_session_key=args.airsim_session_key,
                    image_session_key=args.image_session_key,
                    drone_id=args.drone_id,
                    airsim_speed=args.airsim_speed,
                    initial_takeoff_m=args.initial_takeoff_m,
                    scenario_timeout_sec=args.scenario_timeout_sec,
                    action_timeout_sec=args.action_timeout_sec,
                    image_wait_timeout_sec=args.image_wait_timeout_sec,
                    validation_timeout_sec=args.validation_timeout_sec,
                    max_steps=args.max_steps,
                    skip_session_check=args.skip_session_check,
                    wait_fire_validation=not args.no_wait_fire_validation,
                )
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
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
