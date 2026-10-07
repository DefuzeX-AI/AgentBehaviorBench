"""Standalone singlefire workflow runner.

In full-auto mode this script sends scenario/takeoff/photo commands, then waits
for the external image side to call POST /sim/uav/singlefire. It does not call
the LLM analysis route itself during the closed loop, avoiding duplicate LLM
requests.
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

from app.modules.envs.task_id import make_task_id
from examples._log_util import setup_console_logging, log_cmd
from examples.singledrone_fire.run_case_test import (
    HttpClient,
    build_singlefire_photo_payload,
    build_scenario_payload,
    ensure_sessions,
    safe_component,
    send_scenario,
    send_takeoff,
)

CASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = CASE_DIR / "uploads"
RESULTS_DIR = CASE_DIR / "results"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def run_case_fire(
    *,
    backend_url: str,
    task_id: str,
    drone_id: str,
    global_image: Path | None,
    topdown_image: Path | None,
    airsim_session_key: str = "LJ-ENGINE_airsim",
    image_session_key: str = "LJ-ENGINE_image",
    scenario_timeout_sec: float = 30.0,
    takeoff_height_m: float = 300.0,
    takeoff_speed: float = 20.0,
    takeoff_timeout_sec: float = 0.0,
    photo_timeout_sec: float = 420.0,
    skip_session_check: bool = False,
    dispatch_result: bool = True,
    dry_run_dispatch: bool = False,
    send_continue_action: bool = True,
    max_steps: int = 50,
) -> dict[str, Any]:
    task_id = task_id or make_task_id(prefix="singlefire")
    client = HttpClient(backend_url)
    setup: dict[str, Any] = {"mode": "image_only"}
    trajectory: list[dict[str, Any]] = []

    single_screenshot_mode = global_image is not None and topdown_image is None
    if global_image is not None and topdown_image is not None:
        global_path = global_image
        topdown_path = topdown_image
    elif single_screenshot_mode:
        global_path = global_image
        topdown_path = None
    elif global_image is None and topdown_image is None:
        setup = initialize_photo_sequence(
            client,
            task_id=task_id,
            drone_id=drone_id,
            airsim_session_key=airsim_session_key,
            image_session_key=image_session_key,
            scenario_timeout_sec=scenario_timeout_sec,
            takeoff_height_m=takeoff_height_m,
            takeoff_speed=takeoff_speed,
            takeoff_timeout_sec=takeoff_timeout_sec,
            skip_session_check=skip_session_check,
        )
        final_status = "max_steps_reached"
        for step in range(1, max_steps + 1):
            step_record = run_singlefire_step(
                client,
                task_id=task_id,
                drone_id=drone_id,
                airsim_session_key=airsim_session_key,
                image_session_key=image_session_key,
                photo_timeout_sec=photo_timeout_sec,
                takeoff_timeout_sec=takeoff_timeout_sec,
                dispatch_result=dispatch_result,
                dry_run_dispatch=dry_run_dispatch,
                send_continue_action=send_continue_action,
                step=step,
            )
            trajectory.append(step_record)
            result = step_record["analysis"]["result"]
            if result.get("status") == "stop":
                final_status = "stop"
                break
            if not send_continue_action or dry_run_dispatch:
                final_status = "continue_without_action"
                break
        payload = {
            "mode": "singlefire_full_auto_loop",
            "status": final_status,
            "task_id": task_id,
            "drone_id": drone_id,
            "setup": setup,
            "steps": len(trajectory),
            "max_steps": max_steps,
            "trajectory": trajectory,
        }
        payload["result_path"] = str(write_result(task_id, payload))
        return payload
    else:
        raise RuntimeError("--topdown-image \u4e0d\u80fd\u5355\u72ec\u63d0\u4f9b\uff1b\u53ea\u4f20 --global-image \u8868\u793a\u5355\u56fe\u88c1\u526a\u6a21\u5f0f")

    step_record = analyze_and_dispatch_singlefire(
        client,
        task_id=task_id,
        drone_id=drone_id,
        airsim_session_key=airsim_session_key,
        global_path=global_path,
        topdown_path=topdown_path,
        dispatch_result=dispatch_result,
        dry_run_dispatch=dry_run_dispatch,
        send_continue_action=send_continue_action,
        takeoff_timeout_sec=takeoff_timeout_sec,
    )
    payload = {
        "mode": (
            "singlefire_single_screenshot"
            if single_screenshot_mode
            else "singlefire_two_image"
        ),
        "task_id": task_id,
        "drone_id": drone_id,
        "setup": setup,
        "global_image": str(global_path),
        "topdown_image": str(topdown_path) if topdown_path is not None else None,
        **step_record,
    }
    payload["result_path"] = str(write_result(task_id, payload))
    return payload


def dispatch_singlefire_result(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    airsim_session_key: str,
    result: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    log_cmd(drone_id, f"singlefire/result  \u4e0b\u53d1\u8bc6\u56fe\u7ed3\u679c(status={result.get('status')}, dryRun={dry_run})")
    return client.post_json(
        "/sim/uav/singlefire/result",
        {
            "taskId": task_id,
            "droneId": drone_id,
            "engineSessionKey": airsim_session_key,
            "dryRun": dry_run,
            "result": {
                "thought_process": result.get("thought_process"),
                "status": result.get("status"),
                "fire_detected": result.get("fire_detected"),
                "target_visible": result.get("target_visible"),
                "coord_frame": result.get("coord_frame"),
                "fire_pixel_coord": result.get("fire_pixel_coord"),
                "fire_offset_px": result.get("fire_offset_px"),
                "target_pixel_coord": result.get("target_pixel_coord"),
                "current_coord": result.get("current_coord"),
                "action_offset_px": result.get("action_offset_px"),
                "reason": result.get("reason"),
            },
        },
        timeout=30.0,
    )


def run_singlefire_step(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    airsim_session_key: str,
    image_session_key: str,
    photo_timeout_sec: float,
    takeoff_timeout_sec: float,
    dispatch_result: bool,
    dry_run_dispatch: bool,
    send_continue_action: bool,
    step: int,
) -> dict[str, Any]:
    requested_at = time.time()
    photo_response = request_singlefire_photo(
        client,
        task_id=task_id,
        image_session_key=image_session_key,
        drone_id=drone_id,
        step_index=step,
    )
    analysis = wait_external_singlefire_result(
        task_id=task_id,
        drone_id=drone_id,
        requested_at=requested_at,
        timeout_sec=photo_timeout_sec,
    )
    step_record = dispatch_and_act_on_singlefire_result(
        client,
        task_id=task_id,
        drone_id=drone_id,
        airsim_session_key=airsim_session_key,
        analysis=analysis,
        dispatch_result=dispatch_result,
        dry_run_dispatch=dry_run_dispatch,
        send_continue_action=send_continue_action,
        takeoff_timeout_sec=takeoff_timeout_sec,
    )
    return {
        "step": step,
        "photo_response": photo_response,
        **step_record,
    }


def request_singlefire_photo(
    client: HttpClient,
    *,
    task_id: str,
    image_session_key: str,
    drone_id: str,
    step_index: int,
) -> dict[str, Any]:
    log_cmd(image_session_key, f"take-photo  \u62cd\u7167(drone={drone_id}, step={step_index})")
    return client.post_json(
        "/sim/engine/image/take-photo",
        build_singlefire_photo_payload(
            task_id=task_id,
            image_session_key=image_session_key,
            drone_id=drone_id,
            step_index=step_index,
        ),
        timeout=10.0,
    )


def analyze_and_dispatch_singlefire(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    airsim_session_key: str,
    global_path: Path,
    topdown_path: Path | None,
    dispatch_result: bool,
    dry_run_dispatch: bool,
    send_continue_action: bool,
    takeoff_timeout_sec: float,
) -> dict[str, Any]:
    files = {"globalFile": global_path}
    if topdown_path is not None:
        files["topdownFile"] = topdown_path
    response = client.post_multipart(
        "/sim/uav/singlefire",
        fields={
            "taskId": task_id,
            "droneId": drone_id,
            "globalLengthM": "6000",
            "globalWidthM": "6000",
            "topdownLengthM": "400",
            "topdownWidthM": "300",
        },
        files=files,
        timeout=300.0,
    )
    dispatch_response = None
    if dispatch_result:
        dispatch_response = dispatch_singlefire_result(
            client,
            task_id=task_id,
            drone_id=drone_id,
            airsim_session_key=airsim_session_key,
            result=response["result"],
            dry_run=dry_run_dispatch,
        )
    action_response = None
    if send_continue_action and not dry_run_dispatch and response["result"].get("status") == "continue":
        action_response = send_singlefire_continue_action(
            client,
            task_id=task_id,
            drone_id=drone_id,
            airsim_session_key=airsim_session_key,
            result=response["result"],
            timeout_sec=takeoff_timeout_sec,
        )
    return {
        "global_image": str(global_path),
        "topdown_image": str(topdown_path) if topdown_path is not None else None,
        "analysis": response,
        "dispatch_response": dispatch_response,
        "action_response": action_response,
    }


def dispatch_and_act_on_singlefire_result(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    airsim_session_key: str,
    analysis: dict[str, Any],
    dispatch_result: bool,
    dry_run_dispatch: bool,
    send_continue_action: bool,
    takeoff_timeout_sec: float,
) -> dict[str, Any]:
    result = analysis["result"]
    dispatch_response = None
    if dispatch_result:
        dispatch_response = dispatch_singlefire_result(
            client,
            task_id=task_id,
            drone_id=drone_id,
            airsim_session_key=airsim_session_key,
            result=result,
            dry_run=dry_run_dispatch,
        )
    action_response = None
    if send_continue_action and not dry_run_dispatch and result.get("status") == "continue":
        action_response = send_singlefire_continue_action(
            client,
            task_id=task_id,
            drone_id=drone_id,
            airsim_session_key=airsim_session_key,
            result=result,
            timeout_sec=takeoff_timeout_sec,
        )
    return {
        "global_image": analysis.get("savedImages", {}).get("global_rgb", {}).get("path"),
        "topdown_image": analysis.get("savedImages", {}).get("topdown_rgb", {}).get("path"),
        "analysis": analysis,
        "dispatch_response": dispatch_response,
        "action_response": action_response,
    }


def send_singlefire_continue_action(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    airsim_session_key: str,
    result: dict[str, Any],
    timeout_sec: float,
) -> dict[str, Any]:
    offset = result.get("action_offset_px")
    if not isinstance(offset, (list, tuple)) or len(offset) != 2:
        raise RuntimeError(f"action_offset_px \u5fc5\u987b\u662f\u957f\u5ea6\u4e3a 2 \u7684\u6570\u7ec4: {offset}")
    log_cmd(drone_id, f"setDestination  x={float(offset[0])},y={float(offset[1])}")
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
            "instructionType": "setDestination",
            "actionCommand": {
                "x": float(offset[0]),
                "y": float(offset[1]),
            },
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )


def initialize_photo_sequence(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    airsim_session_key: str,
    image_session_key: str,
    scenario_timeout_sec: float,
    takeoff_height_m: float,
    takeoff_speed: float,
    takeoff_timeout_sec: float,
    skip_session_check: bool,
) -> dict[str, Any]:
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
        height_m=takeoff_height_m,
        speed=takeoff_speed,
        timeout_sec=takeoff_timeout_sec,
    )
    return {
        "mode": "initialized",
        "sessions": sessions,
        "scenario_response": scenario_response,
        "takeoff_response": takeoff_response,
    }


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


def wait_external_singlefire_result(
    *,
    task_id: str,
    drone_id: str,
    requested_at: float,
    timeout_sec: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        candidates = find_singlefire_result_candidates(
            task_id=task_id,
            drone_id=drone_id,
            requested_at=requested_at,
        )
        if candidates:
            path, payload = max(candidates, key=lambda item: item[0].stat().st_mtime)
            payload = dict(payload)
            payload["result_path"] = str(path)
            if payload.get("status") == "failed":
                raise RuntimeError(
                    "\u5916\u90e8 /sim/uav/singlefire \u5df2\u6536\u5230\u56fe\u7247\u4f46\u8bc6\u56fe\u5931\u8d25: "
                    f"{payload.get('error_type')}: {payload.get('error')}\uff1b"
                    f"\u9519\u8bef\u7ed3\u679c\u6587\u4ef6: {path}"
                )
            return payload
        time.sleep(0.5)
    raise RuntimeError(
        f"\u7b49\u5f85\u5916\u90e8 singlefire \u8bc6\u56fe\u7ed3\u679c\u8d85\u65f6: {timeout_sec:.1f}s\uff1b"
        f"taskId={task_id}, droneId={drone_id}\u3002\u8bf7\u786e\u8ba4\u6280\u672f\u90e8\u5df2\u5728\u62cd\u7167\u540e\u8c03\u7528 /sim/uav/singlefire"
    )


def find_singlefire_result_candidates(
    *,
    task_id: str,
    drone_id: str,
    requested_at: float,
) -> list[tuple[Path, dict[str, Any]]]:
    task_key = safe_component(task_id)
    prefix = f"singlefire_{task_key}_"
    candidates: list[tuple[Path, dict[str, Any]]] = []
    search_dirs = [RESULTS_DIR / task_key, RESULTS_DIR]
    if not any(path.exists() for path in search_dirs):
        return candidates
    seen: set[Path] = set()
    for result_dir in search_dirs:
        if not result_dir.exists():
            continue
        for path in result_dir.glob(f"{prefix}*.json"):
            if path in seen:
                continue
            seen.add(path)
            if path.stat().st_mtime < requested_at - 1.0:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if payload.get("taskId") != task_id or payload.get("droneId") != drone_id:
                continue
            result = payload.get("result")
            if not isinstance(result, dict) and payload.get("status") != "failed":
                continue
            candidates.append((path, payload))
    return candidates


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


def latest_uploaded_image(task_id: str, drone_id: str, image_type: str) -> Path:
    roots = [
        UPLOAD_ROOT / safe_component(task_id) / safe_component(drone_id) / image_type,
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        candidates.extend(
            path
            for path in root.iterdir()
            if path.is_file()
            and "_preview" not in path.stem
            and path.suffix.lower() in IMAGE_SUFFIXES
        )
    if not candidates:
        raise RuntimeError(f"\u672a\u627e\u5230 {image_type} \u56fe\u7247\uff0c\u8bf7\u663e\u5f0f\u4f20 --global-image/--topdown-image")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def write_result(task_id: str, payload: dict[str, Any]) -> Path:
    task_dir = RESULTS_DIR / safe_component(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = task_dir / f"run_case_fire_{safe_component(task_id)}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--drone-id", default="UAV-FIRE-001")
    parser.add_argument("--airsim-session-key", default="LJ-ENGINE_airsim")
    parser.add_argument("--image-session-key", default="LJ-ENGINE_image")
    parser.add_argument("--scenario-timeout-sec", type=float, default=30.0)
    parser.add_argument("--takeoff-height-m", type=float, default=300.0)
    parser.add_argument("--takeoff-speed", type=float, default=20.0)
    parser.add_argument("--takeoff-timeout-sec", type=float, default=0.0)
    parser.add_argument("--photo-timeout-sec", type=float, default=420.0)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--no-dispatch-result", action="store_true")
    parser.add_argument("--dry-run-dispatch", action="store_true")
    parser.add_argument("--no-send-continue-action", action="store_true")
    parser.add_argument("--global-image", type=Path, default=None)
    parser.add_argument("--topdown-image", type=Path, default=None)
    args = parser.parse_args()

    log_path = setup_console_logging(RESULTS_DIR, "singledrone_fire")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)

    try:
        result = run_case_fire(
            backend_url=args.backend_url,
            task_id=args.task_id,
            drone_id=args.drone_id,
            global_image=args.global_image,
            topdown_image=args.topdown_image,
            airsim_session_key=args.airsim_session_key,
            image_session_key=args.image_session_key,
            scenario_timeout_sec=args.scenario_timeout_sec,
            takeoff_height_m=args.takeoff_height_m,
            takeoff_speed=args.takeoff_speed,
            takeoff_timeout_sec=args.takeoff_timeout_sec,
            photo_timeout_sec=args.photo_timeout_sec,
            skip_session_check=args.skip_session_check,
            dispatch_result=not args.no_dispatch_result,
            dry_run_dispatch=args.dry_run_dispatch,
            send_continue_action=not args.no_send_continue_action,
            max_steps=args.max_steps,
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
