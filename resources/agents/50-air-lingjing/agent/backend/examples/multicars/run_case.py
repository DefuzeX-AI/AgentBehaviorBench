"""Run the multi-car task allocation workflow.

Flow:
1. Broadcast the scenario with 3 cars and 10 task points to all online engines.
2. Wait for Carla to return ``allDistancesReport``.
3. Ask the LLM to assign task points to cars based on the distance matrix.
4. Dispatch one task point per car, then wait for ``executionCompleted`` events and
   continue with the next point for that car.
"""

from __future__ import annotations

import argparse
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
from examples._log_util import (
    add_backbone_args,
    brief_cmd,
    log_cmd,
    log_http_err,
    log_http_req,
    log_http_resp,
    log_receipt,
    push_vision_override,
    restart_engine_between_episodes,
    send_task_complete,
    setup_console_logging,
    wait_engine_ready,
)
from examples.multicars.policy import allocate_tasks_sync, safe_component
from examples.multicars.scenario import (
    CAR_DEFS,
    TASK_POINTS,
    build_multicars_scenario,
    car_ids,
    normalize_task_points,
)

CASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = CASE_DIR / "results"


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
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        log_http_req("POST", path, payload)
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


def load_task_points(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return normalize_task_points(TASK_POINTS)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        points = payload.get("taskPoints") or payload.get("task_points") or payload.get("points")
    else:
        points = payload
    if not isinstance(points, list):
        raise RuntimeError(f"\u4efb\u52a1\u70b9\u6587\u4ef6\u5fc5\u987b\u662f\u6570\u7ec4\uff0c\u6216\u5305\u542b taskPoints/task_points/points \u6570\u7ec4: {path}")
    return normalize_task_points(points)


def load_distance_report(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_distance_report(payload)


def build_scenario_payload(task_id: str, task_points: list[dict[str, Any]]) -> dict[str, Any]:
    spec = ScenarioSpec.from_definition(build_multicars_scenario(task_points=task_points))
    spec.task_id = task_id
    return spec.to_engine_payload()


def broadcast_scenario_to_engines(
    client: HttpClient,
    *,
    task_id: str,
    scenario: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    log_cmd("LJ-ENGINE(\u5e7f\u64ad)", f"scenario  \u5e7f\u64ad\u591a\u8f66\u60f3\u5b9a (dryRun={dry_run})")
    return client.post_json(
        "/sim/engine/scenario",
        {
            "taskId": task_id,
            "scenario": scenario,
            "broadcast": True,
            "requireAck": False,
            "timeoutSec": 0,
            "dryRun": dry_run,
        },
        timeout=10.0,
    )


def wait_all_distances_report(
    client: HttpClient,
    *,
    task_id: str,
    timeout_sec: float,
) -> dict[str, Any]:
    event = client.post_json(
        "/sim/engine/event/wait",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_carla",
            "commandType": "allDistancesReport",
            "timeoutSec": timeout_sec,
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )
    response = event.get("response") if isinstance(event.get("response"), dict) else event
    log_receipt("LJ-ENGINE_carla", response)
    return normalize_distance_report(response)


def normalize_distance_report(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("allDistancesReport \u5fc5\u987b\u662f JSON object")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError(f"allDistancesReport.data \u5fc5\u987b\u662f\u6570\u7ec4: {payload}")
    normalized_data: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"allDistancesReport.data item \u5fc5\u987b\u662f object: {item}")
        car_id = str(item.get("autocarId") or item.get("autoCarId") or item.get("carId") or "")
        if not car_id:
            raise ValueError(f"allDistancesReport item \u7f3a\u5c11 autocarId: {item}")
        distances = item.get("distances")
        if not isinstance(distances, dict):
            raise ValueError(f"{car_id}.distances \u5fc5\u987b\u662f object")
        normalized_data.append(
            {
                "autocarId": car_id,
                "distances": {str(point_id): float(distance) for point_id, distance in distances.items()},
            }
        )
    return {
        "commandType": payload.get("commandType") or "allDistancesReport",
        "taskId": payload.get("taskId"),
        "data": normalized_data,
    }


def build_multicar_plan(
    *,
    task_id: str,
    allocation: dict[str, Any],
    task_points: list[dict[str, Any]],
) -> dict[str, Any]:
    point_by_id = {str(point["id"]): point for point in task_points}
    actions: list[dict[str, Any]] = []
    for assignment in allocation["assignments"]:
        ordered_ids = [str(point_id) for point_id in assignment.get("orderedTaskPointIds") or []]
        location_array = [
            {
                "taskPointId": point_id,
                "lon": point_by_id[point_id]["lon"],
                "lat": point_by_id[point_id]["lat"],
                "alt": point_by_id[point_id].get("alt", 0.0),
            }
            for point_id in ordered_ids
        ]
        actions.append(
            {
                "autocarId": assignment["autocarId"],
                "instructionType": "multiTaskRoute",
                "taskPointIds": ordered_ids,
                "locationArray": location_array,
            }
        )
    return {
        "commandType": "multiTaskPlan",
        "taskId": task_id,
        "autocarAction": actions,
    }


def build_car_point_command(
    *,
    task_id: str,
    car_id: str,
    point: dict[str, Any],
) -> dict[str, Any]:
    point_id = str(point["id"])
    point_num: int | str = int(point_id) if point_id.isdigit() else point_id
    return {
        "commandType": "executeAction",
        "taskId": task_id,
        "autocarAction": [
            {
                "autocarId": car_id,
                "instructionType": "setDestination",
                "pointNum": point_num,
                "location": {
                    "lon": float(point["lon"]),
                    "lat": float(point["lat"]),
                    "alt": float(point.get("alt") or 0.0),
                },
            }
        ],
    }


def dispatch_car_point(
    client: HttpClient,
    *,
    command: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    
    for action in command.get("autocarAction") or []:
        car_id = str(action.get("autocarId") or "car")
        label = f"{action.get('instructionType')}  {brief_cmd(action.get('location') or action)}".strip()
        log_cmd(car_id, label)
    return client.post_json(
        "/sim/engine/carla/action",
        {
            **command,
            "engineSessionKey": "LJ-ENGINE_carla",
            "broadcast": False,
            "requireAck": False,
            "dryRun": dry_run,
        },
        timeout=10.0,
    )


def wait_car_completion_event(
    client: HttpClient,
    *,
    task_id: str,
    timeout_sec: float,
) -> dict[str, Any]:
    return client.post_json(
        "/sim/engine/event/wait",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_carla",
            "commandType": "executionCompleted",
            "timeoutSec": timeout_sec,
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )


def event_response(event: dict[str, Any]) -> dict[str, Any]:
    response = event.get("response")
    return response if isinstance(response, dict) else event


def extract_car_completion_event(event: dict[str, Any]) -> dict[str, Any]:
    response = event_response(event)
    car_id = _first_present(response, "autocarId", "autoCarId", "carID", "carId")
    point_num = _first_present(response, "pointNum", "taskPointId", "pointIndex", "point_index")
    return {
        "autocarId": str(car_id) if car_id is not None else "",
        "pointNum": str(point_num) if point_num is not None else "",
        "location": response.get("location") if isinstance(response.get("location"), dict) else None,
        "raw": response,
    }


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) is not None:
            return payload[key]
    return None


def assignment_queues(allocation: dict[str, Any]) -> dict[str, list[str]]:
    queues: dict[str, list[str]] = {}
    for assignment in allocation["assignments"]:
        queues[str(assignment["autocarId"])] = [
            str(point_id) for point_id in assignment.get("orderedTaskPointIds") or []
        ]
    return queues


def dispatch_point_queues(
    client: HttpClient,
    *,
    task_id: str,
    allocation: dict[str, Any],
    task_points: list[dict[str, Any]],
    dry_run: bool,
    completion_timeout_sec: float,
) -> dict[str, Any]:
    point_by_id = {str(point["id"]): point for point in task_points}
    queues = assignment_queues(allocation)
    pending = {car_id: list(point_ids) for car_id, point_ids in queues.items()}
    active: dict[str, str] = {}
    dispatch_log: list[dict[str, Any]] = []
    completion_events: list[dict[str, Any]] = []
    ignored_completion_events: list[dict[str, Any]] = []

    def send_next(car_id: str) -> None:
        if not pending.get(car_id):
            active.pop(car_id, None)
            return
        point_id = pending[car_id].pop(0)
        point = point_by_id[point_id]
        command = build_car_point_command(task_id=task_id, car_id=car_id, point=point)
        response = dispatch_car_point(client, command=command, dry_run=dry_run)
        active[car_id] = point_id
        dispatch_log.append(
            {
                "autocarId": car_id,
                "taskPointId": point_id,
                "command": command,
                "response": response,
            }
        )

    for car_id in car_ids():
        send_next(car_id)

    if dry_run:
        return {
            "status": "dry_run",
            "queues": queues,
            "dispatch_log": dispatch_log,
            "completion_events": completion_events,
            "ignored_completion_events": ignored_completion_events,
        }

    while active:
        raw_event = wait_car_completion_event(
            client,
            task_id=task_id,
            timeout_sec=completion_timeout_sec,
        )
        event = extract_car_completion_event(raw_event)
        log_receipt(event["autocarId"] or "car", event)
        car_id = event["autocarId"]
        if car_id not in active:
            ignored_completion_events.append({"event": event, "raw_event": raw_event})
            continue
        completed_point_id = active.pop(car_id)
        completion_events.append(
            {
                "autocarId": car_id,
                "completedTaskPointId": completed_point_id,
                "reportedPointNum": event["pointNum"],
                "event": event,
                "raw_event": raw_event,
            }
        )
        send_next(car_id)

    return {
        "status": "completed",
        "queues": queues,
        "dispatch_log": dispatch_log,
        "completion_events": completion_events,
        "ignored_completion_events": ignored_completion_events,
    }


def run_case(
    *,
    backend_url: str,
    task_id: str,
    task_points_file: Path | None,
    distance_report_file: Path | None,
    distance_timeout_sec: float,
    completion_timeout_sec: float,
    skip_session_check: bool,
    dry_run: bool,
    dispatch_actions: bool,
) -> dict[str, Any]:
    task_id = task_id or make_task_id(prefix="multicars")
    client = HttpClient(backend_url)
    task_points = load_task_points(task_points_file)
    scenario = build_scenario_payload(task_id, task_points)
    required_sessions = ["LJ-ENGINE_carla"]
    sessions = {"skipped": True} if skip_session_check or dry_run else ensure_sessions(client, required_sessions)

    scenario_response = None
    if distance_report_file is None:
        if not dry_run:
            try:
                send_task_complete(client, task_id=task_id)  
                print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u5148\u53d1 complete \u590d\u4f4d\u5f15\u64ce (taskId={task_id})", flush=True)
            except Exception as _exc:  # noqa: BLE001
                print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u7684 complete \u5931\u8d25(\u5ffd\u7565): {_exc}", flush=True)
        scenario_response = broadcast_scenario_to_engines(
            client,
            task_id=task_id,
            scenario=scenario,
            dry_run=dry_run,
        )
        
        
        if not dry_run:
            wait_engine_ready(client, task_id=task_id, engine="carla")
    distance_report = load_distance_report(distance_report_file)
    if distance_report is None and not dry_run:
        distance_report = wait_all_distances_report(
            client,
            task_id=task_id,
            timeout_sec=distance_timeout_sec,
        )

    allocation_response = None
    multicar_plan = None
    point_dispatch = None
    if distance_report is not None:
        allocation_response = allocate_tasks_sync(
            task_id=task_id,
            cars=CAR_DEFS,
            task_points=task_points,
            distance_report=distance_report,
        )
        multicar_plan = build_multicar_plan(
            task_id=task_id,
            allocation=allocation_response["result"],
            task_points=task_points,
        )
        if dispatch_actions:
            point_dispatch = dispatch_point_queues(
                client,
                task_id=task_id,
                allocation=allocation_response["result"],
                task_points=task_points,
                dry_run=dry_run,
                completion_timeout_sec=completion_timeout_sec,
            )

    payload = {
        "status": "dry_run" if dry_run else "ok",
        "mode": "multicars_task_allocation",
        "task_id": task_id,
        "backend_url": backend_url,
        "sessions": sessions,
        "required_sessions": required_sessions,
        "scenario": scenario,
        "scenario_response": scenario_response,
        "distance_report": distance_report,
        "allocation": allocation_response,
        "multicar_plan": multicar_plan,
        "point_dispatch": point_dispatch,
        "notes": [
            "\u60f3\u5b9a\u901a\u8fc7 /sim/engine/scenario \u5e7f\u64ad\u7ed9\u6240\u6709\u5728\u7ebf LJ-ENGINE\uff1b\u8ddd\u79bb\u77e9\u9635\u4ecd\u7531 Carla \u8fd4\u56de\u3002",
            "\u5f53\u524d\u8ddd\u79bb\u77e9\u9635\u53ea\u5305\u542b\u8f66\u5230\u4efb\u52a1\u70b9\u8ddd\u79bb\uff0cLLM \u5206\u914d\u4efb\u52a1\u70b9\u5e76\u6309\u8f66\u5230\u70b9\u8ddd\u79bb\u8fd1\u4f3c\u6392\u5e8f\u3002",
            "Carla \u52a8\u4f5c\u6309\u5355\u8f66\u5355\u70b9\u9010\u6b21\u4e0b\u53d1\uff1bwayPoint \u53ea\u8bb0\u5f55\u4e3a\u9014\u7ecf\u70b9\uff0c\u540e\u7aef\u7b49\u5f85 executionCompleted \u540e\u624d\u53d1\u4e0b\u4e00\u70b9\u3002",
            "\u5982\u9700\u7cbe\u786e\u591a\u70b9\u8def\u5f84\u4f18\u5316\uff0c\u8bf7\u8ba9 Carla \u8fd4\u56de\u4efb\u52a1\u70b9\u4e4b\u95f4\u7684 pairwise distance matrix\u3002",
        ],
    }
    payload["result_path"] = str(write_result(task_id, payload))
    return payload


def write_result(task_id: str, payload: dict[str, Any]) -> Path:
    task_dir = RESULTS_DIR / safe_component(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = task_dir / f"run_case_{safe_component(task_id)}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--task-id", default="multicars_test_001")
    parser.add_argument("--task-points-file", type=Path, default=None)
    parser.add_argument("--distance-report-file", type=Path, default=None)
    parser.add_argument("--distance-timeout-sec", type=float, default=180.0,
                        help="\u7b49 carla \u8ddd\u79bb\u77e9\u9635(allDistancesReport)\u4e0a\u9650(\u79d2); \u8d85\u65f6\u5219\u672c\u8f6e\u5224\u5931\u8d25\u8fdb\u4e0b\u4e00\u8f6e, \u4e0d\u518d\u65e0\u9650\u7b49")
    parser.add_argument("--completion-timeout-sec", type=float, default=0.0, help="0 means wait indefinitely")
    parser.add_argument("--waypoint-timeout-sec", type=float, default=None, help="\u517c\u5bb9\u65e7\u53c2\u6570\uff1b\u7b49\u540c completion timeout")
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-dispatch-actions", action="store_true")
    parser.add_argument("--episodes", type=int, default=3, help="\u6b63\u5f0f\u5b9e\u9a8c\u8f6e\u6570")
    parser.add_argument(
        "--engine-restart-wait-sec",
        type=float,
        default=20.0,
        help="\u8f6e\u95f4\u91cd\u542f\u5f15\u64ce\u540e\u7684\u7b49\u5f85\u79d2\u6570",
    )
    add_backbone_args(parser)   
    args = parser.parse_args()

    log_path = setup_console_logging(RESULTS_DIR, "multicars")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)

    push_vision_override(HttpClient(args.backend_url), args)   
    episodes = max(1, args.episodes)
    summaries: list[dict[str, Any]] = []
    for ep in range(1, episodes + 1):
        episode_task_id = args.task_id if episodes == 1 else f"{args.task_id}_ep{ep}"
        print(f"\n========== [\u5b9e\u9a8c] \u7b2c {ep}/{episodes} \u8f6e (taskId={episode_task_id}) ==========", flush=True)

        
        if ep >= 2 and not args.dry_run:
            restart_engine_between_episodes(
                HttpClient(args.backend_url),
                task_id=episode_task_id,
                wait_sec=args.engine_restart_wait_sec,
            )

        try:
            result = run_case(
                backend_url=args.backend_url,
                task_id=episode_task_id,
                task_points_file=args.task_points_file,
                distance_report_file=args.distance_report_file,
                distance_timeout_sec=args.distance_timeout_sec,
                completion_timeout_sec=(
                    args.completion_timeout_sec
                    if args.waypoint_timeout_sec is None
                    else args.waypoint_timeout_sec
                ),
                skip_session_check=args.skip_session_check,
                dry_run=args.dry_run,
                dispatch_actions=not args.no_dispatch_actions,
            )
        except Exception as exc:  # noqa: BLE001
            result = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        summaries.append(
            {
                "episode": ep,
                "task_id": episode_task_id,
                "status": result.get("status"),
                "result_path": result.get("result_path"),
                "error": result.get("error"),
            }
        )
        
        if not args.dry_run:
            try:
                send_task_complete(HttpClient(args.backend_url), task_id=episode_task_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[\u5f15\u64ce] \u4e0b\u53d1 complete \u5931\u8d25(\u5ffd\u7565): {exc}", flush=True)

    print(f"\n========== [\u5b9e\u9a8c] \u5168\u90e8 {episodes} \u8f6e\u6c47\u603b ==========", flush=True)
    for item in summaries:
        line = f"  \u7b2c {item['episode']} \u8f6e | task_id={item['task_id']} | status={item['status']}"
        if item.get("result_path"):
            line += f" | result={item['result_path']}"
        if item.get("error"):
            line += f" | error={item['error']}"
        print(line, flush=True)


if __name__ == "__main__":
    main()
