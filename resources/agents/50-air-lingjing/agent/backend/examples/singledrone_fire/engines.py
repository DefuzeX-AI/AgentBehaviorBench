"""Engine bridges for the single-drone fire case."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import mimetypes
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.scenario import ScenarioSpec

from examples._log_util import log_cmd, brief_cmd
from examples.singledrone_fire.run_case_test import build_singlefire_photo_payload
from examples.singledrone_fire.scenario import fire_spots, image_config, uav_name

CASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = CASE_DIR / "uploads"
LLM_GLOBAL_IMAGE_SIZE = (385, 385)
LLM_TOPDOWN_IMAGE_SIZE = (400, 300)
LLM_IMAGE_JPEG_QUALITY = 85


def _blank_rgb(width: int, height: int, color: tuple[int, int, int]) -> bytearray:
    return bytearray(color * (width * height))


def _set_px(
    image: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
) -> None:
    if 0 <= x < width and 0 <= y < height:
        idx = (y * width + x) * 3
        image[idx : idx + 3] = bytes(color)


def _draw_circle(
    image: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
    *,
    fill: bool = True,
) -> None:
    r2 = radius * radius
    inner = max(0, radius - 3)
    inner2 = inner * inner
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy)
            if d2 <= r2 and (fill or d2 >= inner2):
                _set_px(image, width, height, x, y, color)


def _draw_cross(
    image: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    size: int,
    color: tuple[int, int, int],
) -> None:
    for delta in range(-size, size + 1):
        _set_px(image, width, height, cx + delta, cy, color)
        _set_px(image, width, height, cx, cy + delta, color)


def _encode_bmp_data_url(image: bytearray, width: int, height: int) -> str:
    row_stride = (width * 3 + 3) & ~3
    pixel_bytes = row_stride * height
    file_size = 14 + 40 + pixel_bytes
    header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, 54)
    dib = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height,
        1,
        24,
        0,
        pixel_bytes,
        2835,
        2835,
        0,
        0,
    )
    rows = bytearray()
    padding = b"\x00" * (row_stride - width * 3)
    for y in range(height - 1, -1, -1):
        row = image[y * width * 3 : (y + 1) * width * 3]
        bgr = bytearray()
        for idx in range(0, len(row), 3):
            r, g, b = row[idx], row[idx + 1], row[idx + 2]
            bgr.extend((b, g, r))
        rows.extend(bgr)
        rows.extend(padding)
    return "data:image/bmp;base64," + base64.b64encode(header + dib + rows).decode("ascii")


def _parse_offset(offset: Any) -> tuple[float, float]:
    if isinstance(offset, (list, tuple)) and len(offset) >= 2:
        return float(offset[0]), float(offset[1])
    if isinstance(offset, dict):
        return float(offset.get("x", 0.0)), float(offset.get("y", 0.0))
    return 0.0, 0.0


class MockSingleDroneFireBridge:
    """Process-local world for smoke tests and offline environment debugging."""

    def __init__(self) -> None:
        self.agent = uav_name()
        self.poses: dict[str, dict[str, float]] = {}
        self.fires = fire_spots()
        self.image_cfg = image_config()
        self._step = 0

    async def reset_scenario(self, spec: ScenarioSpec, cfg: InteractionConfig) -> dict[str, Any]:
        self._step = 0
        self.poses = {}
        for asset in spec.assets:
            self.poses[asset.name] = {
                "x": float(asset.position.get("x", 0.0)),
                "y": float(asset.position.get("y", 0.0)),
                "z": float(asset.position.get("z", asset.position.get("alt", 80.0))),
            }
        for blueprint in spec.task_matrix:
            spots = blueprint.initial_state.get("fire_spots")
            if spots:
                self.fires = [dict(spot) for spot in spots]
            cfg_raw = blueprint.initial_state.get("image_config")
            if cfg_raw:
                self.image_cfg = dict(cfg_raw)
        return {"status": "reset", "agent": self.agent, "fire_count": len(self.fires)}

    async def request_observation(
        self, query: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        pose = self.poses.get(self.agent) or {"x": 0.0, "y": 0.0, "z": 80.0}
        topdown_meta = {
            "center_x": float(pose["x"]),
            "center_y": float(pose["y"]),
            "side_length_m": float(self.image_cfg.get("topdown_side_length_m", 400.0)),
            "length_m": float(self.image_cfg.get("topdown_ground_length_m", 400.0)),
            "width_m": float(self.image_cfg.get("topdown_ground_width_m", 300.0)),
            "meter_per_pixel_x": float(self.image_cfg.get("topdown_meter_per_pixel_x", 1.0)),
            "meter_per_pixel_y": float(self.image_cfg.get("topdown_meter_per_pixel_y", 1.0)),
            "image_width": int(self.image_cfg.get("topdown_width", 512)),
            "image_height": int(self.image_cfg.get("topdown_height", 512)),
            "ground_z": 0.0,
            "frame": "centered_on_uav_x_right_y_up",
        }
        return {
            "agents": {
                self.agent: {
                    "pose": dict(pose),
                    "global_rgb": self._global_rgb(pose),
                    "topdown_rgb": self._topdown_rgb(topdown_meta),
                    "topdown_meta": topdown_meta,
                }
            },
            "step": self._step,
        }

    async def dispatch_action(
        self, action: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        cmd = (action.get("agents") or {}).get(self.agent) or {}
        dx, dy = _parse_offset(cmd.get("offset"))
        alt_delta = float(cmd.get("altitude_delta", 0.0))
        pose = self.poses.setdefault(self.agent, {"x": 0.0, "y": 0.0, "z": 80.0})
        pose["x"] += dx
        pose["y"] += dy
        pose["z"] = max(20.0, pose["z"] + alt_delta)
        self._step += 1
        return {"status": "ok", "applied": {"dx": dx, "dy": dy, "altitude_delta": alt_delta}}

    async def call_custom(
        self, command_name: str, payload: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        return {"status": "noop", "command": command_name}

    async def close(self) -> None:
        return None

    def _world_to_global_px(
        self, x: float, y: float, *, width: int, height: int
    ) -> tuple[int, int]:
        world_min, world_max = -180.0, 180.0
        px = int((x - world_min) / (world_max - world_min) * (width - 1))
        py = int((world_max - y) / (world_max - world_min) * (height - 1))
        return max(0, min(width - 1, px)), max(0, min(height - 1, py))

    def _global_rgb(self, pose: dict[str, float]) -> str:
        width = int(self.image_cfg.get("global_width", 640))
        height = int(self.image_cfg.get("global_height", 640))
        image = _blank_rgb(width, height, (52, 68, 44))
        for grid in range(0, width, 80):
            for y in range(height):
                _set_px(image, width, height, grid, y, (78, 95, 70))
            for x in range(width):
                _set_px(image, width, height, x, grid, (78, 95, 70))
        for fire in self.fires:
            px, py = self._world_to_global_px(
                float(fire["x"]), float(fire["y"]), width=width, height=height
            )
            _draw_circle(image, width, height, px, py, 12, (255, 80, 0), fill=True)
            _draw_circle(image, width, height, px, py, 20, (255, 180, 0), fill=False)
        ux, uy = self._world_to_global_px(
            float(pose["x"]), float(pose["y"]), width=width, height=height
        )
        _draw_cross(image, width, height, ux, uy, 14, (80, 220, 255))
        return _encode_bmp_data_url(image, width, height)

    def _topdown_rgb(self, meta: dict[str, Any]) -> str:
        width = int(meta["image_width"])
        height = int(meta["image_height"])
        side = float(meta["side_length_m"])
        center_x = float(meta["center_x"])
        center_y = float(meta["center_y"])
        image = _blank_rgb(width, height, (46, 57, 38))
        meters_per_px_x = side / width
        meters_per_px_y = side / height
        for fire in self.fires:
            dx = float(fire["x"]) - center_x
            dy = float(fire["y"]) - center_y
            px = int(width / 2.0 + dx / meters_per_px_x)
            py = int(height / 2.0 - dy / meters_per_px_y)
            if 0 <= px < width and 0 <= py < height:
                _draw_circle(image, width, height, px, py, 16, (255, 90, 0), fill=True)
                _draw_circle(image, width, height, px, py, 26, (255, 210, 0), fill=False)
        _draw_cross(image, width, height, width // 2, height // 2, 16, (120, 240, 255))
        return _encode_bmp_data_url(image, width, height)


class HttpServerRealtimeBridge:
    """Bridge from this runner process to the already-running FastAPI service."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:9909",
        engine_session_key: str = "LJ-ENGINE_airsim",
        image_session_key: str = "LJ-ENGINE_image",
        drone_id: str = "UAV-FIRE-001",
        airsim_speed: float = 20.0,
        initial_takeoff_m: float = 200.0,
        image_wait_timeout_sec: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.engine_session_key = engine_session_key
        self.image_session_key = image_session_key
        self.drone_id = drone_id
        self.airsim_speed = float(airsim_speed)
        self.initial_takeoff_m = float(initial_takeoff_m)
        self.image_wait_timeout_sec = float(image_wait_timeout_sec)
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._pose: dict[str, float] = {"x": 0.0, "y": 0.0, "z": 80.0}
        self._step = 0
        self._image_cfg = image_config()
        self._data_url_cache: dict[str, tuple[float, int, str]] = {}

    async def reset_scenario(self, spec: ScenarioSpec, cfg: InteractionConfig) -> dict[str, Any]:
        await self._ensure_engine_connected()
        self._step = 0
        self._image_cfg = image_config()
        for asset in spec.assets:
            if asset.name == uav_name():
                self._pose = {
                    "x": float(asset.position.get("x", 0.0)),
                    "y": float(asset.position.get("y", 0.0)),
                    "z": float(asset.position.get("z", asset.position.get("alt", 80.0))),
                }
                break
        for blueprint in spec.task_matrix:
            cfg_raw = blueprint.initial_state.get("image_config")
            if cfg_raw:
                self._image_cfg = dict(cfg_raw)
        log_cmd(self.engine_session_key, "scenario  \u4e0b\u53d1\u5355\u673a\u6551\u706b\u60f3\u5b9a")
        data = await self._post(
            "/sim/uav/airsim/singledrone-fire/scenario",
            {
                "taskId": spec.task_id,
                "scenario": spec.to_engine_payload(),
                "engineSessionKey": self.engine_session_key,
                "broadcast": False,
                "requireAck": True,
                "timeoutSec": max(cfg.observation.timeout_sec, 30.0),
            },
            timeout=max(cfg.observation.timeout_sec, 30.0) + 2.0,
        )
        response = dict(data.get("response") or data)
        self._ensure_ack_ok(response, "\u60f3\u5b9a\u4e0b\u53d1")
        await self._send_image_scenario(spec, cfg)
        await self._send_initial_takeoff(spec.task_id, cfg)
        return response

    async def request_observation(
        self, query: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        task_id = str(query.get("task_id") or query.get("taskId") or "")
        requested_at = time.time()
        await self._send_take_photo(task_id, cfg)
        images = await self._wait_uploaded_observation(
            task_id=task_id,
            requested_at=requested_at,
            timeout=max(cfg.observation.timeout_sec, self.image_wait_timeout_sec),
        )
        topdown_meta = {
            "center_x": self._pose["x"],
            "center_y": self._pose["y"],
            "side_length_m": float(self._image_cfg.get("topdown_side_length_m", 400.0)),
            "length_m": float(self._image_cfg.get("topdown_ground_length_m", 400.0)),
            "width_m": float(self._image_cfg.get("topdown_ground_width_m", 300.0)),
            "meter_per_pixel_x": float(self._image_cfg.get("topdown_meter_per_pixel_x", 1.0)),
            "meter_per_pixel_y": float(self._image_cfg.get("topdown_meter_per_pixel_y", 1.0)),
            "image_width": images["topdown_width"],
            "image_height": images["topdown_height"],
            "ground_z": 0.0,
            "frame": "centered_on_uav_x_right_y_up",
        }
        return {
            "agents": {
                uav_name(): {
                    "pose": dict(self._pose),
                    "global_rgb": images["global_rgb"],
                    "topdown_rgb": images["topdown_rgb"],
                    "topdown_meta": topdown_meta,
                }
            },
            "step": self._step,
        }

    async def dispatch_action(self, action: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]:
        task_id = str(action.get("task_id") or action.get("taskId") or "")
        airsim_payload = self._airsim_action_payload(action, task_id)
        log_cmd(
            self.drone_id,
            f"{airsim_payload['instructionType']}  {brief_cmd(airsim_payload.get('actionCommand'))}".strip(),
        )
        data = await self._post(
            "/sim/uav/airsim/action",
            airsim_payload,
            timeout=cfg.action.timeout_sec + 2.0,
        )
        self._apply_local_action_estimate(action)
        self._step += 1
        return dict(data)

    async def call_custom(
        self, command_name: str, payload: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        raise NotImplementedError(f"HTTP realtime bridge has no custom endpoint for {command_name}")

    async def close(self) -> None:
        return None

    async def _send_image_scenario(self, spec: ScenarioSpec, cfg: InteractionConfig) -> None:
        log_cmd(self.image_session_key, "scenario  \u4e0b\u53d1\u5355\u673a\u6551\u706b\u60f3\u5b9a")
        await self._post(
            "/sim/uav/airsim/singledrone-fire/scenario",
            {
                "taskId": spec.task_id,
                "scenario": spec.to_engine_payload(),
                "engineSessionKey": self.image_session_key,
                "broadcast": False,
                "requireAck": False,
                "timeoutSec": 0,
            },
            timeout=cfg.action.timeout_sec + 2.0,
        )

    async def _send_initial_takeoff(self, task_id: str, cfg: InteractionConfig) -> None:
        if self.initial_takeoff_m <= 0:
            return
        log_cmd(
            self.drone_id,
            f"takeoff  {brief_cmd({'mile': self.initial_takeoff_m, 'raw': 0, 'speed': self.airsim_speed})}",
        )
        await self._post(
            "/sim/uav/airsim/action",
            {
                "taskId": task_id,
                "engineSessionKey": self.engine_session_key,
                "broadcast": False,
                "requireAck": False,
                "waitExecutionCompleted": True,
                "executionTimeoutSec": max(cfg.observation.timeout_sec, 30.0),
                "waitDroneId": self.drone_id,
                "dronesId": self.drone_id,
                "instructionType": "takeoff",
                "mile": self.initial_takeoff_m,
                "raw": 0,
                "speed": self.airsim_speed,
            },
            timeout=cfg.action.timeout_sec + 2.0,
        )
        self._pose["z"] = max(0.0, self._pose.get("z", 0.0) + self.initial_takeoff_m)

    async def _send_take_photo(self, task_id: str, cfg: InteractionConfig) -> None:
        log_cmd(self.image_session_key, f"take-photo  \u62cd\u7167(drone={self.drone_id}, step={max(int(self._step), 0) + 1})")
        await self._post(
            "/sim/engine/image/take-photo",
            build_singlefire_photo_payload(
                task_id=task_id,
                image_session_key=self.image_session_key,
                drone_id=self.drone_id,
                step_index=max(int(self._step), 0) + 1,
            ),
            timeout=cfg.action.timeout_sec + 2.0,
        )

    def _interaction_payload(self, cfg: InteractionConfig) -> dict[str, Any]:
        payload = cfg.to_dict()
        payload["bridge"] = "realtime"
        payload.setdefault("action", {})
        payload["action"]["dispatch_mode"] = "unicast"
        payload["action"].setdefault("extra", {})
        payload["action"]["extra"]["engine_session_key"] = self.engine_session_key
        return payload

    def _airsim_action_payload(self, action: dict[str, Any], task_id: str) -> dict[str, Any]:
        agent_action = (action.get("agents") or {}).get("drone1") or {}
        dx, dy = _parse_offset(agent_action.get("offset"))
        distance = math.hypot(dx, dy)
        altitude_delta = float(agent_action.get("altitude_delta", 0.0) or 0.0)
        status = str(agent_action.get("status") or "search")

        if distance > 0.01:
            instruction_type = "forward"
            raw = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
            command = {
                "mile": round(distance, 3),
                "raw": round(raw, 3),
                "speed": self.airsim_speed,
            }
        elif altitude_delta > 0.01:
            instruction_type = "takeoff"
            command = {
                "mile": round(altitude_delta, 3),
                "raw": 0,
                "speed": self.airsim_speed,
            }
        elif altitude_delta < -0.01:
            instruction_type = "down"
            command = {
                "mile": round(abs(altitude_delta), 3),
                "raw": 0,
                "speed": self.airsim_speed,
            }
        else:
            instruction_type = "stop"
            command = {}

        return {
            "taskId": task_id,
            "dronesId": self.drone_id,
            "instructionType": instruction_type,
            "actionCommand": command,
            "engineSessionKey": self.engine_session_key,
            "broadcast": False,
            "requireAck": False,
            "status": status,
        }

    def _apply_local_action_estimate(self, action: dict[str, Any]) -> None:
        agent_action = (action.get("agents") or {}).get("drone1") or {}
        dx, dy = _parse_offset(agent_action.get("offset"))
        altitude_delta = float(agent_action.get("altitude_delta", 0.0) or 0.0)
        self._pose["x"] += dx
        self._pose["y"] += dy
        self._pose["z"] = max(0.0, self._pose["z"] + altitude_delta)

    async def _wait_uploaded_observation(
        self,
        *,
        task_id: str,
        requested_at: float,
        timeout: float,
    ) -> dict[str, Any]:
        deadline = time.time() + max(timeout, 1.0)
        last_missing: list[str] = []
        while time.time() < deadline:
            try:
                global_path = self._latest_uploaded_image(
                    task_id, "global_rgb", requested_at=requested_at
                )
                topdown_path = self._latest_uploaded_image(
                    task_id, "topdown_rgb", requested_at=requested_at
                )
            except FileNotFoundError as exc:
                last_missing = [str(exc)]
                await asyncio.sleep(0.5)
                continue

            global_width, global_height = self._image_size(global_path)
            topdown_width, topdown_height = self._image_size(topdown_path)
            return {
                "global_rgb": self._file_to_data_url_cached(
                    global_path, llm_ready=True, image_size=LLM_GLOBAL_IMAGE_SIZE
                ),
                "topdown_rgb": self._file_to_data_url_cached(
                    topdown_path,
                    llm_ready=True,
                    image_size=LLM_TOPDOWN_IMAGE_SIZE,
                    preserve_if_size_matches=True,
                ),
                "global_width": LLM_GLOBAL_IMAGE_SIZE[0],
                "global_height": LLM_GLOBAL_IMAGE_SIZE[1],
                "topdown_width": LLM_TOPDOWN_IMAGE_SIZE[0],
                "topdown_height": LLM_TOPDOWN_IMAGE_SIZE[1],
                "global_source_width": global_width,
                "global_source_height": global_height,
                "topdown_source_width": topdown_width,
                "topdown_source_height": topdown_height,
                "global_path": str(global_path),
                "topdown_path": str(topdown_path),
            }

        task_dir = UPLOAD_ROOT / self._safe_component(task_id)
        detail = "; ".join(last_missing) if last_missing else "\u672a\u53d1\u73b0\u4e0a\u4f20\u56fe\u7247"
        raise RuntimeError(
            "\u62cd\u7167\u8bf7\u6c42\u5df2\u53d1\u9001\uff0c\u4f46\u8d85\u65f6\u672a\u6536\u5230 global_rgb/topdown_rgb \u4e0a\u4f20\u56fe\u7247\uff1b"
            f"\u8bf7\u786e\u8ba4\u6280\u672f\u90e8\u8c03\u7528 /sim/uav/image/upload\uff0ctaskId={task_id}, "
            f"droneId={self.drone_id}, imageType=global_rgb/topdown_rgb\u3002"
            f"\u7b49\u5f85\u65f6\u95f4: {timeout:.1f}s\u3002\u68c0\u67e5\u76ee\u5f55: {task_dir}\u3002\u6700\u540e\u72b6\u6001: {detail}"
        )

    def _latest_uploaded_image(
        self,
        task_id: str,
        image_type: str,
        *,
        requested_at: float,
    ) -> Path:
        task_dir = UPLOAD_ROOT / self._safe_component(task_id)
        search_roots = [
            task_dir / self._safe_component(self.drone_id) / image_type,
            task_dir / self._safe_component(uav_name()) / image_type,
        ]
        if task_dir.exists():
            search_roots.extend(path / image_type for path in task_dir.iterdir() if path.is_dir())

        candidates: list[Path] = []
        seen: set[Path] = set()
        for root in search_roots:
            if root in seen or not root.exists():
                continue
            seen.add(root)
            candidates.extend(
                path
                for path in root.iterdir()
                if path.is_file() and path.stat().st_mtime >= requested_at - 1.0
            )
        if not candidates:
            raise FileNotFoundError(f"{image_type} \u5c1a\u672a\u4e0a\u4f20\u5230 {task_dir}")
        return max(candidates, key=lambda path: path.stat().st_mtime)

    @staticmethod
    def _safe_component(value: str) -> str:
        text = str(value or "").strip().replace("\\", "/").split("/")[-1]
        safe = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in text).strip("._")
        return safe or "unknown"

    @staticmethod
    def _image_size(path: Path) -> tuple[int, int]:
        with Image.open(path) as image:
            return image.size

    def _file_to_data_url_cached(
        self,
        path: Path,
        *,
        llm_ready: bool = False,
        image_size: tuple[int, int] | None = None,
        preserve_if_size_matches: bool = False,
    ) -> str:
        stat = path.stat()
        cache_key = (
            f"{path}|llm_ready={int(llm_ready)}|size={image_size}|"
            f"preserve={int(preserve_if_size_matches)}"
        )
        cached = self._data_url_cache.get(cache_key)
        if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return cached[2]
        if llm_ready:
            data_url = self._llm_ready_image_data_url(
                path,
                image_size or LLM_TOPDOWN_IMAGE_SIZE,
                preserve_if_size_matches=preserve_if_size_matches,
            )
        else:
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            data_url = "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        self._data_url_cache[cache_key] = (stat.st_mtime, stat.st_size, data_url)
        if len(self._data_url_cache) > 32:
            oldest_key = next(iter(self._data_url_cache))
            self._data_url_cache.pop(oldest_key, None)
        return data_url

    @staticmethod
    def _llm_ready_image_data_url(
        path: Path,
        image_size: tuple[int, int],
        *,
        preserve_if_size_matches: bool = False,
    ) -> str:
        if preserve_if_size_matches:
            with Image.open(path) as image:
                if image.size == image_size:
                    mime = mimetypes.guess_type(path.name)[0] or "image/png"
                    return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        with Image.open(path) as image:
            image = image.convert("RGB")
            if image.size != image_size:
                image = image.resize(image_size, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=LLM_IMAGE_JPEG_QUALITY, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")

    @staticmethod
    def _ensure_ack_ok(response: dict[str, Any], phase: str) -> None:
        ack = response.get("ack")
        status = response.get("status")
        if ack == "ok" or status in {"ok", "sent"}:
            return
        raise RuntimeError(f"{phase}\u672a\u6536\u5230 ack=ok\uff0c\u5b9e\u9645\u54cd\u5e94: {response}")

    async def _ensure_engine_connected(self) -> None:
        data = await asyncio.to_thread(self._get_sync, "/websocket/api/sessions", 3.0)
        sessions_by_type = data.get("sessionsByType") or data.get("sessions_by_type") or {}
        engine_sessions = sessions_by_type.get("LJ-ENGINE") or []
        connected = {
            str(item.get("sessionKey") or item.get("session_key"))
            for item in engine_sessions
            if item.get("connected", True)
        }
        required = [self.engine_session_key, self.image_session_key]
        missing = [key for key in required if key not in connected]
        if missing:
            available = ", ".join(sorted(connected)) or "\u65e0"
            raise RuntimeError(
                f"{', '.join(missing)} \u672a\u8fde\u63a5\u5230\u670d\u52a1\u8fdb\u7a0b {self.base_url}\uff1b"
                f"\u5f53\u524d LJ-ENGINE \u4f1a\u8bdd: {available}"
            )

    async def _post(self, path: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        return await asyncio.to_thread(self._post_sync, path, payload, timeout)

    def _get_sync(self, path: str, timeout: float) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with self._opener.open(url, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"\u65e0\u6cd5\u8fde\u63a5\u540e\u7aef\u670d\u52a1 {url}: {exc}") from exc
        return self._decode_response(url, raw)

    def _post_sync(self, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} \u8c03\u7528 {url} \u5931\u8d25: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"\u65e0\u6cd5\u8fde\u63a5\u540e\u7aef\u670d\u52a1 {url}: {exc}") from exc
        return self._decode_response(url, raw)

    @staticmethod
    def _decode_response(url: str, raw: str) -> dict[str, Any]:
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"\u540e\u7aef\u54cd\u5e94\u4e0d\u662f JSON: {url}: {raw[:300]}") from exc
        if envelope.get("code", 200) != 200:
            raise RuntimeError(str(envelope.get("msg") or envelope))
        data = envelope.get("data")
        return data if isinstance(data, dict) else {"data": data}


async def run_mock_smoke() -> dict[str, Any]:
    from examples.singledrone_fire.env import make_env
    from examples.singledrone_fire.evaluator import SingleDroneFireEvaluator
    from examples.singledrone_fire.scenario import build_single_drone_fire_scenario

    env = make_env(
        scenario=build_single_drone_fire_scenario(),
        bridge=MockSingleDroneFireBridge(),
        evaluator=SingleDroneFireEvaluator(),
    )
    obs, info = await env.reset()
    manual_action = {
        "agents": {
            "drone1": {
                "offset": [10.0, 0.0],
                "altitude_delta": 0.0,
                "status": "search",
            }
        }
    }
    obs2, reward, terminated, truncated, step_info = await env.step(manual_action)
    await env.close()
    agent_obs = (obs2.get("agents") or {}).get("drone1") or {}
    return {
        "initial_info": info,
        "reward": reward,
        "terminated": terminated,
        "truncated": truncated,
        "step_info": step_info,
        "has_global_rgb": bool(agent_obs.get("global_rgb")),
        "has_topdown_rgb": bool(agent_obs.get("topdown_rgb")),
        "topdown_meta": agent_obs.get("topdown_meta"),
    }
