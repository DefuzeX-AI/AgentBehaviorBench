"""Bridge fracture inspection workflow runner."""

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
from examples._log_util import (setup_console_logging, log_cmd, brief_cmd, restart_engine_between_episodes,
                                 wait_engine_ready, add_backbone_args, push_vision_override, send_task_complete,
                                 log_http_req, log_http_resp, log_http_err, log_receipt, log_vision)
from examples.bridge.scenario import UAV_DEF, build_bridge_scenario

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


def build_scenario_payload(*, task_id: str, max_steps: int) -> dict[str, Any]:
    spec = ScenarioSpec.from_definition(build_bridge_scenario(max_steps=max_steps))
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


def send_takeoff(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    height_m: float,
    speed: float,
    timeout_sec: float,
) -> dict[str, Any]:
    log_cmd(drone_id, f"takeoff  mile={height_m},speed={speed}")
    return client.post_json(
        "/sim/uav/airsim/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_airsim",
            "broadcast": False,
            "requireAck": False,
            "waitExecutionCompleted": True,
            "executionTimeoutSec": timeout_sec,
            "waitDroneId": drone_id,
            "dronesId": drone_id,
            "instructionType": "takeoff",
            "mile": height_m,
            "raw": 0,
            "speed": speed,
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )


def send_uav_move(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    instruction_type: str,
    mile: float = 0.0,
    raw: float = 0.0,
    speed: float = 20.0,
    timeout_sec: float,
) -> dict[str, Any]:
    """\u76f4\u63a5\u4e0b\u53d1\u65b9\u5411\u6307\u4ee4 (forward/left/right/stop), \u8d70 executeAction\u3002mile \u5355\u4f4d\u7c73, raw \u5355\u4f4d\u5ea6\u3002

    \u4e0e\u7528\u6237\u7ed9\u7684\u534f\u8bae\u4e00\u81f4: \u540e\u7aef\u628a\u8fd9\u6761\u6241\u5e73\u8f7d\u8377\u5f52\u4e00\u5316\u4e3a
    ``{commandType:executeAction, dronesAction:[{dronesId, instructionType, command:{mile,raw,speed}}]}``,
    \u5f15\u64ce\u6267\u884c\u5b8c\u56de executionCompleted \u56de\u6267 (\u65e0\u9700\u8ddf\u8e2a\u7edd\u5bf9\u5750\u6807, \u65e0 setDestination)\u3002
    """
    command: dict[str, Any] = {"speed": float(speed)}
    if instruction_type in ("forward", "backword", "down"):
        command["mile"] = float(mile)
    elif instruction_type in ("left", "right"):
        command["raw"] = float(raw)
    log_cmd(drone_id, f"{instruction_type}  {brief_cmd(command)}")
    return client.post_json(
        "/sim/uav/airsim/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_airsim",
            "broadcast": False,
            "requireAck": False,
            "waitExecutionCompleted": True,
            "executionTimeoutSec": timeout_sec,
            "waitDroneId": drone_id,
            "dronesId": drone_id,
            "instructionType": instruction_type,
            "mile": float(mile),
            "raw": float(raw),
            "speed": float(speed),
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )


def request_topdown_photo(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    step_index: int,
    public_upload_base_url: str,
    memo: str = "",
) -> dict[str, Any]:
    upload_url = f"{public_upload_base_url.rstrip('/')}/sim/vision/upload"
    photo_id = f"{task_id}_{drone_id}_topdown_step_{step_index}"
    upload_fields = {
        "taskId": task_id,
        "taskType": "bridge",
        "agentId": drone_id,
        "agentType": "uav",
        "viewType": "topdown",
        "analysisType": "bridge_inspection",
        "stepIndex": step_index,
        "photoid": photo_id,
        "topdownLengthM": 400,
        "topdownWidthM": 300,
        "subtaskIndex": 0,
        "memo": memo,
    }
    log_cmd(drone_id, f"take-photo topdown step={step_index}")
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


