"""Delivery task workflow runner.

Flow:
1. Dispatch scenario to Carla/AirSim/Go2/Image.
2. Dispatch Carla setDestination with the target lon/lat.
3. Wait for Carla's inbound carlaSendLoc event and save its locationArray.
4. Send AirSim UAV to each returned point, request a topdown photo, and wait for
   /sim/uav/deliverytask/traffic-inspect to write the LLM inspection result.
5. If a blockage is detected, report trafficJam to Carla, then wait for the next
   carlaSendLoc replanned route.
6. Repeat until all returned route points are verified clear.
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
    log_vision,
    push_vision_override,
    restart_engine_between_episodes,
    send_task_complete,
    setup_console_logging,
    wait_engine_ready,
)
from examples.deliverytask.scenario import (
    CAR_DEF,
    DEFAULT_DELIVERY_POINT,
    DOG_DEF,
    UAV_DEF,
    build_delivery_task_scenario,
)

CASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = CASE_DIR / "results"

TASK_TYPE = "deliverytask"


PUBLIC_UPLOAD_BASE_URL = "http://127.0.0.1:9909"


def _build_upload_spec(*, task_id: str, agent_id: str, agent_type: str, view_type: str,
                       analysis_type: str, step_index: int, photo_id: str,
                       extra_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """\u6784\u9020 takePhoto \u7684 uploadSpec (\u4e0e bridge/firesearch \u540c\u5951\u7ea6): \u544a\u77e5\u5f15\u64ce\u62cd\u5b8c\u56fe\u4e0a\u4f20\u5230\u54ea\u3001\u5e26\u54ea\u4e9b\u5b57\u6bb5\u3002"""
    fields: dict[str, Any] = {
        "taskId": task_id, "taskType": TASK_TYPE, "agentId": agent_id, "agentType": agent_type,
        "viewType": view_type, "analysisType": analysis_type, "stepIndex": step_index, "photoid": photo_id,
    }
    if extra_fields:
        fields.update(extra_fields)
    return {
        "url": f"{PUBLIC_UPLOAD_BASE_URL.rstrip('/')}/sim/vision/upload",
        "method": "POST", "contentType": "multipart/form-data", "fileField": "file", "fields": fields,
    }


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
            if timeout is None or timeout <= 0:
                response_context = self._opener.open(request)
            else:
                response_context = self._opener.open(request, timeout=timeout)
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


def build_scenario_payload(
    *,
    task_id: str,
    target_position: dict[str, float] | None,
    delivery_point: dict[str, float] | None,
) -> dict[str, Any]:
    spec = ScenarioSpec.from_definition(
        build_delivery_task_scenario(
            target_position=target_position,
            delivery_point=delivery_point,
        )
    )
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


def dispatch_scenario_to_engines(
    client: HttpClient,
    *,
    task_id: str,
    scenario: dict[str, Any],
    require_carla_ack: bool,
    timeout_sec: float,
) -> dict[str, Any]:
    responses: dict[str, Any] = {}
    targets = {
        "carla": ("/sim/engine/carla/scenario", require_carla_ack),
        "airsim": ("/sim/engine/airsim/scenario", False),
        "go2": ("/sim/engine/go2/scenario", False),
        "image": ("/sim/engine/image/scenario", False),
    }
    for name, (path, require_ack) in targets.items():
        log_cmd(f"LJ-ENGINE_{name}", f"\u4e0b\u53d1\u573a\u666f scenario (requireAck={require_ack})")
        responses[name] = client.post_json(
            path,
            {
                "taskId": task_id,
                "scenario": scenario,
                "requireAck": require_ack,
                "timeoutSec": timeout_sec if require_ack else 0,
            },
            timeout=None if require_ack and timeout_sec <= 0 else (timeout_sec + 5.0 if require_ack else 10.0),
        )
    return responses


def send_carla_destination(
    client: HttpClient,
    *,
    task_id: str,
    destination: dict[str, float],
) -> dict[str, Any]:
    log_cmd(CAR_DEF["code"], f"setDestination {brief_cmd(destination)}")
    return client.post_json(
        "/sim/engine/carla/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_carla",
            "broadcast": False,
            "requireAck": False,
            "autocarId": CAR_DEF["code"],
            "instructionType": "setDestination",
            "location": destination,
        },
        timeout=10.0,
    )


def wait_carla_route_points(
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
            "commandType": "carlaSendLoc",
            "timeoutSec": timeout_sec,
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )


def wait_vehicle_execution_completed(
    client: HttpClient,
    *,
    task_id: str,
    car_id: str,
    timeout_sec: float,
) -> dict[str, Any]:
    # Vehicle delivery can take much longer than the generic route-planning timeout.
    # Keep waiting until Carla reports executionCompleted.
    event = client.post_json(
        "/sim/engine/event/wait",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_carla",
            "commandType": "executionCompleted",
            "timeoutSec": 0,
        },
        timeout=None,
    )
    event_car_id = _find_first_present_by_key(event, {"carID", "carId", "carlaId", "vehicleId"})
    if event_car_id is not None and str(event_car_id) != str(car_id):
        raise RuntimeError(f"\u6536\u5230\u8f66\u8f86\u5b8c\u6210\u4e8b\u4ef6\u4f46 carID \u4e0d\u5339\u914d: expected={car_id}, actual={event_car_id}")
    return event


def wait_dog_execution_completed(
    client: HttpClient,
    *,
    task_id: str,
    dog_id: str,
    timeout_sec: float,
) -> dict[str, Any]:
    # Dog path execution can include animation and slow walking; wait until Go2 reports completion.
    event = client.post_json(
        "/sim/engine/event/wait",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_go2",
            "commandType": "executionCompleted",
            "timeoutSec": 0,
        },
        timeout=None,
    )
    event_dog_id = _find_first_present_by_key(
        event,
        {"dogID", "dogId", "unmannedDogID", "unmannedDogId", "go2Id", "ugvId"},
    )
    if event_dog_id is not None and str(event_dog_id) != str(dog_id):
        event["dog_id_warning"] = f"expected={dog_id}, actual={event_dog_id}"
    return event


def extract_route_points(payload: Any) -> list[dict[str, float]]:
    route = _find_first_list_by_key(
        payload,
        {
            "routePoints",
            "route_points",
            "waypoints",
            "points",
            "locationArray",
            "verified_route",
            "route",
        },
    )
    if not route:
        return []
    points: list[dict[str, float]] = []
    for index, item in enumerate(route, start=1):
        if isinstance(item, dict):
            x = _first_present(item, "x", "X", "lon")
            y = _first_present(item, "y", "Y", "lat")
            z = _first_present(item, "z", "Z", "alt")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            x, y = item[0], item[1]
            z = item[2] if len(item) >= 3 else None
        else:
            continue
        if x is None or y is None:
            continue
        point = {"x": float(x), "y": float(y), "point_index": index}
        if z is not None:
            point["z"] = float(z)
        points.append(point)
    return points


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) is not None:
            return payload[key]
    return None


def _find_first_list_by_key(value: Any, keys: set[str]) -> list[Any] | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, list):
                return item
        for item in value.values():
            found = _find_first_list_by_key(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_first_list_by_key(item, keys)
            if found:
                return found
    return None


def _find_first_present_by_key(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                return item
        for item in value.values():
            found = _find_first_present_by_key(item, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_first_present_by_key(item, keys)
            if found is not None:
                return found
    return None


def send_uav_takeoff(client: HttpClient, *, task_id: str, drone_id: str, height_m: float, speed: float) -> dict[str, Any]:
    log_cmd(drone_id, f"takeoff mile={height_m},speed={speed}")
    return client.post_json(
        "/sim/uav/airsim/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_airsim",
            "broadcast": False,
            "requireAck": False,
            "waitExecutionCompleted": False,
            "waitDroneId": drone_id,
            "dronesId": drone_id,
            "instructionType": "takeoff",
            "mile": height_m,
            "raw": 0,
            "speed": speed,
        },
        timeout=None,
    )


def send_uav_to_point(client: HttpClient, *, task_id: str, drone_id: str, point: dict[str, float]) -> dict[str, Any]:
    log_cmd(drone_id, f"setDestinationLoc {brief_cmd({'x': point['x'], 'y': point['y']})}")
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
            "instructionType": "setDestinationLoc",
            "actionCommand": {"x": point["x"], "y": point["y"]},
        },
        timeout=None,
    )


def request_uav_photo(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    analysis_type: str = "traffic_inspection",
    step_index: int | None = None,
    current_height_m: float | None = None,
) -> dict[str, Any]:
    effective_step_index = step_index if step_index is not None else 0
    photo_id = f"{task_id}_{drone_id}_topdown_step_{effective_step_index}"
    extra: dict[str, Any] = {}
    if current_height_m is not None:
        extra["uavHeightM"] = current_height_m
    model_item: dict[str, Any] = {
        "droneId": drone_id,
        "agentId": drone_id,
        "agentType": "uav",
        "viewType": "topdown",
        "analysisType": analysis_type,
        "photoid": photo_id,
        "uploadSpec": _build_upload_spec(
            task_id=task_id, agent_id=drone_id, agent_type="uav", view_type="topdown",
            analysis_type=analysis_type, step_index=effective_step_index, photo_id=photo_id,
            extra_fields=extra or None),
    }
    if step_index is not None:
        model_item["stepIndex"] = step_index
    if current_height_m is not None:
        model_item["uavHeightM"] = current_height_m
    log_cmd(drone_id, f"\u62cd\u7167(topdown) analysisType={analysis_type},step={effective_step_index}")
    return client.post_json(
        "/sim/engine/image/take-photo",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_image",
            "broadcast": False,
            "requireAck": False,
            "timeoutSec": 0,
            "modelIdList": [model_item],
        },
        timeout=10.0,
    )


def request_dog_front_photo(client: HttpClient, *, task_id: str, dog_id: str, step_index: int) -> dict[str, Any]:
    photo_id = f"{task_id}_{dog_id}_front_step_{step_index}"
    log_cmd(dog_id, f"\u62cd\u7167(front) analysisType=dog_target_house,step={step_index}")
    return client.post_json(
        "/sim/engine/image/take-photo",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_image",
            "broadcast": False,
            "requireAck": False,
            "timeoutSec": 0,
            "modelIdList": [
                {
                    "dogId": dog_id,
                    "agentId": dog_id,
                    "agentType": "dog",
                    "viewType": "front",
                    "analysisType": "dog_target_house",
                    "stepIndex": step_index,
                    "photoid": photo_id,
                    "uploadSpec": _build_upload_spec(
                        task_id=task_id, agent_id=dog_id, agent_type="dog", view_type="front",
                        analysis_type="dog_target_house", step_index=step_index, photo_id=photo_id),
                }
            ],
        },
        timeout=10.0,
    )


def wait_traffic_result(
    *,
    task_id: str,
    drone_id: str,
    requested_at: float,
    timeout_sec: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        candidates = find_traffic_result_candidates(
            task_id=task_id,
            drone_id=drone_id,
            requested_at=requested_at,
        )
        if candidates:
            path, payload = max(candidates, key=lambda item: item[0].stat().st_mtime)
            payload = dict(payload)
            payload["result_path"] = str(path)
            return payload
        time.sleep(0.5)
    raise RuntimeError(
        f"\u7b49\u5f85 deliverytask \u4fef\u89c6\u56fe\u8bc6\u522b\u7ed3\u679c\u8d85\u65f6: {timeout_sec:.1f}s\uff1b"
        f"taskId={task_id}, droneId={drone_id}\u3002"
        "\u8bf7\u786e\u8ba4\u6280\u672f\u90e8\u5df2\u5728\u62cd\u7167\u540e\u8c03\u7528 /sim/vision/upload\uff0c"
        "analysisType=traffic_inspection"
    )


def find_traffic_result_candidates(
    *,
    task_id: str,
    drone_id: str,
    requested_at: float,
) -> list[tuple[Path, dict[str, Any]]]:
    task_dir = RESULTS_DIR / safe_component(task_id)
    if not task_dir.exists():
        return []
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in task_dir.glob(f"uav_traffic_inspection_{safe_component(task_id)}_*.json"):
        if path.stat().st_mtime < requested_at - 1.0:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("taskId") != task_id or payload.get("droneId") != drone_id:
            continue
        candidates.append((path, payload))
    return candidates


def wait_policy_result(
    *,
    task_id: str,
    result_type: str,
    requested_at: float,
    timeout_sec: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    task_dir = RESULTS_DIR / safe_component(task_id)
    prefix = f"{result_type}_{safe_component(task_id)}_"
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
                if payload.get("taskId") == task_id and payload.get("type") == result_type:
                    candidates.append((path, payload))
        if candidates:
            path, payload = max(candidates, key=lambda item: item[0].stat().st_mtime)
            payload = dict(payload)
            payload["result_path"] = str(path)
            return payload
        time.sleep(0.5)
    raise RuntimeError(
        f"\u7b49\u5f85 {result_type} \u8bc6\u56fe\u7ed3\u679c\u8d85\u65f6: {timeout_sec:.1f}s\uff1b"
        f"taskId={task_id}\u3002\u8bf7\u786e\u8ba4\u6280\u672f\u90e8\u5df2\u8c03\u7528 /sim/vision/upload"
    )


def report_blockage_to_carla(
    client: HttpClient,
    *,
    task_id: str,
    blocked_point: dict[str, Any],
    require_ack: bool,
    timeout_sec: float,
) -> dict[str, Any]:
    log_cmd(CAR_DEF["code"], f"trafficJam \u4e0a\u62a5\u62e5\u5835\u70b9 {brief_cmd(blocked_point)}")
    return client.post_json(
        "/sim/engine/carla/traffic-jam",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_carla",
            "broadcast": False,
            "requireAck": False,
            "timeoutSec": timeout_sec,
            "locationArray": [{"x": float(blocked_point["x"]), "y": float(blocked_point["y"])}],
        },
        timeout=10.0,
    )


def dispatch_vehicle_verified_route(
    client: HttpClient,
    *,
    task_id: str,
    route_points: list[dict[str, float]],
) -> dict[str, Any]:
    log_cmd(CAR_DEF["code"], f"verifiedRoute \u4e0b\u53d1\u5df2\u6838\u9a8c\u8def\u7ebf ({len(route_points)} \u4e2a\u70b9)")
    return client.post_json(
        "/sim/engine/carla/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_carla",
            "broadcast": False,
            "requireAck": False,
            "commandType": "executeAction",
            "autocarAction": [
                {
                    "autocarId": CAR_DEF["code"],
                    "instructionType": "verifiedRoute",
                    "locationArray": [{"x": point["x"], "y": point["y"]} for point in route_points],
                }
            ],
        },
        timeout=10.0,
    )


def dispatch_dog_start_location(
    client: HttpClient,
    *,
    task_id: str,
    dog_id: str,
    start_point: dict[str, float],
) -> dict[str, Any]:
    log_cmd(dog_id, f"setStartLocation {brief_cmd({'x': start_point['x'], 'y': start_point['y']})}")
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
                    "instructionType": "setStartLocation",
                    "command": {
                        "x": float(start_point["x"]),
                        "y": float(start_point["y"]),
                    },
                }
            ],
        },
        timeout=10.0,
    )


def dispatch_dog_path_planning(
    client: HttpClient,
    *,
    task_id: str,
    dog_id: str,
    waypoints: list[dict[str, Any]],
) -> dict[str, Any]:
    dog_action: dict[str, Any] = {
        "unmannedDogId": dog_id,
        "NavigationType": "PathPlanning",
        "PathPlanning": {
            "waypoints": waypoints,
        },
    }
    log_cmd(dog_id, f"PathPlanning \u4e0b\u53d1\u673a\u5668\u72d7\u5bfc\u822a\u8def\u5f84 ({len(waypoints)} \u4e2a\u70b9)")
    return client.post_json(
        "/sim/engine/go2/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_go2",
            "broadcast": False,
            "requireAck": False,
            "unmannedDogAction": [dog_action],
        },
        timeout=10.0,
    )


def route_from_file(path: Path | None) -> list[dict[str, float]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    points = extract_route_points(payload)
    if not points:
        raise RuntimeError(f"\u8def\u7ebf\u6587\u4ef6\u91cc\u6ca1\u6709\u53ef\u89e3\u6790\u7684 routePoints/waypoints/locationArray: {path}")
    return points


def run_case(
    *,
    backend_url: str,
    task_id: str,
    route_file: Path | None,
    target_position: dict[str, float] | None,
    delivery_point: dict[str, float] | None,
    dry_run: bool,
    skip_session_check: bool,
    route_timeout_sec: float,
    photo_timeout_sec: float,
    scenario_to_carla_delay_sec: float,
    max_replans: int,
    dog_plan_height_m: float,
    dog_exit_delay_sec: float,
    takeoff_height_m: float,
    takeoff_speed: float,
) -> dict[str, Any]:
    task_id = task_id or make_task_id(prefix="deliverytask")
    client = HttpClient(backend_url)
    required_sessions = ["LJ-ENGINE_carla", "LJ-ENGINE_airsim", "LJ-ENGINE_image", "LJ-ENGINE_go2"]
    sessions = {"skipped": True} if skip_session_check else ensure_sessions(client, required_sessions)
    delivery_point = delivery_point or DEFAULT_DELIVERY_POINT
    scenario = build_scenario_payload(
        task_id=task_id,
        target_position=target_position,
        delivery_point=delivery_point,
    )
    if dry_run:
        return {
            "status": "dry_run",
            "task_id": task_id,
            "required_sessions": required_sessions,
            "scenario": scenario,
            "carla_destination_command": {
                "taskId": task_id,
                "autocarId": CAR_DEF["code"],
                "instructionType": "setDestination",
                "location": delivery_point,
            },
            "scenario_to_carla_delay_sec": scenario_to_carla_delay_sec,
            "dog_plan_height_m": dog_plan_height_m,
            "dog_exit_delay_sec": dog_exit_delay_sec,
        }
    if delivery_point is None:
        raise RuntimeError("\u5fc5\u987b\u63d0\u4f9b\u76ee\u6807\u70b9\u7ecf\u7eac\u5ea6\uff1a--delivery-lon \u548c --delivery-lat\uff0c\u6216\u5728 scenario.py \u4e2d\u914d\u7f6e DEFAULT_DELIVERY_POINT")

    try:
        send_task_complete(client, task_id=task_id)  
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u5148\u53d1 complete \u590d\u4f4d\u5f15\u64ce (taskId={task_id})", flush=True)
    except Exception as _exc:  # noqa: BLE001
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u7684 complete \u5931\u8d25(\u5ffd\u7565): {_exc}", flush=True)
    scenario_response = dispatch_scenario_to_engines(
        client,
        task_id=task_id,
        scenario=scenario,
        require_carla_ack=False,
        timeout_sec=route_timeout_sec,
    )
    
    
    wait_engine_ready(client, task_id=task_id, engine="airsim")
    route_points = route_from_file(route_file)
    if not route_points:
        if scenario_to_carla_delay_sec > 0:
            time.sleep(scenario_to_carla_delay_sec)
        carla_destination_response = send_carla_destination(
            client,
            task_id=task_id,
            destination=delivery_point,
        )
        carla_route_event = wait_carla_route_points(
            client,
            task_id=task_id,
            timeout_sec=route_timeout_sec,
        )
        route_points = extract_route_points(carla_route_event)
    else:
        carla_destination_response = None
        carla_route_event = {"source": "route_file", "path": str(route_file)}
    if not route_points:
        raise RuntimeError("Carla \u672a\u8fd4\u56de\u53ef\u89e3\u6790\u8def\u7ebf\u70b9\uff0c\u8bf7\u786e\u8ba4 carlaSendLoc \u56de\u5305\u5305\u542b locationArray")

    takeoff_response = send_uav_takeoff(
        client,
        task_id=task_id,
        drone_id=UAV_DEF["code"],
        height_m=takeoff_height_m,
        speed=takeoff_speed,
    )

    verified_route: list[dict[str, float]] = []
    blocked_reports: list[dict[str, Any]] = []
    trajectory: list[dict[str, Any]] = []
    replan_count = 0
    index = 0
    blockage_detected = False
    while index < len(route_points):
        point = route_points[index]
        route_point_index = int(point.get("point_index") or index + 1)
        action_response = send_uav_to_point(
            client,
            task_id=task_id,
            drone_id=UAV_DEF["code"],
            point=point,
        )
        requested_at = time.time()
        photo_response = request_uav_photo(
            client,
            task_id=task_id,
            drone_id=UAV_DEF["code"],
            analysis_type="traffic_inspection",
            step_index=route_point_index,
        )
        inspection = wait_traffic_result(
            task_id=task_id,
            drone_id=UAV_DEF["code"],
            requested_at=requested_at,
            timeout_sec=photo_timeout_sec,
        )
        result = inspection["result"]
        log_vision(UAV_DEF["code"], "traffic_inspection", result, waited_sec=time.time() - requested_at)
        step_record = {
            "routePointIndex": route_point_index,
            "routePoint": point,
            "action_response": action_response,
            "photo_response": photo_response,
            "inspection": inspection,
        }
        trajectory.append(step_record)
        if result.get("status") == "blocked":
            blocked_point = result.get("blocked_route_point") or point
            if isinstance(blocked_point, dict) and ("x" not in blocked_point or "y" not in blocked_point):
                blocked_point = point
            blocked_reports.append({"blocked_point": blocked_point, "inspection": inspection})
            replan_count += 1
            if replan_count > max_replans:
                raise RuntimeError(f"\u8d85\u8fc7\u6700\u5927\u91cd\u89c4\u5212\u6b21\u6570 max_replans={max_replans}")
            traffic_jam_response = report_blockage_to_carla(
                client,
                task_id=task_id,
                blocked_point=blocked_point,
                require_ack=False,
                timeout_sec=route_timeout_sec,
            )
            terminal_point = route_points[-1]
            terminal_action_response = send_uav_to_point(
                client,
                task_id=task_id,
                drone_id=UAV_DEF["code"],
                point=terminal_point,
            )
            blocked_reports[-1]["traffic_jam_response"] = traffic_jam_response
            blocked_reports[-1]["terminal_point"] = terminal_point
            blocked_reports[-1]["terminal_action_response"] = terminal_action_response
            blockage_detected = True
            break
        if result.get("status") == "clear":
            verified_route.append(point)
        index += 1

    vehicle_response = dispatch_vehicle_verified_route(client, task_id=task_id, route_points=route_points)
    car_stop_node = route_points[-1] if route_points else None
    uav_fixed_height_response = send_uav_takeoff(
        client,
        task_id=task_id,
        drone_id=UAV_DEF["code"],
        height_m=dog_plan_height_m,
        speed=takeoff_speed,
    )
    vehicle_completed_event = wait_vehicle_execution_completed(
        client,
        task_id=task_id,
        car_id=CAR_DEF["code"],
        timeout_sec=route_timeout_sec,
    )
    log_receipt(CAR_DEF["code"], vehicle_completed_event)
    dog_response = dispatch_dog_start_location(
        client,
        task_id=task_id,
        dog_id=DOG_DEF["code"],
        start_point=car_stop_node or route_points[-1],
    )
    dog_stage: dict[str, Any] = {
        "uav_fixed_height_m": dog_plan_height_m,
        "uav_fixed_height_response": uav_fixed_height_response,
        "vehicle_completed_event": vehicle_completed_event,
        "dog_start_location_response": dog_response,
        "dog_exit_delay_sec": dog_exit_delay_sec,
    }
    if dog_exit_delay_sec > 0:
        dog_stage["dog_exit_delay_started_at"] = datetime.now().isoformat()
        time.sleep(dog_exit_delay_sec)
        dog_stage["dog_exit_delay_finished_at"] = datetime.now().isoformat()

    dog_plan_requested_at = time.time()
    dog_plan_photo_response = request_uav_photo(
        client,
        task_id=task_id,
        drone_id=UAV_DEF["code"],
        analysis_type="dog_path_planning",
        step_index=1,
        current_height_m=dog_plan_height_m,
    )
    dog_plan = wait_policy_result(
        task_id=task_id,
        result_type="uav_dog_path_planning",
        requested_at=dog_plan_requested_at,
        timeout_sec=photo_timeout_sec,
    )
    dog_stage["uav_dog_path_photo_response"] = dog_plan_photo_response
    dog_stage["uav_dog_path_plan"] = dog_plan
    log_vision(UAV_DEF["code"], "dog_path_planning", dog_plan.get("result") or {}, waited_sec=time.time() - dog_plan_requested_at)
    dog_stage["final_uav_height_m"] = dog_plan_height_m
    dog_waypoints = ((dog_plan.get("result") or {}).get("waypoints") or [])
    if dog_waypoints:
        dog_path_response = dispatch_dog_path_planning(
            client,
            task_id=task_id,
            dog_id=DOG_DEF["code"],
            waypoints=dog_waypoints,
        )
        dog_stage["dog_path_response"] = dog_path_response
        dog_completed_event = wait_dog_execution_completed(
            client,
            task_id=task_id,
            dog_id=DOG_DEF["code"],
            timeout_sec=route_timeout_sec,
        )
        log_receipt(DOG_DEF["code"], dog_completed_event)
        dog_stage["dog_completed_event"] = dog_completed_event
    else:
        raise RuntimeError("UAV \u4fef\u89c6\u56fe\u672a\u751f\u6210\u673a\u5668\u72d7 PathPlanning waypoints")

    dog_verify_requested_at = time.time()
    dog_front_photo_response = request_dog_front_photo(
        client,
        task_id=task_id,
        dog_id=DOG_DEF["code"],
        step_index=1,
    )
    dog_verification = wait_policy_result(
        task_id=task_id,
        result_type="dog_target_house",
        requested_at=dog_verify_requested_at,
        timeout_sec=photo_timeout_sec,
    )
    dog_stage["dog_front_photo_response"] = dog_front_photo_response
    dog_stage["dog_verification"] = dog_verification
    log_vision(DOG_DEF["code"], "dog_target_house", dog_verification.get("result") or {}, waited_sec=time.time() - dog_verify_requested_at)
    dog_stage["mission_completed"] = bool((dog_verification.get("result") or {}).get("arrived"))
    payload = {
        "status": "ok" if dog_stage["mission_completed"] else "target_unconfirmed",
        "mode": "deliverytask_full_workflow",
        "task_id": task_id,
        "backend_url": backend_url,
        "sessions": sessions,
        "scenario_response": scenario_response,
        "scenario_to_carla_delay_sec": scenario_to_carla_delay_sec,
        "carla_destination_response": carla_destination_response,
        "carla_route_event": carla_route_event,
        "takeoff_response": takeoff_response,
        "verified_route": route_points,
        "car_stop_node": car_stop_node,
        "blockage_detected": blockage_detected,
        "blocked_reports": blocked_reports,
        "trajectory": trajectory,
        "vehicle_response": vehicle_response,
        "dog_response": dog_response,
        "dog_stage": dog_stage,
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


def _position_arg(x: float | None, y: float | None, z: float | None) -> dict[str, float] | None:
    if x is None or y is None:
        return None
    data = {"X": float(x), "Y": float(y)}
    if z is not None:
        data["Z"] = float(z)
    return data


def _geo_position_arg(lon: float | None, lat: float | None, alt: float | None) -> dict[str, float] | None:
    if lon is None or lat is None:
        return None
    data = {"lon": float(lon), "lat": float(lat)}
    if alt is not None:
        data["alt"] = float(alt)
    return data


def main() -> None:
    log_path = setup_console_logging(RESULTS_DIR, "deliverytask")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--public-upload-base-url", default=None,
                        help="\u5f15\u64ce\u62cd\u7167\u540e\u4e0a\u4f20 /sim/vision/upload \u7684\u516c\u7f51\u57fa\u5740 (\u5f15\u64ce\u9700\u80fd\u8bbf\u95ee); \u9ed8\u8ba4\u8bfb .env VISION_UPLOAD_BASE_URL, \u65e0\u5219\u56de\u9000 backend-url")
    parser.add_argument("--task-id", default="deliverytask_test_001")
    parser.add_argument("--route-file", type=Path, default=None)
    parser.add_argument("--target-x", type=float, default=None)
    parser.add_argument("--target-y", type=float, default=None)
    parser.add_argument("--target-z", type=float, default=None)
    parser.add_argument("--delivery-lon", type=float, default=None)
    parser.add_argument("--delivery-lat", type=float, default=None)
    parser.add_argument("--delivery-alt", type=float, default=None)
    parser.add_argument("--delivery-x", type=float, default=None, help="\u517c\u5bb9\u65e7\u53c2\u6570\uff0c\u7b49\u540c delivery-lon")
    parser.add_argument("--delivery-y", type=float, default=None, help="\u517c\u5bb9\u65e7\u53c2\u6570\uff0c\u7b49\u540c delivery-lat")
    parser.add_argument("--delivery-z", type=float, default=None, help="\u517c\u5bb9\u65e7\u53c2\u6570\uff0c\u7b49\u540c delivery-alt")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--route-timeout-sec", type=float, default=60.0)
    parser.add_argument("--photo-timeout-sec", type=float, default=420.0)
    parser.add_argument("--scenario-to-carla-delay-sec", type=float, default=10.0)
    parser.add_argument("--max-replans", type=int, default=5)
    parser.add_argument("--dog-plan-height-m", type=float, default=280.0)
    parser.add_argument("--dog-exit-delay-sec", type=float, default=60.0)
    parser.add_argument("--takeoff-height-m", type=float, default=100.0)
    parser.add_argument("--takeoff-speed", type=float, default=20.0)
    parser.add_argument("--episodes", type=int, default=3, help="\u6b63\u5f0f\u5b9e\u9a8c\u8f6e\u6570 (\u6bcf\u8f6e\u4f7f\u7528\u72ec\u7acb task_id)")
    parser.add_argument(
        "--engine-restart-wait-sec",
        type=float,
        default=20.0,
        help="\u8f6e\u95f4\u91cd\u542f\u5f15\u64ce\u540e\u7b49\u5f85\u5c31\u7eea\u7684\u79d2\u6570",
    )
    add_backbone_args(parser)   
    args = parser.parse_args()

    
    global PUBLIC_UPLOAD_BASE_URL
    if args.public_upload_base_url:
        PUBLIC_UPLOAD_BASE_URL = args.public_upload_base_url
    else:
        try:
            from app.core.config import get_settings  # noqa: PLC0415
            PUBLIC_UPLOAD_BASE_URL = get_settings().vision_upload_base_url or args.backend_url
        except Exception:  # noqa: BLE001
            PUBLIC_UPLOAD_BASE_URL = args.backend_url
    print(f"[\u5f15\u64ce] \u62cd\u7167\u4e0a\u4f20\u56de\u8c03: {PUBLIC_UPLOAD_BASE_URL}/sim/vision/upload (\u5f15\u64ce\u9700\u80fd\u8bbf\u95ee\u6b64\u5730\u5740)", flush=True)

    delivery_point = _geo_position_arg(
        args.delivery_lon if args.delivery_lon is not None else args.delivery_x,
        args.delivery_lat if args.delivery_lat is not None else args.delivery_y,
        args.delivery_alt if args.delivery_alt is not None else args.delivery_z,
    )
    target_position = _position_arg(args.target_x, args.target_y, args.target_z)

    
    restart_client = HttpClient(args.backend_url)
    push_vision_override(restart_client, args)   
    episodes = max(1, args.episodes)
    base_task_id = args.task_id or make_task_id(prefix="deliverytask")
    summaries: list[dict[str, Any]] = []
    exit_code = 0
    for ep in range(1, episodes + 1):
        episode_task_id = base_task_id if episodes == 1 else f"{base_task_id}_ep{ep}"
        if ep >= 2:
            restart_engine_between_episodes(
                restart_client,
                task_id=episode_task_id,
                wait_sec=args.engine_restart_wait_sec,
            )
        print(f"\n========== \u7b2c {ep}/{episodes} \u8f6e (task_id={episode_task_id}) ==========", flush=True)
        try:
            result = run_case(
                backend_url=args.backend_url,
                task_id=episode_task_id,
                route_file=args.route_file,
                target_position=target_position,
                delivery_point=delivery_point,
                dry_run=args.dry_run,
                skip_session_check=args.skip_session_check,
                route_timeout_sec=args.route_timeout_sec,
                photo_timeout_sec=args.photo_timeout_sec,
                scenario_to_carla_delay_sec=args.scenario_to_carla_delay_sec,
                max_replans=args.max_replans,
                dog_plan_height_m=args.dog_plan_height_m,
                dog_exit_delay_sec=args.dog_exit_delay_sec,
                takeoff_height_m=args.takeoff_height_m,
                takeoff_speed=args.takeoff_speed,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            summaries.append({"episode": ep, "task_id": episode_task_id, "status": result.get("status")})
            
            if not args.dry_run:
                try:
                    send_task_complete(restart_client, task_id=episode_task_id)
                except Exception as exc2:  # noqa: BLE001
                    print(f"[\u5f15\u64ce] \u4e0b\u53d1 complete \u5931\u8d25(\u5ffd\u7565): {exc2}", flush=True)
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
            summaries.append(
                {"episode": ep, "task_id": episode_task_id, "status": "failed", "error": str(exc)}
            )
            exit_code = 1

    print(f"\n========== \u591a\u8f6e\u5b9e\u9a8c\u6c47\u603b ({len(summaries)} \u8f6e) ==========", flush=True)
    for item in summaries:
        line = f"  \u7b2c {item['episode']} \u8f6e  task_id={item['task_id']}  status={item['status']}"
        if item.get("error"):
            line += f"  error={item['error']}"
        print(line, flush=True)
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
