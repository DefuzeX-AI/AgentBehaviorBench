"""Run the initial 10-UAV scenario, takeoff, and photo-upload smoke flow."""

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
from examples.multiagentstasks.scenario import (
    TASK_TYPE,
    UAV_DEFS,
    build_multiagentstasks_scenario,
    uav_ids,
)

CASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = CASE_DIR / "results"
UPLOADS_DIR = CASE_DIR / "uploads"
DEFAULT_PUBLIC_UPLOAD_BASE_URL = "http://127.0.0.1:9909"


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, path: str, *, timeout: float = 5.0) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with self._opener.open(url, timeout=timeout) as response:
                return self._decode(url, response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
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
        try:
            response_context = (
                self._opener.open(request)
                if timeout is None or timeout <= 0
                else self._opener.open(request, timeout=timeout)
            )
            with response_context as response:
                return self._decode(url, response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} \u8c03\u7528 {url} \u5931\u8d25: {detail}") from exc
        except urllib.error.URLError as exc:
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


def safe_component(value: str, fallback: str = "item") -> str:
    text = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or ""))
    return text.strip("._-") or fallback


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


def build_scenario_payload(task_id: str, max_steps: int) -> dict[str, Any]:
    spec = ScenarioSpec.from_definition(build_multiagentstasks_scenario(max_steps=max_steps))
    spec.task_id = task_id
    return spec.to_engine_payload()


def dispatch_scenario(client: HttpClient, *, task_id: str, scenario: dict[str, Any], dry_run: bool) -> dict[str, Any]:
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


def send_takeoff_for_all(
    client: HttpClient,
    *,
    task_id: str,
    height_m: float,
    speed: float,
    dry_run: bool,
) -> dict[str, Any]:
    return client.post_json(
        "/sim/uav/airsim/action",
        {
            "taskId": task_id,
            "engineSessionKey": "LJ-ENGINE_airsim",
            "broadcast": False,
            "requireAck": False,
            "dryRun": dry_run,
            "commandType": "executeAction",
            "dronesAction": [
                {
                    "dronesId": drone_id,
                    "instructionType": "takeoff",
                    "command": {
                        "mile": height_m,
                        "raw": 0,
                        "speed": speed,
                    },
                }
                for drone_id in uav_ids()
            ],
        },
        timeout=10.0,
    )


def build_photo_request(
    *,
    task_id: str,
    step_index: int,
    public_upload_base_url: str,
    topdown_length_m: float,
    topdown_width_m: float,
) -> dict[str, Any]:
    upload_url = f"{public_upload_base_url.rstrip('/')}/sim/vision/upload"
    model_items: list[dict[str, Any]] = []
    for drone_id in uav_ids():
        photo_request_id = f"{task_id}_multiagentstasks_step_{step_index}_{drone_id}_topdown"
        photo_id = f"{task_id}_{drone_id}_topdown_step_{step_index}"
        fields = {
            "taskId": task_id,
            "taskType": TASK_TYPE,
            "agentId": drone_id,
            "agentType": "uav",
            "viewType": "topdown",
            "analysisType": "multiagentstasks_photo",
            "stepIndex": step_index,
            "photoid": photo_id,
            "photoRequestId": photo_request_id,
            "subtaskIndex": 0,
            "topdownLengthM": topdown_length_m,
            "topdownWidthM": topdown_width_m,
        }
        model_items.append(
            {
                "droneId": drone_id,
                "carId": "",
                "dogId": "",
                "viewType": "topdown",
                "photoid": photo_id,
                "photoRequestId": photo_request_id,
                "stepIndex": step_index,
                "uploadSpec": {
                    "url": upload_url,
                    "method": "POST",
                    "contentType": "multipart/form-data",
                    "fileField": "file",
                    "fields": fields,
                },
            }
        )
    return {
        "commandType": "takePhoto",
        "taskId": task_id,
        "engineSessionKey": "LJ-ENGINE_image",
        "broadcast": False,
        "requireAck": False,
        "timeoutSec": 0,
        "modelIdList": model_items,
    }


def request_photos(
    client: HttpClient,
    *,
    task_id: str,
    step_index: int,
    public_upload_base_url: str,
    topdown_length_m: float,
    topdown_width_m: float,
    dry_run: bool,
) -> dict[str, Any]:
    payload = build_photo_request(
        task_id=task_id,
        step_index=step_index,
        public_upload_base_url=public_upload_base_url,
        topdown_length_m=topdown_length_m,
        topdown_width_m=topdown_width_m,
    )
    if dry_run:
        return {"status": "dry_run", "command": payload}
    return client.post_json("/sim/engine/image/take-photo", payload, timeout=10.0)


def find_uploaded_images(*, task_id: str, requested_at: float) -> dict[str, list[dict[str, Any]]]:
    safe_task_id = safe_component(task_id, "unknown_task")
    found: dict[str, list[dict[str, Any]]] = {}
    for drone_id in uav_ids():
        drone_dir = UPLOADS_DIR / safe_task_id / safe_component(drone_id) / "topdown"
        images: list[dict[str, Any]] = []
        if drone_dir.exists():
            for path in drone_dir.iterdir():
                if not path.is_file() or "_preview" in path.stem:
                    continue
                if path.stat().st_mtime < requested_at - 1.0:
                    continue
                images.append(
                    {
                        "path": str(path),
                        "relativePath": str(path.relative_to(REPO_ROOT)),
                        "sizeBytes": path.stat().st_size,
                        "mtime": path.stat().st_mtime,
                    }
                )
        if images:
            found[drone_id] = sorted(images, key=lambda item: item["mtime"], reverse=True)
    return found


