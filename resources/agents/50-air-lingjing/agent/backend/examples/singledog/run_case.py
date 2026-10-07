"""Single-dog visual navigation workflow runner."""

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
from examples._log_util import (add_backbone_args, brief_cmd, log_cmd, push_vision_override,
                                 restart_engine_between_episodes, setup_console_logging, wait_engine_ready,
                                 log_http_req, log_http_resp, log_http_err, log_receipt, log_vision,
                                 send_task_complete)
from examples.singledog.scenario import DOG_DEF, SUBTASKS, build_singledog_scenario

CASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = CASE_DIR / "results"

MAX_FORWARD_M = 25.0   
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
    spec = ScenarioSpec.from_definition(build_singledog_scenario(max_steps=max_steps))
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
        "go2": "/sim/engine/go2/scenario",
        "image": "/sim/engine/image/scenario",
    }.items():
        log_cmd(f"LJ-ENGINE_{name}", "scenario  \u4e0b\u53d1\u573a\u666f")
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


def request_dog_front_photo(
    client: HttpClient,
    *,
    task_id: str,
    dog_id: str,
    subtask_index: int,
    step_index: int,
    public_upload_base_url: str,
) -> dict[str, Any]:
    upload_url = f"{public_upload_base_url.rstrip('/')}/sim/vision/upload"
    photo_id = f"{task_id}_{dog_id}_front_step_{step_index}"
    upload_fields = {
        "taskId": task_id,
        "taskType": "singledog",
        "agentId": dog_id,
        "agentType": "dog",
        "viewType": "front",
        "analysisType": "singledog_navigation",
        "stepIndex": step_index,
        "photoid": photo_id,
        "topdownLengthM": "",
        "topdownWidthM": "",
        "subtaskIndex": subtask_index,
    }
    log_cmd(dog_id, "take-photo  front \u524d\u89c6\u56fe")
    return client.post_json(
        "/sim/engine/image/take-photo",
        {
            "commandType": "takePhoto",
            "taskId": task_id,
            "modelIdList": [
                {
                    "droneId": "",
                    "carId": "",
                    "dogId": dog_id,
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


def dispatch_dog_pathfinding_action(
    client: HttpClient,
    *,
    task_id: str,
    dog_id: str,
    action: dict[str, Any],
) -> dict[str, Any]:
    instruction_type = str(action["instructionType"])
    command: dict[str, Any] = {}
    if instruction_type == "forward":
        
        mile = float(action["mile"])
        if mile > MAX_FORWARD_M:
            print(f"[\u673a\u5668\u72d7] \u26a0 {dog_id} \u524d\u8fdb {mile:.0f}m \u8d85\u4e0a\u9650 \u2192 \u622a\u65ad\u5230 {MAX_FORWARD_M:.0f}m (\u9632\u8d70\u8fc7\u5934)", flush=True)
            mile = MAX_FORWARD_M
        command["mile"] = mile
        command["raw"] = 0
    elif instruction_type in {"left", "right"}:
        command["mile"] = 0
        command["raw"] = float(action["raw"])
    elif instruction_type == "stop":
        command = {}
    else:
        raise RuntimeError(f"\u4e0d\u652f\u6301\u7684\u673a\u5668\u72d7\u52a8\u4f5c: {instruction_type}")
    if instruction_type != "stop" and action.get("speed") is not None:
        command["speed"] = float(action["speed"])

    log_cmd(dog_id, f"{instruction_type}  {brief_cmd(command)}".strip())
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
                    "NavigationType": "Pathfinding",
                    "Pathfinding": {
                        "instructionType": instruction_type,
                        "command": command,
                    },
                }
            ],
        },
        timeout=10.0,
    )


def wait_dog_motion_event(
    client: HttpClient,
    *,
    task_id: str,
    dog_id: str,
    timeout_sec: float,
) -> dict[str, Any]:
    
    
    window = timeout_sec if timeout_sec > 0 else 60.0
    body = {
        "taskId": task_id,
        "engineSessionKey": "LJ-ENGINE_go2",
        "commandTypes": ["executionCompleted", "collision"],
        "timeoutSec": window,
    }
    waited = 0.0
    max_wait_sec = 900.0
    event: dict[str, Any]
    while True:
        try:
            event = client.post_json("/sim/engine/event/wait", body, timeout=window + 5.0)
            break
        except RuntimeError as exc:
            if "\u8d85\u65f6" in str(exc) or "timeout" in str(exc).lower():
                waited += window
                if waited >= max_wait_sec:
                    print(f"[\u65e0\u4eba\u72d7] \u7b49 {dog_id} \u8fd0\u52a8\u56de\u6267\u7d2f\u8ba1 {waited:.0f}s\u2265\u4e0a\u9650 {max_wait_sec:.0f}s, "
                          f"\u653e\u5f03\u672c\u6b65 (\u5f15\u64ce\u7591\u4f3c\u4e0d\u56de\u62a5)", flush=True)
                    return {"dog_motion_status": "timeout", "dog_id": dog_id}
                print(f"[\u65e0\u4eba\u72d7] \u7b49 {dog_id} \u8fd0\u52a8\u56de\u6267... \u5df2\u7b49 {waited:.0f}s (\u52a8\u4f5c\u53ef\u80fd\u8f83\u6162)", flush=True)
                continue
            raise
    response = event.get("response") if isinstance(event.get("response"), dict) else event
    event_command_type = response.get("commandType") if isinstance(response, dict) else None
    event["dog_motion_status"] = "collision" if event_command_type == "collision" else "completed"
    event_dog_id = _find_first_present_by_key(
        event,
        {"dogID", "dogId", "unmannedDogID", "unmannedDogId", "go2Id", "ugvId"},
    )
    if event_dog_id is not None and str(event_dog_id) != str(dog_id):
        event["dog_id_warning"] = f"expected={dog_id}, actual={event_dog_id}"
    return event