def request_front_photo(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    step_index: int,
    public_upload_base_url: str,
    memo: str = "",
) -> dict[str, Any]:
    """\u62cd\u4e00\u5f20**\u524d\u89c6\u56fe** (viewType=front, analysisType=bridge_front): \u6865\u4e0d\u5728\u4fef\u89c6\u753b\u9762\u65f6\u7528\u5b83\u5224\u671d\u6d77\u65b9\u5411\u3002"""
    upload_url = f"{public_upload_base_url.rstrip('/')}/sim/vision/upload"
    photo_id = f"{task_id}_{drone_id}_front_step_{step_index}"
    upload_fields = {
        "taskId": task_id,
        "taskType": "bridge",
        "agentId": drone_id,
        "agentType": "uav",
        "viewType": "front",
        "analysisType": "bridge_front",
        "stepIndex": step_index,
        "photoid": photo_id,
        "subtaskIndex": 0,
        "memo": memo,
    }
    log_cmd(drone_id, f"take-photo front step={step_index}")
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
                    "viewType": "front",
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


def report_bridge_result(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    result: dict[str, Any],
    final_status: str,
) -> dict[str, Any]:
    command = {
        "commandType": "bridgeInspectionResult",
        "taskId": task_id,
        "droneId": drone_id,
        "status": final_status,
        "result": result,
    }
    responses: dict[str, Any] = {}
    for name, session_key in {
        "airsim": "LJ-ENGINE_airsim",
        "image": "LJ-ENGINE_image",
    }.items():
        log_cmd(session_key, f"command bridgeInspectionResult status={final_status}")
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


def wait_bridge_result(
    *,
    task_id: str,
    drone_id: str,
    step_index: int,
    requested_at: float,
    timeout_sec: float,
    analysis_type: str = "bridge_inspection",
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    task_dir = RESULTS_DIR / safe_component(task_id)
    prefix = f"{analysis_type}_{safe_component(task_id)}_"
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
        f"\u7b49\u5f85 bridge \u8bc6\u522b\u7ed3\u679c\u8d85\u65f6: {timeout_sec:.1f}s\uff1b"
        f"taskId={task_id}, droneId={drone_id}, stepIndex={step_index}, analysisType={analysis_type}\u3002"
        f"\u8bf7\u786e\u8ba4\u6280\u672f\u90e8\u5df2\u5728\u62cd\u7167\u540e\u8c03\u7528 /sim/vision/upload\uff0canalysisType={analysis_type}"
    )


def wait_bridge_adjudication(
    client: HttpClient,
    *,
    task_id: str,
    drone_id: str,
    timeout_sec: float,
) -> dict[str, Any] | None:
    """\u7b49\u5f15\u64ce\u7684\u5230\u70b9\u88c1\u51b3 ``reachTargetPoint`` \u2014\u2014 **\u662f\u5426\u627e\u5230\u65ad\u6865\u4ee5\u5f15\u64ce\u88c1\u51b3\u4e3a\u51c6**(\u5bf9\u6807\u591a\u667a\u80fd\u4f53\u4efb\u52a1)\u3002

    \u5f15\u64ce\u5728\u65e0\u4eba\u673a\u62b5\u8fd1\u65ad\u6865\u76ee\u6807\u70b9\u65f6\u4e0b\u53d1::

        {droneID, commandType:"reachTargetPoint",
         judgment:{reached:true, targetPoint:{X,Y}, distance_m, timestamp},
         position:{x,y}}

    \u547d\u4e2d reached=true \u5373\u8fd4\u56de {reached, distance_m, target_point, position, raw}; \u8d85\u65f6\u672a\u89c1\u8fd4\u56de None; \u975e\u8d85\u65f6\u5f02\u5e38\u7167\u629b\u3002
    """
    try:
        event = client.post_json(
            "/sim/engine/event/wait",
            {
                "taskId": task_id,
                "engineSessionKey": "LJ-ENGINE_airsim",
                "commandTypes": ["reachTargetPoint"],
                "timeoutSec": timeout_sec,
                "filters": {"taskId": task_id},
            },
            timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
        )
    except RuntimeError as exc:
        if "\u8d85\u65f6" in str(exc) or "timeout" in str(exc).lower():
            return None
        raise
    resp = event.get("response") if isinstance(event.get("response"), dict) else event
    if not isinstance(resp, dict) or str(resp.get("commandType")) != "reachTargetPoint":
        return None
    judgment = resp.get("judgment") if isinstance(resp.get("judgment"), dict) else {}
    if not bool(judgment.get("reached")):
        return None
    return {
        "reached": True,
        "distance_m": judgment.get("distance_m"),
        "target_point": judgment.get("targetPoint"),
        "position": resp.get("position"),
        "raw": resp,
    }