def wait_uploaded_images(*, task_id: str, requested_at: float, timeout_sec: float) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    expected = set(uav_ids())
    latest: dict[str, list[dict[str, Any]]] = {}
    while time.time() < deadline:
        latest = find_uploaded_images(task_id=task_id, requested_at=requested_at)
        if expected.issubset(latest):
            return {
                "status": "complete",
                "expectedCount": len(expected),
                "receivedCount": len(latest),
                "missingDroneIds": [],
                "uploadedImages": latest,
            }
        time.sleep(0.5)
    missing = sorted(expected - set(latest))
    return {
        "status": "timeout",
        "expectedCount": len(expected),
        "receivedCount": len(latest),
        "missingDroneIds": missing,
        "uploadedImages": latest,
    }


def write_result(task_id: str, payload: dict[str, Any]) -> Path:
    task_dir = RESULTS_DIR / safe_component(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = task_dir / f"run_case_{safe_component(task_id)}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def run_case(
    *,
    backend_url: str,
    task_id: str,
    dry_run: bool,
    skip_session_check: bool,
    max_steps: int,
    takeoff_height_m: float,
    takeoff_speed: float,
    photo_step_index: int,
    photo_timeout_sec: float,
    public_upload_base_url: str,
    topdown_length_m: float,
    topdown_width_m: float,
    no_wait_uploads: bool,
) -> dict[str, Any]:
    task_id = task_id or make_task_id(prefix="multiagentstasks")
    client = HttpClient(backend_url)
    required_sessions = ["LJ-ENGINE_airsim", "LJ-ENGINE_image"]
    sessions = {"skipped": True} if skip_session_check or dry_run else ensure_sessions(client, required_sessions)
    scenario = build_scenario_payload(task_id=task_id, max_steps=max_steps)

    scenario_response = dispatch_scenario(client, task_id=task_id, scenario=scenario, dry_run=dry_run)
    takeoff_response = send_takeoff_for_all(
        client,
        task_id=task_id,
        height_m=takeoff_height_m,
        speed=takeoff_speed,
        dry_run=dry_run,
    )
    photo_requested_at = time.time()
    photo_response = request_photos(
        client,
        task_id=task_id,
        step_index=photo_step_index,
        public_upload_base_url=public_upload_base_url,
        topdown_length_m=topdown_length_m,
        topdown_width_m=topdown_width_m,
        dry_run=dry_run,
    )
    upload_wait = (
        {"status": "skipped", "reason": "dry_run or no_wait_uploads"}
        if dry_run or no_wait_uploads
        else wait_uploaded_images(
            task_id=task_id,
            requested_at=photo_requested_at,
            timeout_sec=photo_timeout_sec,
        )
    )

    payload = {
        "status": "dry_run" if dry_run else "ok",
        "mode": "multiagentstasks_initial_flow",
        "task_id": task_id,
        "backend_url": backend_url,
        "required_sessions": required_sessions,
        "sessions": sessions,
        "uav_count": len(UAV_DEFS),
        "uav_ids": uav_ids(),
        "scenario": scenario,
        "scenario_response": scenario_response,
        "takeoff_response": takeoff_response,
        "photo_response": photo_response,
        "upload_wait": upload_wait,
        "uploads_dir": str(UPLOADS_DIR / safe_component(task_id)),
        "notes": [
            "\u521d\u59cb\u6d41\u53ea\u505a 10 \u67b6\u65e0\u4eba\u673a\u60f3\u5b9a\u3001\u8d77\u98de\u3001\u62cd\u7167\u8bf7\u6c42\u3001\u56fe\u7247\u4fdd\u5b58\u786e\u8ba4\u3002",
            "\u56fe\u7247\u4e0a\u4f20\u4f7f\u7528 /sim/vision/upload\uff0ctaskType=multiagentstasks\uff0canalysisType=multiagentstasks_photo\u3002",
            "\u5f53\u524d\u4e0d\u8c03\u7528 LLM\uff0c\u4e0d\u505a\u4efb\u52a1\u89c4\u5212\u3002",
        ],
    }
    payload["result_path"] = str(write_result(task_id, payload))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--task-id", default="multiagentstasks_test_001")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-session-check", action="store_true")
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--takeoff-height-m", type=float, default=200.0)
    parser.add_argument("--takeoff-speed", type=float, default=20.0)
    parser.add_argument("--photo-step-index", type=int, default=1)
    parser.add_argument("--photo-timeout-sec", type=float, default=420.0)
    parser.add_argument("--public-upload-base-url", default=DEFAULT_PUBLIC_UPLOAD_BASE_URL)
    parser.add_argument("--topdown-length-m", type=float, default=400.0)
    parser.add_argument("--topdown-width-m", type=float, default=300.0)
    parser.add_argument("--no-wait-uploads", action="store_true")
    args = parser.parse_args()

    try:
        result = run_case(
            backend_url=args.backend_url,
            task_id=args.task_id,
            dry_run=args.dry_run,
            skip_session_check=args.skip_session_check,
            max_steps=args.max_steps,
            takeoff_height_m=args.takeoff_height_m,
            takeoff_speed=args.takeoff_speed,
            photo_step_index=args.photo_step_index,
            photo_timeout_sec=args.photo_timeout_sec,
            public_upload_base_url=args.public_upload_base_url,
            topdown_length_m=args.topdown_length_m,
            topdown_width_m=args.topdown_width_m,
            no_wait_uploads=args.no_wait_uploads,
        )
    except Exception as exc:  # noqa: BLE001
        result = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
