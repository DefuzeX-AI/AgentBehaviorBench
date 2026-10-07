"""End-to-end topdown-only fire recognition test.

This branch test does not run the full navigation policy. It sends the
single-drone scenario, sends a takeoff command, asks the image engine to take a
photo, waits for the uploaded topdown image, and calls the topdown fire-analysis
HTTP route.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.modules.envs.scenario import ScenarioSpec
from app.modules.envs.task_id import make_task_id
from examples._log_util import setup_console_logging, log_cmd, brief_cmd, log_http_req, log_http_resp, log_http_err
from examples.singledrone_fire.scenario import build_single_drone_fire_scenario, image_config, uav_name

CASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = CASE_DIR / "uploads"
RESULTS_DIR = CASE_DIR / "results"

DEFAULT_IMAGE = (
    UPLOAD_ROOT
    / "singledrone_fire_test_001"
    / "UAV-FIRE-001"
    / "topdown_rgb"
    / "topdown_rgb_20260528_161927_759357.png"
)


def build_singlefire_photo_payload(
    *,
    task_id: str,
    image_session_key: str,
    drone_id: str = "UAV-FIRE-001",
    step_index: int = 1,
    upload_url: str = "http://127.0.0.1:9909/sim/vision/upload",
) -> dict[str, Any]:
    """Build the takePhoto payload whose uploadSpec can be copied by UE.

    singlefire uploads one full/global screenshot through the common vision
    endpoint. The backend then crops/saves global and topdown images before
    running the LLM.
    """

    cfg = image_config()
    photo_request_id = f"{task_id}_singledrone_fire_step_{step_index}_{drone_id}_global"
    photo_id = f"{task_id}_{drone_id}_global_step_{step_index}"
    fields = {
        "taskId": task_id,
        "taskType": "singledrone_fire",
        "agentId": drone_id,
        "agentType": "uav",
        "viewType": "global",
        "analysisType": "singlefire",
        "stepIndex": step_index,
        "photoid": photo_id,
        "photoRequestId": photo_request_id,
        "subtaskIndex": 0,
        "globalLengthM": cfg.get("global_ground_length_m", 6000),
        "globalWidthM": cfg.get("global_ground_width_m", 6000),
        "topdownLengthM": cfg.get("topdown_ground_length_m", 400),
        "topdownWidthM": cfg.get("topdown_ground_width_m", 300),
    }
    return {
        "commandType": "takePhoto",
        "taskId": task_id,
        "engineSessionKey": image_session_key,
        "broadcast": False,
        "requireAck": False,
        "timeoutSec": 0,
        "modelIdList": [
            {
                "droneId": drone_id,
                "carId": "",
                "dogId": "",
                "viewType": "global",
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
        ],
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
        return self._open_json(request, url, timeout)

    def post_file(self, path: str, field_name: str, file_path: Path, *, timeout: float = 120.0) -> dict[str, Any]:
        return self.post_multipart(path, files={field_name: file_path}, timeout=timeout)

    def post_multipart(
        self,
        path: str,
        *,
        fields: dict[str, Any] | None = None,
        files: dict[str, Path] | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        boundary = f"----singledrone-fire-{uuid.uuid4().hex}"
        parts: list[bytes] = []
        for name, value in (fields or {}).items():
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        for field_name, file_path in (files or {}).items():
            mime = mimetypes.guess_type(file_path.name)[0] or "image/png"
            content = file_path.read_bytes()
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    (
                        f'Content-Disposition: form-data; name="{field_name}"; '
                        f'filename="{file_path.name}"\r\n'
                    ).encode("utf-8"),
                    f"Content-Type: {mime}\r\n\r\n".encode("utf-8"),
                    content,
                    b"\r\n",
                ]
            )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        return self._open_json(request, url, timeout)

    def _open_json(self, request: urllib.request.Request, url: str, timeout: float | None) -> dict[str, Any]:
        try:
            if timeout is None or timeout <= 0:
                response_context = self._opener.open(request)
            else:
                response_context = self._opener.open(request, timeout=timeout)
            with response_context as response:
                data = self._decode(url, response.read().decode("utf-8"))
                log_http_resp("POST", url, data)
                return data
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            log_http_err("POST", url, detail)
            raise RuntimeError(f"HTTP {exc.code} \u8c03\u7528 {url} \u5931\u8d25: {detail}") from exc
        except urllib.error.URLError as exc:
            log_http_err("POST", url, exc)
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


def build_scenario_payload(task_id: str) -> dict[str, Any]:
    spec = ScenarioSpec.from_definition(build_single_drone_fire_scenario())
    spec.task_id = task_id
    return spec.to_engine_payload()


def ensure_sessions(
    client: HttpClient,
    *,
    airsim_session_key: str,
    image_session_key: str,
) -> dict[str, Any]:
    data = client.get("/websocket/api/sessions", timeout=5.0)
    sessions = (data.get("sessionsByType") or {}).get("LJ-ENGINE") or []
    connected = {
        str(item.get("sessionKey") or item.get("session_key"))
        for item in sessions
        if item.get("connected", True)
    }
    missing = [key for key in (airsim_session_key, image_session_key) if key not in connected]
    if missing:
        available = ", ".join(sorted(connected)) or "\u65e0"
        raise RuntimeError(f"{', '.join(missing)} \u672a\u8fde\u63a5\uff1b\u5f53\u524d LJ-ENGINE \u4f1a\u8bdd: {available}")
    return data


def send_scenario(
    client: HttpClient,
    *,
    task_id: str,
    scenario: dict[str, Any],
    airsim_session_key: str,
    image_session_key: str,
    timeout_sec: float,
) -> dict[str, Any]:
    log_cmd(airsim_session_key, "scenario  \u4e0b\u53d1\u5355\u673a\u6551\u706b\u60f3\u5b9a")
    airsim_response = client.post_json(
        "/sim/uav/airsim/singledrone-fire/scenario",
        {
            "taskId": task_id,
            "scenario": scenario,
            "engineSessionKey": airsim_session_key,
            "broadcast": False,
            "requireAck": True,
            "timeoutSec": timeout_sec,
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )
    log_cmd(image_session_key, "scenario  \u4e0b\u53d1\u5355\u673a\u6551\u706b\u60f3\u5b9a")
    image_response = client.post_json(
        "/sim/uav/airsim/singledrone-fire/scenario",
        {
            "taskId": task_id,
            "scenario": scenario,
            "engineSessionKey": image_session_key,
            "broadcast": False,
            "requireAck": False,
            "timeoutSec": 0,
        },
        timeout=10.0,
    )
    return {"airsim": airsim_response, "image": image_response}


def request_topdown_photo(
    client: HttpClient,
    *,
    task_id: str,
    image_session_key: str,
    drone_id: str = "UAV-FIRE-001",
    step_index: int = 1,
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


def send_takeoff(
    client: HttpClient,
    *,
    task_id: str,
    airsim_session_key: str,
    drone_id: str,
    height_m: float,
    speed: float,
    timeout_sec: float,
) -> dict[str, Any]:
    if height_m <= 0:
        return {"status": "skipped", "reason": "takeoff height <= 0"}
    log_cmd(drone_id, f"takeoff  {brief_cmd({'mile': height_m, 'raw': 0, 'speed': speed})}")
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
            "instructionType": "takeoff",
            "mile": height_m,
            "raw": 0,
            "speed": speed,
        },
        timeout=None if timeout_sec <= 0 else timeout_sec + 5.0,
    )


def wait_topdown_image(
    *,
    task_id: str,
    drone_id: str,
    requested_at: float,
    timeout_sec: float,
) -> Path:
    deadline = time.time() + timeout_sec
    task_dir = UPLOAD_ROOT / safe_component(task_id)
    last_status = f"{task_dir} \u4e0d\u5b58\u5728"
    while time.time() < deadline:
        candidates = find_topdown_candidates(task_dir, drone_id, requested_at)
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)
        if task_dir.exists():
            last_status = f"{task_dir} \u5b58\u5728\uff0c\u4f46\u672a\u53d1\u73b0\u8bf7\u6c42\u540e\u7684 topdown_rgb \u539f\u56fe"
        time.sleep(0.5)
    raise RuntimeError(
        f"\u7b49\u5f85 topdown_rgb \u4e0a\u4f20\u8d85\u65f6: {timeout_sec:.1f}s\uff1b"
        f"taskId={task_id}, droneId={drone_id}\u3002\u6700\u540e\u72b6\u6001: {last_status}"
    )


def find_topdown_candidates(task_dir: Path, drone_id: str, requested_at: float) -> list[Path]:
    if not task_dir.exists():
        return []
    roots = [
        task_dir / safe_component(drone_id) / "topdown_rgb",
        task_dir / safe_component(uav_name()) / "topdown_rgb",
    ]
    roots.extend(path / "topdown_rgb" for path in task_dir.iterdir() if path.is_dir())
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
                and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
                and path.stat().st_mtime >= requested_at - 1.0
            ):
                candidates.append(path)
    return candidates


def safe_component(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/").split("/")[-1]
    safe = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in text).strip("._")
    return safe or "unknown"


def analyze_image_via_route(client: HttpClient, image_path: Path) -> dict[str, Any]:
    return client.post_file("/sim/uav/fire/analyze-topdown", "file", image_path, timeout=180.0)


def write_result(payload: dict[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"topdown_fire_test_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:9909")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--airsim-session-key", default="LJ-ENGINE_airsim")
    parser.add_argument("--image-session-key", default="LJ-ENGINE_image")
    parser.add_argument("--drone-id", default="UAV-FIRE-001")
    parser.add_argument("--scenario-timeout-sec", type=float, default=30.0)
    parser.add_argument("--takeoff-height-m", type=float, default=300.0)
    parser.add_argument("--takeoff-speed", type=float, default=20.0)
    parser.add_argument("--takeoff-timeout-sec", type=float, default=120.0)
    parser.add_argument("--photo-timeout-sec", type=float, default=300.0)
    parser.add_argument(
        "--no-takeoff",
        action="store_true",
        help="skip takeoff and directly request topdown photo",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=None,
        help="only analyze an existing topdown image; skip scenario and takePhoto",
    )
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument(
        "--skip-session-check",
        action="store_true",
        help="skip preflight WebSocket session validation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_path = setup_console_logging(RESULTS_DIR, "singledrone_fire")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)
    client = HttpClient(args.backend_url)
    task_id = args.task_id or make_task_id(prefix="singledrone_fire_test")

    try:
        if args.image:
            image_path = args.image
            payload: dict[str, Any] = {
                "mode": "image_only",
                "task_id": task_id,
                "image_path": str(image_path),
                "analysis": analyze_image_via_route(client, image_path),
            }
        else:
            if not args.skip_session_check:
                sessions = ensure_sessions(
                    client,
                    airsim_session_key=args.airsim_session_key,
                    image_session_key=args.image_session_key,
                )
            else:
                sessions = {"skipped": True}
            scenario = build_scenario_payload(task_id)
            scenario_response = send_scenario(
                client,
                task_id=task_id,
                scenario=scenario,
                airsim_session_key=args.airsim_session_key,
                image_session_key=args.image_session_key,
                timeout_sec=args.scenario_timeout_sec,
            )
            takeoff_response = (
                {"status": "skipped"}
                if args.no_takeoff
                else send_takeoff(
                    client,
                    task_id=task_id,
                    airsim_session_key=args.airsim_session_key,
                    drone_id=args.drone_id,
                    height_m=args.takeoff_height_m,
                    speed=args.takeoff_speed,
                    timeout_sec=args.takeoff_timeout_sec,
                )
            )
            requested_at = time.time()
            photo_response = request_topdown_photo(
                client,
                task_id=task_id,
                image_session_key=args.image_session_key,
            )
            image_path = wait_topdown_image(
                task_id=task_id,
                drone_id=args.drone_id,
                requested_at=requested_at,
                timeout_sec=args.photo_timeout_sec,
            )
            payload = {
                "mode": "auto",
                "task_id": task_id,
                "sessions": sessions,
                "scenario_response": scenario_response,
                "takeoff_response": takeoff_response,
                "photo_response": photo_response,
                "image_path": str(image_path),
                "analysis": analyze_image_via_route(client, image_path),
            }

        if not args.no_save:
            payload["result_path"] = str(write_result(payload))
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                    "task_id": task_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
