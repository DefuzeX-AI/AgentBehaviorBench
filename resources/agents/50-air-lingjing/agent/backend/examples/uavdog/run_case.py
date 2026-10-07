"""UAV-guided dog path-planning workflow runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.modules.envs.scenario import ScenarioSpec
from app.modules.envs.task_id import make_task_id
from examples._log_util import (setup_console_logging, log_cmd, brief_cmd, restart_engine_between_episodes,
                                 wait_engine_ready, add_backbone_args, push_vision_override, send_task_complete,
                                 log_http_req, log_http_resp, log_http_err, log_receipt, log_vision)
from examples.uavdog.scenario import DOG_DEF, UAV_DEF, UAV_HEIGHT_M, build_uavdog_scenario

CASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = CASE_DIR / "results"
DEFAULT_PUBLIC_UPLOAD_BASE_URL = "http://127.0.0.1:9909"


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, path: str, *, timeout: float = 5.0) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        log_http_req("GET", path)
        try:
            with self._opener.open(url, timeout=timeout) as response:
                data = self._decode(url, response.read().decode("utf-8"))
                log_http_resp("GET", path, data)
                return data
        except urllib.error.URLError as exc:
            log_http_err("GET", path, exc)
            raise RuntimeError(f"\u65e0\u6cd5\u8fde\u63a5\u540e\u7aef\u670d\u52a1 {url}: {exc}") from exc

    def post_json(self, path: str, payload: dict[str, Any], *, timeout: float | None = 30.0) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        log_http_req("POST", path, payload)
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response_context = self._opener.open(request) if timeout is None or timeout <= 0 else self._opener.open(request, timeout=timeout)
            with response_context as response:
                data = self._decode(url, response.read().decode("utf-8"))
                log_http_resp("POST", path, data)
                return data
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            log_http_err("POST", path, detail)
            raise RuntimeError(f"HTTP {exc.code} \u8c03\u7528 {url} \u5931\u8d25: {detail}") from exc
        except urllib.error.URLError as exc:
            log_http_err("POST", path, exc)
            raise RuntimeError(f"\u65e0\u6cd5\u8fde\u63a5\u540e\u7aef\u670d\u52a1 {url}: {exc}") from exc

    @staticmethod
    def _decode(url: str, raw: str) -> dict[str, Any]:
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"\u540e\u7aef\u54cd\u5e94\u4e0d\u662f JSON: {url}: {raw[:300]}") from exc
        if envelope.get("code", 200) != 200:
            raise RuntimeError(str(envelope.get("msg") or envelope))
        data = envelope.get("data")
        return data if isinstance(data, dict) else {"data": data}


def safe_component(value: str | None, default: str = "unknown") -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "").strip())
    return (safe.strip("._") or default)[:120]


def collision_context_path(task_id: str) -> Path:
    return RESULTS_DIR / safe_component(task_id) / "collision_context.json"


def clear_collision_context(task_id: str) -> None:
    path = collision_context_path(task_id)
    if path.exists():
        path.unlink()


def write_collision_context(
    *,
    task_id: str,
    step_index: int,
    result: dict[str, Any],
    motion_event: dict[str, Any],
) -> Path:
    path = collision_context_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "hasCollision": True,
        "collisionStepIndex": step_index,
        "nextStepIndex": step_index + 1,
        "failedWaypoints": result.get("waypoints") or [],
        "previousDogPixelCoord": result.get("dog_pixel_coord"),
        "previousTargetPixelCoord": result.get("target_pixel_coord"),
        "previousReason": result.get("reason"),
        "motionEvent": motion_event,
        "instruction": "\u4e0a\u4e00\u8f6e\u673a\u5668\u72d7\u6267\u884c\u8def\u5f84\u65f6\u53d1\u751f\u78b0\u649e\u3002\u4e0b\u4e00\u8f6e\u89c4\u5212\u5fc5\u987b\u907f\u5f00 failedWaypoints \u9644\u8fd1\u533a\u57df\uff0c\u4f18\u5148\u9009\u62e9\u53ef\u89c1\u9053\u8def\u3001\u8def\u53e3\u6216\u7a7a\u65f7\u533a\u57df\u7ed5\u884c\u3002",
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def build_scenario_payload(*, task_id: str, max_steps: int) -> dict[str, Any]:
    spec = ScenarioSpec.from_definition(build_uavdog_scenario(max_steps=max_steps))
    spec.task_id = task_id
    return spec.to_engine_payload()


def ensure_sessions(client: HttpClient, required: list[str]) -> dict[str, Any]:
    data = client.get("/websocket/api/sessions", timeout=5.0)
    sessions = (data.get("sessionsByType") or {}).get("LJ-ENGINE") or []
    connected = {
        str(item.get("sessionKey") or item.get("session_key"))
        for item in sessions
        if item.get("connected", True)
    }
    missing = [key for key in required if key not in connected]
    if missing:
        available = ", ".join(sorted(connected)) or "\u65e0"
        raise RuntimeError(f"{', '.join(missing)} \u672a\u8fde\u63a5\uff1b\u5f53\u524d LJ-ENGINE \u4f1a\u8bdd: {available}")
    return data


def dispatch_scenario(client: HttpClient, *, task_id: str, scenario: dict[str, Any]) -> dict[str, Any]:
    responses: dict[str, Any] = {}
    for name, path in {
        "airsim": "/sim/engine/airsim/scenario",
        "go2": "/sim/engine/go2/scenario",
        "image": "/sim/engine/image/scenario",
    }.items():
        log_cmd(f"LJ-ENGINE_{name}", "\u4e0b\u53d1\u60f3\u5b9a scenario")
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


def send_uav_takeoff(client: HttpClient, *, task_id: str, drone_id: str, height_m: float, speed: float) -> dict[str, Any]:
    log_cmd(drone_id, f"takeoff  mile={height_m},speed={speed}")
    return client.post_json(
        "/sim/uav/airsim/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_airsim",
            "broadcast": False,
            "requireAck": False,
            "waitExecutionCompleted": True,
            "executionTimeoutSec": 0,
            "waitDroneId": drone_id,
            "dronesId": drone_id,
            "instructionType": "takeoff",
            "mile": height_m,
            "raw": 0,
            "speed": speed,
        },
        timeout=None,
    )


def request_uav_topdown_photo(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    dog_id: str,
    step_index: int,
    public_upload_base_url: str,
) -> dict[str, Any]:
    upload_url = f"{public_upload_base_url.rstrip('/')}/sim/vision/upload"
    photo_id = f"{task_id}_{drone_id}_topdown_step_{step_index}"
    upload_fields = {
        "taskId": task_id,
        "taskType": "uavdog",
        "agentId": drone_id,
        "agentType": "uav",
        "viewType": "topdown",
        "analysisType": "uavdog_path_planning",
        "stepIndex": step_index,
        "photoid": photo_id,
        "topdownLengthM": 400,
        "topdownWidthM": 300,
        "subtaskIndex": 0,
    }
    log_cmd(drone_id, f"takePhoto  topdown step={step_index}")
    return client.post_json(
        "/sim/engine/image/take-photo",
        {
            "commandType": "takePhoto",
            "taskId": task_id,
            "modelIdList": [
                {
                    "droneId": drone_id,
                    "carId": "",
                    "dogId": "",
                    "viewType": "topdown",
                    "photoid": photo_id,
                    "uploadSpec": {
                        "url": upload_url,
                        "method": "POST",
                        "contentType": "multipart/form-data",
                        "fileField": "file",
                        "fields": upload_fields,
                    },
                }
            ],
        },
        timeout=10.0,
    )


def wait_uavdog_result(
    *,
    task_id: str,
    drone_id: str,
    step_index: int,
    requested_at: float,
    timeout_sec: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    task_dir = RESULTS_DIR / safe_component(task_id)
    prefix = f"uavdog_path_planning_{safe_component(task_id)}_"
    while time.time() < deadline:
        candidates: list[tuple[Path, dict[str, Any]]] = []
        if task_dir.exists():
            for path in task_dir.glob(f"{prefix}*.json"):
                if path.stat().st_mtime < requested_at - 1.0:
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if (
                    payload.get("taskId") == task_id
                    and payload.get("droneId") == drone_id
                    and int(payload.get("stepIndex") or 0) == step_index
                ):
                    candidates.append((path, payload))
        if candidates:
            path, payload = max(candidates, key=lambda item: item[0].stat().st_mtime)
            payload = dict(payload)
            payload["result_path"] = str(path)
            return payload
        time.sleep(0.5)
    raise RuntimeError(
        f"\u7b49\u5f85 uavdog \u4fef\u89c6\u56fe\u8def\u5f84\u89c4\u5212\u7ed3\u679c\u8d85\u65f6: {timeout_sec:.1f}s\uff1b"
        f"taskId={task_id}, droneId={drone_id}, stepIndex={step_index}\u3002"
        "\u8bf7\u786e\u8ba4\u6280\u672f\u90e8\u5df2\u5728\u62cd\u7167\u540e\u8c03\u7528 /sim/vision/upload\uff0canalysisType=uavdog_path_planning"
    )


def send_dog_path_plan(client: HttpClient, *, task_id: str, dog_id: str, waypoints: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_waypoints: list[dict[str, Any]] = []
    for index, waypoint in enumerate(waypoints, start=1):
        offset = waypoint["targetOffsetPx"]
        normalized_waypoints.append(
            {
                "point_index": index,
                "description": f"UAV planned junction offset {index}",
                "targetOffsetPx": [float(offset[0]), float(offset[1])],
                "uavHeightM": float(waypoint.get("uavHeightM") or UAV_HEIGHT_M),
            }
        )
    log_cmd(dog_id, f"PathPlanning  waypoints={len(normalized_waypoints)}")
    return client.post_json(
        "/sim/engine/go2/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_go2",
            "broadcast": False,
            "requireAck": False,
            "commandType": "executeAction",
            "unmannedDogAction": [
                {
                    "unmannedDogId": dog_id,
                    "NavigationType": "PathPlanning",
                    "PathPlanning": {
                        "waypoints": normalized_waypoints,
                    },
                }
            ],
        },
        timeout=10.0,
    )


def wait_dog_motion_event(client: HttpClient, *, task_id: str, timeout_sec: float) -> dict[str, Any]:
    event = client.post_json(
        "/sim/engine/event/wait",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_go2",
            "commandTypes": ["executionCompleted", "collision"],
            "timeoutSec": timeout_sec,
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )
    response = event.get("response") if isinstance(event.get("response"), dict) else event
    event_command_type = response.get("commandType") if isinstance(response, dict) else None
    event["dog_motion_status"] = "collision" if event_command_type == "collision" else "completed"
    return event


def report_uavdog_result(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    dog_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    command = {
        "commandType": "uavdogNavigationResult",
        "taskId": task_id,
        "droneId": drone_id,
        "dogId": dog_id,
        "status": result.get("status"),
        "arrived": result.get("arrived"),
        "result": result,
    }
    responses: dict[str, Any] = {}
    for name, session_key in {
        "airsim": "LJ-ENGINE_airsim",
        "go2": "LJ-ENGINE_go2",
        "image": "LJ-ENGINE_image",
    }.items():
        log_cmd(session_key, f"uavdogNavigationResult  status={command.get('status')},arrived={command.get('arrived')}")
        responses[name] = client.post_json(
            "/sim/engine/command",
            {
                "taskId": task_id,
                "engineSessionKey": session_key,
                "broadcast": False,
                "requireAck": False,
                "command": command,
            },
            timeout=10.0,
        )
    return responses


def write_run_result(task_id: str, payload: dict[str, Any]) -> Path:
    task_dir = RESULTS_DIR / safe_component(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = task_dir / f"run_case_{safe_component(task_id)}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def run_case(
    *,
    task_id: str | None = None,
    backend_url: str = "http://127.0.0.1:9909",
    public_upload_base_url: str = DEFAULT_PUBLIC_UPLOAD_BASE_URL,
    max_steps: int = 60,
    photo_timeout_sec: float = 420.0,
    dog_event_timeout_sec: float = 0.0,
    skip_session_check: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    task_id = task_id or make_task_id(prefix="uavdog")
    client = HttpClient(backend_url)
    drone_id = str(UAV_DEF["code"])
    dog_id = str(DOG_DEF["code"])
    scenario = build_scenario_payload(task_id=task_id, max_steps=max_steps)
    trace: list[dict[str, Any]] = []

    if not skip_session_check:
        trace.append({"phase": "sessions", "response": ensure_sessions(client, ["LJ-ENGINE_airsim", "LJ-ENGINE_go2", "LJ-ENGINE_image"])})
    if dry_run:
        result = {
            "status": "dry_run",
            "taskId": task_id,
            "droneId": drone_id,
            "dogId": dog_id,
            "scenario": scenario,
        }
        result["result_path"] = str(write_run_result(task_id, result))
        return result

    try:
        send_task_complete(client, task_id=task_id)  
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u5148\u53d1 complete \u590d\u4f4d\u5f15\u64ce (taskId={task_id})", flush=True)
    except Exception as _exc:  # noqa: BLE001
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u7684 complete \u5931\u8d25(\u5ffd\u7565): {_exc}", flush=True)
    trace.append({"phase": "scenario", "response": dispatch_scenario(client, task_id=task_id, scenario=scenario)})
    wait_engine_ready(client, task_id=task_id, engine="airsim")
    clear_collision_context(task_id)
    trace.append({"phase": "uav_takeoff", "response": send_uav_takeoff(client, task_id=task_id, drone_id=drone_id, height_m=UAV_HEIGHT_M, speed=20)})

    final_status = "failed"
    final_result: dict[str, Any] | None = None
    for step_index in range(1, max_steps + 1):
        requested_at = time.time()
        trace.append(
            {
                "phase": "request_uav_topdown_photo",
                "stepIndex": step_index,
                "response": request_uav_topdown_photo(
                    client,
                    task_id=task_id,
                    drone_id=drone_id,
                    dog_id=dog_id,
                    step_index=step_index,
                    public_upload_base_url=public_upload_base_url,
                ),
            }
        )
        policy_payload = wait_uavdog_result(
            task_id=task_id,
            drone_id=drone_id,
            step_index=step_index,
            requested_at=requested_at,
            timeout_sec=photo_timeout_sec,
        )
        result = dict(policy_payload.get("result") or {})
        log_vision(drone_id, "uavdog_path_planning", result)
        trace.append({"phase": "uavdog_path_planning", "stepIndex": step_index, "result": result, "result_path": policy_payload.get("result_path")})
        final_result = result

        if result.get("arrived") or result.get("status") == "completed":
            final_status = "completed"
            trace.append({"phase": "report_completed", "response": report_uavdog_result(client, task_id=task_id, drone_id=drone_id, dog_id=dog_id, result=result)})
            break
        if result.get("status") == "failed":
            final_status = "failed"
            trace.append({"phase": "report_failed", "response": report_uavdog_result(client, task_id=task_id, drone_id=drone_id, dog_id=dog_id, result=result)})
            break

        waypoints = result.get("waypoints") or []
        if not waypoints:
            final_status = "failed"
            result["reason"] = result.get("reason") or "LLM \u672a\u8f93\u51fa\u53ef\u6267\u884c waypoints"
            trace.append({"phase": "report_failed_no_waypoints", "response": report_uavdog_result(client, task_id=task_id, drone_id=drone_id, dog_id=dog_id, result=result)})
            break

        trace.append({"phase": "dispatch_dog_path_plan", "stepIndex": step_index, "response": send_dog_path_plan(client, task_id=task_id, dog_id=dog_id, waypoints=waypoints)})
        motion_event = wait_dog_motion_event(client, task_id=task_id, timeout_sec=dog_event_timeout_sec)
        log_receipt(dog_id, motion_event)
        trace.append({"phase": "wait_dog_motion_event", "stepIndex": step_index, "response": motion_event})
        if motion_event.get("dog_motion_status") == "collision":
            context_path = write_collision_context(
                task_id=task_id,
                step_index=step_index,
                result=result,
                motion_event=motion_event,
            )
            trace.append(
                {
                    "phase": "collision_replan",
                    "stepIndex": step_index,
                    "collisionContextPath": str(context_path),
                    "message": "dog collision received; next UAV topdown planning will include collision context",
                }
            )
    else:
        final_status = "failed"
        final_result = final_result or {"status": "failed", "reason": f"\u8fbe\u5230 max_steps={max_steps} \u4ecd\u672a\u5b8c\u6210"}

    output = {
        "status": final_status,
        "taskId": task_id,
        "droneId": drone_id,
        "dogId": dog_id,
        "uavHeightM": UAV_HEIGHT_M,
        "finalResult": final_result,
        "trace": trace,
    }
    output["result_path"] = str(write_run_result(task_id, output))
    return output


async def run_experiment(args: argparse.Namespace) -> list[dict[str, Any]]:
    client = HttpClient(args.backend_url)
    summaries: list[dict[str, Any]] = []
    for i in range(1, args.episodes + 1):
        episode_task_id = f"{args.task_id}_ep{i}"
        print(f"\n========== \u7b2c {i}/{args.episodes} \u8f6e  task_id={episode_task_id} ==========", flush=True)

        if i >= 2:
            print(f"[\u8f6e\u95f4\u91cd\u542f] \u91cd\u542f\u5f15\u64ce\u5e76\u7b49\u5f85 {args.engine_restart_wait_sec}s ...", flush=True)
            await asyncio.to_thread(
                restart_engine_between_episodes,
                client,
                task_id=episode_task_id,
                wait_sec=args.engine_restart_wait_sec,
            )

        try:
            result = await asyncio.to_thread(
                run_case,
                task_id=episode_task_id,
                backend_url=args.backend_url,
                public_upload_base_url=args.public_upload_base_url,
                max_steps=args.max_steps,
                photo_timeout_sec=args.photo_timeout_sec,
                dog_event_timeout_sec=args.dog_event_timeout_sec,
                skip_session_check=args.skip_session_check,
                dry_run=args.dry_run,
            )
            summaries.append(
                {
                    "episode": i,
                    "taskId": episode_task_id,
                    "status": result.get("status"),
                    "result_path": result.get("result_path"),
                }
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            
            if not args.dry_run:
                try:
                    await asyncio.to_thread(send_task_complete, client, task_id=episode_task_id)
                except Exception as exc2:  # noqa: BLE001
                    print(f"[\u5f15\u64ce] \u4e0b\u53d1 complete \u5931\u8d25(\u5ffd\u7565): {exc2}", flush=True)
        except Exception as exc:  # noqa: BLE001
            summaries.append(
                {
                    "episode": i,
                    "taskId": episode_task_id,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "episode": i,
                        "taskId": episode_task_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Run UAV-guided dog path planning task")
    parser.add_argument("--task-id", default="uavdog_test_001")
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--public-upload-base-url", default=DEFAULT_PUBLIC_UPLOAD_BASE_URL)
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--photo-timeout-sec", type=float, default=420.0)
    parser.add_argument("--dog-event-timeout-sec", type=float, default=0.0)
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--engine-restart-wait-sec", type=float, default=20.0)
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    add_backbone_args(parser)   
    args = parser.parse_args()

    log_path = setup_console_logging(RESULTS_DIR, "uavdog")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)

    push_vision_override(HttpClient(args.backend_url), args)   
    summaries = asyncio.run(run_experiment(args))

    print("\n========== \u591a\u8f6e\u5b9e\u9a8c\u6c47\u603b ==========", flush=True)
    for item in summaries:
        line = f"  ep{item['episode']}  task_id={item['taskId']}  status={item['status']}"
        if item.get("error"):
            line += f"  error={item['error_type']}: {item['error']}"
        print(line, flush=True)

    if not summaries or any(item.get("status") not in ("completed", "dry_run") for item in summaries):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