def _parse_yaw(response: Any) -> float | None:
    """\u4ece\u65e0\u4eba\u673a\u6307\u4ee4\u56de\u6267\u91cc\u9012\u5f52\u53d6\u6700\u65b0\u822a\u5411\u89d2 yaw(\u5ea6); \u53d6\u4e0d\u5230\u8fd4\u56de None (\u8c03\u7528\u65b9\u56de\u9000\u822a\u4f4d\u63a8\u7b97)\u3002"""
    stack: list[Any] = [response]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            pos = cur.get("position")
            if isinstance(pos, dict) and pos.get("yaw") is not None:
                try:
                    return float(pos.get("yaw"))
                except (TypeError, ValueError):
                    pass
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def run_case(
    *,
    backend_url: str,
    task_id: str,
    drone_id: str,
    dry_run: bool,
    skip_session_check: bool,
    max_steps: int,
    takeoff_height_m: float,
    takeoff_speed: float,
    action_timeout_sec: float,
    photo_timeout_sec: float,
    public_upload_base_url: str,
    move_speed: float,
    max_forward_m: float,
    front_forward_m: float,
    front_turn_deg: float,
    lost_patience: int,
    adj_check_sec: float,
    adj_final_sec: float,
    max_llm_calls: int,
    max_turn_deg: float,
    max_consecutive_turns: int,
) -> dict[str, Any]:
    task_id = task_id or make_task_id(prefix="bridge")
    log_path = setup_console_logging(RESULTS_DIR, "bridge")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)
    client = HttpClient(backend_url)
    required_sessions = ["LJ-ENGINE_airsim", "LJ-ENGINE_image"]
    sessions = {"skipped": True} if skip_session_check else ensure_sessions(client, required_sessions)
    scenario = build_scenario_payload(task_id=task_id, max_steps=max_steps)
    if dry_run:
        return {
            "status": "dry_run",
            "task_id": task_id,
            "drone_id": drone_id,
            "required_sessions": required_sessions,
            "scenario": scenario,
            "takeoff": {
                "height_m": takeoff_height_m,
                "speed": takeoff_speed,
            },
        }

    
    try:
        send_task_complete(client, task_id=task_id)
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u5148\u53d1 complete \u590d\u4f4d\u5f15\u64ce (taskId={task_id})", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u7684 complete \u5931\u8d25(\u5ffd\u7565): {exc}", flush=True)
    scenario_response = dispatch_scenario(client, task_id=task_id, scenario=scenario)
    wait_engine_ready(client, task_id=task_id, engine="airsim")
    takeoff_response = send_takeoff(
        client,
        task_id=task_id,
        drone_id=drone_id,
        height_m=takeoff_height_m,
        speed=takeoff_speed,
        timeout_sec=action_timeout_sec,
    )
    log_receipt(drone_id, takeoff_response)

    
    heading_deg: float = float(UAV_DEF["start"].get("yaw", 0.0) or 0.0)
    tk_yaw = _parse_yaw(takeoff_response)
    if tk_yaw is not None:
        heading_deg = tk_yaw
    recent_actions: list[str] = []          
    scan_dir = "right"                       
    scan_accum_deg: float = 0.0              
    last_seen_dir = "unknown"                
    llm_calls = 0                            
    print(f"[\u65e0\u4eba\u673a] {drone_id} \u8d77\u98de\u5b8c\u6210 \u9ad8\u5ea6 {takeoff_height_m}m, \u521d\u59cb\u822a\u5411 yaw={heading_deg:.0f}\u00b0 \u2192 \u76f4\u63a5\u7528\u65b9\u5411\u6307\u4ee4\u5de1\u68c0", flush=True)

    def _apply_move(response: Any, *, instr: str, raw: float = 0.0, mile: float = 0.0) -> None:
        """\u4f9d\u636e\u56de\u6267/\u822a\u4f4d\u63a8\u7b97\u66f4\u65b0\u822a\u5411 heading + \u8ffd\u52a0\u52a8\u4f5c\u8bb0\u5fc6\u3002left \u51cf\u89d2, right \u52a0\u89d2 (\u56de\u6267 yaw \u4f18\u5148)\u3002"""
        nonlocal heading_deg
        y = _parse_yaw(response)
        if y is not None:
            heading_deg = y
        elif instr == "left":
            heading_deg = (heading_deg - raw) % 360.0
        elif instr == "right":
            heading_deg = (heading_deg + raw) % 360.0
        if instr in ("left", "right"):
            recent_actions.append(f"{instr} {raw:.0f}deg")
        elif instr == "forward":
            recent_actions.append(f"forward {mile:.0f}m")
        else:
            recent_actions.append(instr)
        del recent_actions[:-6]              

    def _memo() -> str:
        """\u7ed9\u5927\u6a21\u578b\u7684\u98de\u884c\u8bb0\u5fc6\u4e32: \u5f53\u524d\u822a\u5411 + \u6700\u8fd1\u52a8\u4f5c + \u641c\u7d22\u626b\u63cf\u8fdb\u5ea6 + \u6865/\u6d77\u6700\u8fd1\u65b9\u4f4d\u3002"""
        acts = "; ".join(recent_actions) or "none"
        return (f"current UAV heading yaw={heading_deg:.0f} deg; recent actions (old->new): {acts}; "
                f"while searching you have rotated ~{scan_accum_deg:.0f} deg consistently to the {scan_dir} "
                f"(keep turning the SAME way, do not reverse); bridge/sea last seen toward: {last_seen_dir}; "
                f"vision-model calls used: {llm_calls}/{max_llm_calls}.")

    consecutive_turns = 0          
    last_turn_dir: str | None = None

    def _run_topdown_action(result_obj: dict[str, Any]) -> dict[str, Any]:
        """\u6865\u53ef\u89c1\u65f6\u6267\u884c\u52a8\u4f5c: **\u4f18\u5148\u6cbf\u6865\u524d\u8fdb**, \u8f6c\u5411\u53ea\u505a\u5c0f\u89d2\u5ea6\u5bf9\u51c6; \u68c0\u6d4b\u5230\u539f\u5730\u6765\u56de/\u8fde\u7eed\u8f6c \u2192 \u5f3a\u5236\u524d\u8fdb (\u53cd\u6b7b\u9501)\u3002"""
        nonlocal consecutive_turns, last_turn_dir
        it = str(result_obj.get("instructionType") or "forward")
        mile = float(result_obj.get("mile") or 0.0)
        raw = float(result_obj.get("raw") or 0.0)
        speed = min(30.0, max(15.0, float(result_obj.get("speed") or move_speed)))
        if it in ("left", "right"):
            reversal = last_turn_dir is not None and it != last_turn_dir
            if consecutive_turns >= max_consecutive_turns or reversal:
                why = "\u6765\u56de\u53cd\u5411\u8f6c" if reversal else f"\u8fde\u7eed\u8f6c{consecutive_turns}\u6b21"
                print(f"[\u65e0\u4eba\u673a] {drone_id} \u68c0\u6d4b\u5230{why}(\u7591\u4f3c\u6b7b\u9501) \u2192 \u4e0d\u518d\u8f6c, \u5f3a\u5236\u6cbf\u6865\u524d\u8fdb\u5de1\u68c0", flush=True)
                it = "forward"
        if it == "forward":
            consecutive_turns = 0
            last_turn_dir = None
            if mile <= 0.0:
                mile = min(front_forward_m, max_forward_m)
            mile = min(mile, max_forward_m)              
            resp = send_uav_move(client, task_id=task_id, drone_id=drone_id, instruction_type="forward",
                                 mile=mile, speed=speed, timeout_sec=action_timeout_sec)
            _apply_move(resp, instr="forward", mile=mile)
            return resp
        if it in ("left", "right"):
            consecutive_turns += 1
            last_turn_dir = it
            raw = min(max_turn_deg, max(1.0, raw))       
            resp = send_uav_move(client, task_id=task_id, drone_id=drone_id, instruction_type=it,
                                 raw=raw, speed=speed, timeout_sec=action_timeout_sec)
            _apply_move(resp, instr=it, raw=raw)
            return resp
        
        resp = send_uav_move(client, task_id=task_id, drone_id=drone_id, instruction_type="stop",
                             speed=speed, timeout_sec=action_timeout_sec)
        _apply_move(resp, instr="stop")
        return resp

    trajectory: list[dict[str, Any]] = []
    final_status = "max_steps_reached"
    final_result: dict[str, Any] | None = None
    adjudication: dict[str, Any] | None = None
    not_visible_streak = 0        

    def _finish_reached(step_record: dict[str, Any], adj: dict[str, Any], result_obj: dict[str, Any]) -> None:
        """\u5f15\u64ce reachTargetPoint \u88c1\u51b3\u5230\u70b9 = \u627e\u5230\u65ad\u6865, \u6536\u5c3e\u4e0a\u62a5 (\u5f15\u64ce\u6743\u5a01)\u3002"""
        nonlocal final_status, final_result, adjudication
        final_status = "completed"
        adjudication = adj
        final_result = {"status": "completed", "reachTargetPoint": adj, "vlm": result_obj}
        d = adj.get("distance_m")
        print(f"[\u65e0\u4eba\u673a] {drone_id} \u5f15\u64ce\u88c1\u51b3 reachTargetPoint reached=true "
              f"distance_m={d} \u2192 \u627e\u5230\u65ad\u6865, \u4efb\u52a1\u6210\u529f", flush=True)
        step_record["adjudication"] = adj
        step_record["report_response"] = report_bridge_result(
            client, task_id=task_id, drone_id=drone_id, result=final_result, final_status=final_status)

    for step_index in range(1, max_steps + 1):
        
        if llm_calls >= max_llm_calls:
            final_status = "failed"
            final_result = {"status": "failed",
                            "reason": f"exceeded {max_llm_calls} vision-model calls without locating the bridge break"}
            print(f"[\u65e0\u4eba\u673a] {drone_id} \u8bc6\u56fe\u5df2\u8fbe {llm_calls}/{max_llm_calls} \u6b21\u4ecd\u672a\u627e\u5230\u65ad\u6865 \u2192 \u5224\u5b9a\u5931\u8d25", flush=True)
            report_bridge_result(client, task_id=task_id, drone_id=drone_id,
                                 result=final_result, final_status="failed")
            break

        requested_at = time.time()
        photo_response = request_topdown_photo(
            client,
            task_id=task_id,
            drone_id=drone_id,
            step_index=step_index,
            public_upload_base_url=public_upload_base_url,
            memo=_memo(),
        )
        analysis = wait_bridge_result(
            task_id=task_id,
            drone_id=drone_id,
            step_index=step_index,
            requested_at=requested_at,
            timeout_sec=photo_timeout_sec,
        )
        llm_calls += 1
        result = analysis["result"]
        log_vision(drone_id, "bridge_inspection", result)
        step_record: dict[str, Any] = {
            "stepIndex": step_index,
            "heading_deg": round(heading_deg, 1),
            "llm_calls": llm_calls,
            "photo_response": photo_response,
            "analysis": analysis,
        }
        trajectory.append(step_record)

        
        if result.get("status") == "completed" or result.get("fracture_detected"):
            adj = wait_bridge_adjudication(client, task_id=task_id, drone_id=drone_id, timeout_sec=adj_final_sec)
            if adj:
                _finish_reached(step_record, adj, result)
                break
            nudge = min(front_forward_m, 50.0)
            print(f"[\u65e0\u4eba\u673a] {drone_id} VLM \u62a5\u65ad\u88c2\u4f46\u5f15\u64ce\u672a\u88c1\u51b3\u5230\u70b9 \u2192 \u524d\u8fdb {nudge:.0f}m \u9760\u8fd1\u540e\u590d\u6838", flush=True)
            move = send_uav_move(client, task_id=task_id, drone_id=drone_id, instruction_type="forward",
                                 mile=nudge, speed=move_speed, timeout_sec=action_timeout_sec)
            _apply_move(move, instr="forward", mile=nudge)
            step_record["action_response"] = move
            log_receipt(drone_id, move)
            continue

        
        if result.get("bridge_visible") and result.get("status") in {"approach", "inspect"}:
            not_visible_streak = 0
            scan_accum_deg = 0.0
            last_seen_dir = "under/ahead (top-down)"
            it = str(result.get("instructionType") or "forward")
            print(f"[\u65e0\u4eba\u673a] {drone_id} \u6865\u53ef\u89c1({result.get('status')}) yaw={heading_deg:.0f}\u00b0 \u2192 \u6a21\u578b\u5efa\u8bae {it} "
                  f"mile={result.get('mile')} raw={result.get('raw')} (\u8f6c\u5411\u5c06\u622a\u65ad\u5230\u2264{max_turn_deg:.0f}\u00b0)", flush=True)
            action_response = _run_topdown_action(result)
            step_record["action_response"] = action_response
            log_receipt(drone_id, action_response)
            
            adj = wait_bridge_adjudication(client, task_id=task_id, drone_id=drone_id, timeout_sec=adj_check_sec)
            if adj:
                _finish_reached(step_record, adj, result)
                break
            continue

        
        not_visible_streak += 1
        front: dict[str, Any] = {}
        try:
            front_req_at = time.time()
            front_photo = request_front_photo(
                client,
                task_id=task_id,
                drone_id=drone_id,
                step_index=step_index,
                public_upload_base_url=public_upload_base_url,
                memo=_memo(),
            )
            front_analysis = wait_bridge_result(
                task_id=task_id,
                drone_id=drone_id,
                step_index=step_index,
                requested_at=front_req_at,
                timeout_sec=photo_timeout_sec,
                analysis_type="bridge_front",
            )
            llm_calls += 1
            front = front_analysis["result"]
            log_vision(drone_id, "bridge_front", front)
            step_record["front_photo_response"] = front_photo
            step_record["front_analysis"] = front_analysis
        except Exception as exc:  # noqa: BLE001
            print(f"[\u65e0\u4eba\u673a] {drone_id} \u524d\u89c6\u8bc6\u56fe\u5931\u8d25(\u6309\u770b\u4e0d\u5230\u5904\u7406\u2192\u8f6c\u5411\u626b\u63cf): {exc}", flush=True)
            step_record["front_error"] = str(exc)
        bearing = str(front.get("bearing") or "center").strip().lower()
        front_visible = bool(front.get("visible"))
        if front_visible and bearing in ("left", "right"):
            
            scan_accum_deg = 0.0
            last_seen_dir = bearing
            move = send_uav_move(client, task_id=task_id, drone_id=drone_id, instruction_type=bearing,
                                 raw=front_turn_deg, speed=move_speed, timeout_sec=action_timeout_sec)
            _apply_move(move, instr=bearing, raw=front_turn_deg)
            how = f"\u770b\u5230\u6d77/\u6865\u5728{bearing} \u2192 \u8f6c\u5411\u5bf9\u51c6"
        elif front_visible:
            
            scan_accum_deg = 0.0
            last_seen_dir = "center"
            move = send_uav_move(client, task_id=task_id, drone_id=drone_id, instruction_type="forward",
                                 mile=front_forward_m, speed=move_speed, timeout_sec=action_timeout_sec)
            _apply_move(move, instr="forward", mile=front_forward_m)
            how = "\u770b\u5230\u6d77/\u6865\u5728\u6b63\u524d\u65b9 \u2192 \u524d\u8fdb\u9760\u62e2"
        else:
            
            move = send_uav_move(client, task_id=task_id, drone_id=drone_id, instruction_type=scan_dir,
                                 raw=front_turn_deg, speed=move_speed, timeout_sec=action_timeout_sec)
            _apply_move(move, instr=scan_dir, raw=front_turn_deg)
            scan_accum_deg += front_turn_deg
            how = f"\u770b\u4e0d\u5230\u6d77/\u6865 \u2192 \u539f\u5730\u671d{scan_dir}\u8f6c {front_turn_deg:.0f}\u00b0 \u626b\u63cf(\u7d2f\u8ba1{scan_accum_deg:.0f}\u00b0)"
        print(f"[\u65e0\u4eba\u673a] {drone_id} \u6865\u4e0d\u53ef\u89c1(\u7b2c{not_visible_streak}\u6b21) yaw={heading_deg:.0f}\u00b0 \u2192 "
              f"\u524d\u89c6 visible={front_visible} bearing={bearing} \u2192 {how}", flush=True)
        step_record["action_response"] = move
        log_receipt(drone_id, move)
        
        adj = wait_bridge_adjudication(client, task_id=task_id, drone_id=drone_id, timeout_sec=adj_check_sec)
        if adj:
            _finish_reached(step_record, adj, result)
            break

    
    try:
        send_task_complete(client, task_id=task_id)
        print(f"[\u5f15\u64ce] \u672c\u8f6e\u7ed3\u675f \u2192 \u5df2\u4e0b\u53d1 complete (taskId={task_id}), \u5f15\u64ce\u5c06\u590d\u4f4d\u5f85\u4e0b\u4e00\u8f6e\u5c31\u7eea", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[\u5f15\u64ce] \u4e0b\u53d1 complete \u5931\u8d25(\u5ffd\u7565): {exc}", flush=True)

    payload = {
        "status": final_status,
        "mode": "bridge_fracture_inspection",
        "task_id": task_id,
        "drone_id": drone_id,
        "backend_url": backend_url,
        "public_upload_base_url": public_upload_base_url,
        "sessions": sessions,
        "scenario_response": scenario_response,
        "takeoff_response": takeoff_response,
        "final_result": final_result,
        "adjudication": adjudication,
        "steps": len(trajectory),
        "max_steps": max_steps,
        "trajectory": trajectory,
        "completed_at": datetime.now().isoformat(),
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
    parser.add_argument("--task-id", default="bridge_test_001")
    parser.add_argument("--drone-id", default=UAV_DEF["code"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--takeoff-height-m", type=float, default=200.0)
    parser.add_argument("--takeoff-speed", type=float, default=20.0)
    parser.add_argument("--move-speed", type=float, default=20.0, help="\u98de\u884c\u901f\u5ea6(15-30)")
    parser.add_argument("--max-forward-m", type=float, default=150.0,
                        help="\u5355\u6b65 forward \u524d\u8fdb\u4e0a\u9650(\u7c73), \u9632\u5355\u6b65\u8fc7\u51b2")
    parser.add_argument("--front-forward-m", type=float, default=100.0,
                        help="\u6865\u4e0d\u53ef\u89c1\u65f6\u524d\u89c6\u671d\u6d77\u65b9\u5411\u524d\u8fdb\u7684\u5355\u6b65\u8ddd\u79bb(\u7c73)")
    parser.add_argument("--front-turn-deg", type=float, default=25.0,
                        help="\u6865\u4e0d\u53ef\u89c1\u65f6\u8f6c\u5411\u641c\u7d22/\u5bf9\u51c6\u7684\u5355\u6b65\u89d2\u5ea6(\u5ea6); \u4e5f\u662f\u539f\u5730\u626b\u63cf\u7684\u6b65\u8fdb\u89d2")
    parser.add_argument("--max-turn-deg", type=float, default=25.0,
                        help="\u6865\u53ef\u89c1\u65f6\u5355\u6b21\u8f6c\u5411\u7684\u6700\u5927\u89d2\u5ea6(\u5ea6), \u522b\u592a\u5927; \u6a21\u578b\u7ed9\u7684\u5927\u89d2\u5ea6\u4f1a\u88ab\u622a\u65ad\u5230\u6b64\u503c")
    parser.add_argument("--max-consecutive-turns", type=int, default=2,
                        help="\u6865\u53ef\u89c1\u65f6\u8fde\u7eed\u8f6c\u5411(\u4e0d\u524d\u8fdb)\u7684\u6700\u5927\u6b21\u6570, \u8d85\u8fc7\u6216\u6765\u56de\u53cd\u5411\u8f6c\u5373\u5f3a\u5236\u524d\u8fdb(\u53cd\u6b7b\u9501)")
    parser.add_argument("--lost-patience", type=int, default=4,
                        help="(\u4fdd\u7559)\u4fef\u89c6+\u524d\u89c6\u8fde\u7eed\u770b\u4e0d\u5230\u6865\u7684\u6b65\u6570\u9608\u503c; \u73b0\u5728\u7ec8\u6b62\u4ee5 --max-llm-calls \u4e3a\u51c6")
    parser.add_argument("--max-llm-calls", type=int, default=50,
                        help="\u8bc6\u56fe\u5927\u6a21\u578b\u8c03\u7528\u6b21\u6570\u4e0a\u9650, \u8d85\u8fc7\u4ecd\u6ca1\u627e\u5230\u65ad\u6865\u5373\u5224 failed \u5e76\u8fdb\u5165\u4e0b\u4e00\u8f6e")
    parser.add_argument("--adj-check-sec", type=float, default=8.0,
                        help="\u6bcf\u6b65\u79fb\u52a8\u540e\u8f6e\u8be2\u5f15\u64ce reachTargetPoint \u5230\u70b9\u88c1\u51b3\u7684\u77ed\u8d85\u65f6(\u79d2)")
    parser.add_argument("--adj-final-sec", type=float, default=90.0,
                        help="VLM \u62a5\u65ad\u88c2\u65f6\u7b49\u5f85\u5f15\u64ce reachTargetPoint \u88c1\u51b3\u7684\u8f83\u957f\u8d85\u65f6(\u79d2)")
    parser.add_argument("--action-timeout-sec", type=float, default=0.0)
    parser.add_argument("--photo-timeout-sec", type=float, default=420.0)
    parser.add_argument("--public-upload-base-url", default=DEFAULT_PUBLIC_UPLOAD_BASE_URL)
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--engine-restart-wait-sec", type=float, default=20.0)
    add_backbone_args(parser)   
    args = parser.parse_args()

    
    
    client = HttpClient(args.backend_url)
    push_vision_override(client, args)   
    episode_summaries: list[dict[str, Any]] = []
    exit_code = 0
    for i in range(1, args.episodes + 1):
        episode_task_id = f"{args.task_id}_ep{i}"
        
        if i >= 2:
            restart_engine_between_episodes(
                client,
                task_id=episode_task_id,
                wait_sec=args.engine_restart_wait_sec,
            )
        try:
            result = run_case(
                backend_url=args.backend_url,
                task_id=episode_task_id,
                drone_id=args.drone_id,
                dry_run=args.dry_run,
                skip_session_check=args.skip_session_check,
                max_steps=args.max_steps,
                takeoff_height_m=args.takeoff_height_m,
                takeoff_speed=args.takeoff_speed,
                action_timeout_sec=args.action_timeout_sec,
                photo_timeout_sec=args.photo_timeout_sec,
                public_upload_base_url=args.public_upload_base_url,
                move_speed=args.move_speed,
                max_forward_m=args.max_forward_m,
                front_forward_m=args.front_forward_m,
                front_turn_deg=args.front_turn_deg,
                lost_patience=args.lost_patience,
                adj_check_sec=args.adj_check_sec,
                adj_final_sec=args.adj_final_sec,
                max_llm_calls=args.max_llm_calls,
                max_turn_deg=args.max_turn_deg,
                max_consecutive_turns=args.max_consecutive_turns,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            episode_summaries.append(
                {
                    "episode": i,
                    "task_id": episode_task_id,
                    "status": result.get("status"),
                    "steps": result.get("steps"),
                    "max_steps": result.get("max_steps"),
                    "result_path": result.get("result_path"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "episode": i,
                        "task_id": episode_task_id,
                        "error_type": exc.__class__.__name__,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            episode_summaries.append(
                {
                    "episode": i,
                    "task_id": episode_task_id,
                    "status": "failed",
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
            exit_code = 1

    print("\n===== \u591a\u8f6e\u5b9e\u9a8c\u6c47\u603b =====", flush=True)
    print(
        json.dumps(
            {"episodes": args.episodes, "summaries": episode_summaries},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    for summary in episode_summaries:
        ok = summary.get("status") in {"completed", "dry_run"}
        flag = "\u6210\u529f" if ok else "\u672a\u6210\u529f"
        print(
            f"[\u7b2c {summary['episode']} \u8f6e] {flag} "
            f"task_id={summary['task_id']} status={summary.get('status')} "
            f"steps={summary.get('steps')}/{summary.get('max_steps')}",
            flush=True,
        )

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