def wait_navigation_adjudication(
    client: HttpClient,
    *,
    task_id: str,
    dog_id: str,
    timeout_sec: float,
) -> dict[str, Any] | None:
    """\u7b49\u5f15\u64ce\u7684\u5bfc\u822a\u5b8c\u6210\u88c1\u51b3 ``adjudicationReport`` \u2014\u2014 **\u4efb\u52a1\u662f\u5426\u6210\u529f\u4ee5\u5f15\u64ce\u88c1\u51b3\u4e3a\u51c6**(\u5bf9\u6807\u591a\u667a\u80fd\u4f53\u4efb\u52a1)\u3002

    \u5f15\u64ce\u5728\u673a\u5668\u72d7\u62b5\u8fd1\u76ee\u6807(\u95e8\u524d\u6709\u884c\u4eba\u7684\u767d\u8272\u5efa\u7b51)\u65f6\u4e0b\u53d1:
      {commandType:adjudicationReport, dogID, actionType:VisualNavigationComplete, targetLocation, success:true}
    \u547d\u4e2d\u5373\u8fd4\u56de {success, actionType, targetLocation};\u8d85\u65f6\u672a\u89c1\u8fd4\u56de None\u3002\u5f02\u5e38(\u975e\u8d85\u65f6)\u7167\u629b\u3002
    """
    try:
        event = client.post_json(
            "/sim/engine/event/wait",
            {
                "taskId": task_id,
                "engineSessionKey": "LJ-ENGINE_go2",
                "commandTypes": ["adjudicationReport"],
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
    if not isinstance(resp, dict) or str(resp.get("commandType")) != "adjudicationReport":
        return None
    return {
        "success": bool(resp.get("success")),
        "actionType": resp.get("actionType"),
        "targetLocation": resp.get("targetLocation"),
        "raw": resp,
    }


def wait_navigation_result(
    *,
    task_id: str,
    dog_id: str,
    subtask_index: int,
    step_index: int,
    requested_at: float,
    timeout_sec: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    task_dir = RESULTS_DIR / safe_component(task_id)
    prefix = f"singledog_navigation_{safe_component(task_id)}_"
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
                    and payload.get("dogId") == dog_id
                    and int(payload.get("subtaskIndex") or 0) == subtask_index
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
        f"\u7b49\u5f85 singledog \u5bfc\u822a\u8bc6\u56fe\u7ed3\u679c\u8d85\u65f6: {timeout_sec:.1f}s\uff1b"
        f"taskId={task_id}, dogId={dog_id}, subtaskIndex={subtask_index}, stepIndex={step_index}\u3002"
        "\u8bf7\u786e\u8ba4\u6280\u672f\u90e8\u5df2\u5728\u62cd\u7167\u540e\u8c03\u7528 /sim/vision/upload\uff0canalysisType=singledog_navigation"
    )


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


def run_case(
    *,
    backend_url: str,
    task_id: str,
    dog_id: str,
    dry_run: bool,
    skip_session_check: bool,
    max_steps: int,
    max_steps_per_subtask: int,
    photo_timeout_sec: float,
    dog_event_timeout_sec: float,
    dog_spawn_delay_sec: float,
    public_upload_base_url: str,
) -> dict[str, Any]:
    task_id = task_id or make_task_id(prefix="singledog")
    client = HttpClient(backend_url)
    required_sessions = ["LJ-ENGINE_go2", "LJ-ENGINE_image"]
    sessions = {"skipped": True} if skip_session_check else ensure_sessions(client, required_sessions)
    scenario = build_scenario_payload(task_id=task_id, max_steps=max_steps)
    if dry_run:
        return {
            "status": "dry_run",
            "task_id": task_id,
            "dog_id": dog_id,
            "required_sessions": required_sessions,
            "scenario": scenario,
            "dog_spawn_delay_sec": dog_spawn_delay_sec,
            "public_upload_base_url": public_upload_base_url,
            "subtasks": [{"index": index, "instruction": text} for index, text in enumerate(SUBTASKS, start=1)],
        }

    try:
        send_task_complete(client, task_id=task_id)  
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u5148\u53d1 complete \u590d\u4f4d\u5f15\u64ce (taskId={task_id})", flush=True)
    except Exception as _exc:  # noqa: BLE001
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u7684 complete \u5931\u8d25(\u5ffd\u7565): {_exc}", flush=True)
    scenario_response = dispatch_scenario(client, task_id=task_id, scenario=scenario)
    
    if dog_spawn_delay_sec > 0:
        time.sleep(dog_spawn_delay_sec)
    step_index = 0
    subtask_records: list[dict[str, Any]] = []
    arrived = False                          
    adjudication: dict[str, Any] | None = None
    
    adj_poll_sec = min(max(dog_event_timeout_sec or 0.0, 5.0), 30.0)
    for subtask_index, subtask_text in enumerate(SUBTASKS, start=1):
        subtask_record: dict[str, Any] = {
            "subtaskIndex": subtask_index,
            "instruction": subtask_text,
            "steps": [],
            "finished": False,
        }
        for _ in range(max_steps_per_subtask):
            step_index += 1
            requested_at = time.time()
            photo_response = request_dog_front_photo(
                client,
                task_id=task_id,
                dog_id=dog_id,
                subtask_index=subtask_index,
                step_index=step_index,
                public_upload_base_url=public_upload_base_url,
            )
            navigation = wait_navigation_result(
                task_id=task_id,
                dog_id=dog_id,
                subtask_index=subtask_index,
                step_index=step_index,
                requested_at=requested_at,
                timeout_sec=photo_timeout_sec,
            )
            result = navigation["result"]
            log_vision(dog_id, "singledog_navigation", result)
            step_record: dict[str, Any] = {
                "stepIndex": step_index,
                "photo_response": photo_response,
                "navigation": navigation,
            }
            if result.get("status") == "blocked":
                step_record["action_skipped"] = "blocked"
                subtask_record["steps"].append(step_record)
                print(f"[\u673a\u5668\u72d7] {dog_id} \u524d\u65b9\u53d7\u963b, \u672c\u8f6e\u6682\u505c: {result.get('reason')}", flush=True)
                break

            
            if result.get("task_finished") or result.get("instructionType") == "stop":
                step_record["action_skipped"] = "vlm_stop_await_adjudication"
                adj = wait_navigation_adjudication(
                    client, task_id=task_id, dog_id=dog_id,
                    timeout_sec=(dog_event_timeout_sec or 15.0),
                )
            else:
                step_record["action_response"] = dispatch_dog_pathfinding_action(
                    client, task_id=task_id, dog_id=dog_id, action=result,
                )
                step_record["dog_motion_event"] = wait_dog_motion_event(
                    client, task_id=task_id, dog_id=dog_id, timeout_sec=dog_event_timeout_sec,
                )
                log_receipt(dog_id, step_record["dog_motion_event"])
                if step_record["dog_motion_event"].get("dog_motion_status") == "collision":
                    step_record["collision_replan"] = True
                
                adj = wait_navigation_adjudication(
                    client, task_id=task_id, dog_id=dog_id, timeout_sec=adj_poll_sec,
                )

            if adj is not None:
                step_record["adjudication"] = adj
            if adj and adj.get("success"):
                arrived = True
                adjudication = adj
                subtask_record["finished"] = True
                subtask_record["steps"].append(step_record)
                print(f"\U0001f3c1 [\u88c1\u51b3] {dog_id} \u5f15\u64ce\u5224\u5b9a\u5bfc\u822a\u5b8c\u6210\u6210\u529f "
                      f"(actionType={adj.get('actionType')}, targetLocation={adj.get('targetLocation')})", flush=True)
                break
            subtask_record["steps"].append(step_record)
        subtask_records.append(subtask_record)
        if arrived:
            break

    
    if arrived:
        print(f"[\u673a\u5668\u72d7] {dog_id} \u2705 \u4efb\u52a1\u6210\u529f: \u5df2\u62b5\u8fd1\u95e8\u524d\u6709\u884c\u4eba\u7684\u767d\u8272\u5efa\u7b51 (\u5f15\u64ce\u88c1\u51b3 success)\u3002", flush=True)
    else:
        print(f"[\u673a\u5668\u72d7] {dog_id} \u26a0 \u672a\u5728 {max_steps_per_subtask} \u6b65\u5185\u83b7\u5f97\u5f15\u64ce\u6210\u529f\u88c1\u51b3, \u89c6\u4e3a\u672a\u5b8c\u6210\u3002", flush=True)
    try:
        send_task_complete(client, task_id=task_id)
        print(f"[\u5f15\u64ce] \u5df2\u4e0b\u53d1 complete (taskId={task_id}), \u4efb\u52a1\u6536\u5c3e\u3002", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[\u5f15\u64ce] \u4e0b\u53d1 complete \u5931\u8d25(\u5ffd\u7565): {exc}", flush=True)

    payload = {
        "status": "ok" if arrived else "incomplete",
        "success": arrived,
        "adjudication": adjudication,
        "mode": "singledog_visual_navigation",
        "task_id": task_id,
        "dog_id": dog_id,
        "backend_url": backend_url,
        "sessions": sessions,
        "scenario_response": scenario_response,
        "dog_spawn_delay_sec": dog_spawn_delay_sec,
        "public_upload_base_url": public_upload_base_url,
        "subtasks": subtask_records,
        "total_steps": step_index,
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


async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--task-id", default="singledog_test_001")
    parser.add_argument("--dog-id", default=DOG_DEF["code"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--max-steps", type=int, default=140)
    parser.add_argument("--max-steps-per-subtask", type=int, default=40,
                        help="\u5355\u4e00\u5f00\u653e\u5bfc\u822a\u4efb\u52a1\u7684\u6700\u5927\u6b65\u6570\u9884\u7b97 (\u6bcf\u6b65\u4e00\u6b21\u8bc6\u56fe+\u79fb\u52a8, \u76f4\u5230\u5f15\u64ce\u88c1\u51b3\u6210\u529f\u6216\u7528\u5c3d)")
    parser.add_argument("--photo-timeout-sec", type=float, default=420.0)
    parser.add_argument("--dog-event-timeout-sec", type=float, default=60.0)
    parser.add_argument("--dog-spawn-delay-sec", type=float, default=10.0)
    parser.add_argument("--public-upload-base-url", default=DEFAULT_PUBLIC_UPLOAD_BASE_URL)
    parser.add_argument("--episodes", type=int, default=3, help="\u6b63\u5f0f\u5b9e\u9a8c\u8f6e\u6570 (\u591a\u8f6e\u5faa\u73af)")
    parser.add_argument("--engine-restart-wait-sec", type=float, default=20.0, help="\u8f6e\u95f4\u91cd\u542f\u5f15\u64ce\u540e\u7684\u7b49\u5f85\u79d2\u6570")
    add_backbone_args(parser)   
    args = parser.parse_args()

    log_path = setup_console_logging(RESULTS_DIR, "singledog")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)

    
    client = HttpClient(args.backend_url)
    push_vision_override(client, args)   
    base_task_id = args.task_id or make_task_id(prefix="singledog")

    episode_results: list[dict[str, Any]] = []
    overall_status = "ok"
    for i in range(1, args.episodes + 1):
        episode_task_id = f"{base_task_id}_ep{i}"
        print(f"\n{'=' * 60}\n[\u5b9e\u9a8c] \u7b2c {i}/{args.episodes} \u8f6e  taskId={episode_task_id}\n{'=' * 60}", flush=True)

        
        if i >= 2:
            await asyncio.to_thread(
                restart_engine_between_episodes,
                client,
                task_id=episode_task_id,
                wait_sec=args.engine_restart_wait_sec,
            )

        try:
            result = run_case(
                backend_url=args.backend_url,
                task_id=episode_task_id,
                dog_id=args.dog_id,
                dry_run=args.dry_run,
                skip_session_check=args.skip_session_check,
                max_steps=args.max_steps,
                max_steps_per_subtask=args.max_steps_per_subtask,
                photo_timeout_sec=args.photo_timeout_sec,
                dog_event_timeout_sec=args.dog_event_timeout_sec,
                dog_spawn_delay_sec=args.dog_spawn_delay_sec,
                public_upload_base_url=args.public_upload_base_url,
            )
            episode_results.append({"episode": i, **result})
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        except Exception as exc:  # noqa: BLE001
            overall_status = "failed"
            err = {
                "episode": i,
                "task_id": episode_task_id,
                "status": "failed",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
            episode_results.append(err)
            print(json.dumps(err, ensure_ascii=False, indent=2))

    
    print(f"\n{'=' * 60}\n[\u5b9e\u9a8c] \u5404\u8f6e\u6c47\u603b (\u5171 {args.episodes} \u8f6e)\n{'=' * 60}", flush=True)
    for rec in episode_results:
        print(
            f"  \u7b2c {rec.get('episode')} \u8f6e  taskId={rec.get('task_id')}  "
            f"status={rec.get('status')}  total_steps={rec.get('total_steps', '-')}",
            flush=True,
        )

    if overall_status != "ok":
        raise SystemExit(1)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
