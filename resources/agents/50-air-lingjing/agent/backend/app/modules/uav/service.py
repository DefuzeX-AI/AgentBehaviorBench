"""UAV image analysis, route planning, and command dispatch services."""

import asyncio
import base64
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image

from app.modules.agents.registry import invoke_agent
from app.modules.ai.service import analysis as ai_analysis
from app.modules.ai.service import parse_model_json
from app.modules.realtime.manager import realtime_manager

REPO_ROOT = Path(__file__).resolve().parents[3]
SINGLEDRONE_FIRE_UPLOAD_ROOT = REPO_ROOT / "examples" / "singledrone_fire" / "uploads"
SINGLEDRONE_FIRE_PROMPT_ROOT = REPO_ROOT / "examples" / "singledrone_fire" / "prompts"
DELIVERYTASK_UPLOAD_ROOT = REPO_ROOT / "examples" / "deliverytask" / "uploads"
DELIVERYTASK_TARGET_IMAGE_ROOT = REPO_ROOT / "examples" / "deliverytask" / "targetimage"
SINGLEDOG_UPLOAD_ROOT = REPO_ROOT / "examples" / "singledog" / "uploads"
BRIDGE_UPLOAD_ROOT = REPO_ROOT / "examples" / "bridge" / "uploads"
BRIDGE_RESULTS_ROOT = REPO_ROOT / "examples" / "bridge" / "results"
UAVDOG_UPLOAD_ROOT = REPO_ROOT / "examples" / "uavdog" / "uploads"
MULTIAGENTSTASKS_UPLOAD_ROOT = REPO_ROOT / "examples" / "multiagentstasks" / "uploads"
_SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_IMAGE_SUFFIX_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
}
_ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_SINGLEFIRE_GLOBAL_CROP = (34, 34, 416, 416)
_SINGLEFIRE_TOPDOWN_CROP = (34, 440, 416, 713)
_ROUTING_KEYS = {
    "engineSessionKey",
    "engine_session_key",
    "broadcast",
    "dryRun",
    "dry_run",
    "requireAck",
    "require_ack",
    "timeoutSec",
    "timeout_sec",
}

DEFAULT_TOPDOWN_TARGET_FIRE_PROMPT = """<Role>
You are the fire-reconnaissance image analysis module of an autonomously navigating UAV. You are only responsible for analyzing the UAV's downward-looking camera image.
</Role>

<Input>
You will receive only one image: the top-down view directly beneath the UAV.
- Image resolution: 400x300 pixels.
- Ground coverage: 400m x 300m.
- Scale: 1 pixel = 1 meter.
- The image center [200, 150] corresponds to the UAV's current position.
- The pixel origin is at the top-left corner; pixel x increases to the right, and pixel y increases downward.
</Input>

<Task>
Determine whether there are signs of fire in the image, including open flames, orange-yellow flames, smoke plumes, obvious burning areas, or structural burn damage.
If there is a fire, estimate the pixel coordinates of the center of the most obvious fire spot, and compute the ground offset relative to the UAV's current position.
</Task>

<Coordinate_System>
fire_pixel_coord uses image pixel coordinates [x, y].
offset_from_center_m uses ground meters:
- dx = x - 200, positive to the right/east.
- dy = 150 - y, positive upward/north; if the fire spot is in the lower part of the image, dy is negative.
</Coordinate_System>

<Output_Format>
Return only one valid JSON object, no markdown, no explanatory prefix or suffix:

{
  "fire_detected": true,
  "confidence": 0.0,
  "evidence": "a one-sentence rationale in English",
  "fire_pixel_coord": [x, y],
  "offset_from_center_m": [dx, dy]
}

If there is no fire, fire_detected=false, fire_pixel_coord=null, offset_from_center_m=null.
</Output_Format>
"""

DEFAULT_SINGLEDRONE_FIRE_PLAN_PROMPT = """<Role>
You are the path planning module of an autonomously navigating UAV, responsible for outputting the next flight offset based on the global map, the downward-looking view, and the previous step's recognition result.
</Role>

<Inputs>
You will receive two images:
1. Image 1 (global map): 385x385 pixels, corresponding to an actual ground area of 6000m x 6000m.
2. Image 2 (downward-looking view): 400x300 pixels, corresponding to an actual ground area of 400m x 300m.
You will also receive the previous step's top-down recognition result, recognition.
</Inputs>

<Decision_Rules>
If recognition.fire_detected=true, output status="stop", offset=[0,0].
If recognition.target_visible=true and recognition.fire_detected=false, output a local search offset of 100 to 200 meters.
If recognition.target_visible=false and recognition.fire_detected=false, compute the global relocalization offset in meters based on the white circular domed stadium and the current green dot in the global map.
</Decision_Rules>

<Output_Format>
Return only one valid JSON object:
{
  "status": "continue",
  "mode": "local_search",
  "reason": "a one-sentence explanation of the planning rationale in English",
  "predicted_target_coord": [x, y],
  "current_coord": [x, y],
  "offset": [dx, dy]
}
</Output_Format>
"""


def _safe_path_component(value: str | None, default: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = default
    text = text.replace("\\", "/").split("/")[-1]
    safe = _SAFE_COMPONENT_RE.sub("_", text).strip("._")
    return (safe or default)[:120]


def _bool_from_payload(payload: dict[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)
    return default


def _float_from_payload(payload: dict[str, Any], *keys: str, default: float) -> float:
    for key in keys:
        if payload.get(key) is not None:
            return float(payload[key])
    return default


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return float(value)


def _format_size(width: float | int, height: float | int) -> str:
    return f"{width:g}*{height:g}"


def _load_singledrone_prompt(file_name: str, fallback: str) -> str:
    path = SINGLEDRONE_FIRE_PROMPT_ROOT / file_name
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback
    return text or fallback


def _load_singledrone_legacy_prompt(fallback: str) -> str:
    path = REPO_ROOT / "examples" / "singledrone_fire" / "prompt.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback
    return text or fallback


def _connected_engine_targets(engine_session_key: str | None = None) -> tuple[list[str], list[Any]]:
    sessions = realtime_manager.session_map.get("LJ-ENGINE", {})
    if engine_session_key:
        websocket = realtime_manager.session_key_map.get(engine_session_key)
        return ([engine_session_key], [websocket]) if websocket is not None else ([], [])
    return list(sessions.keys()), list(sessions.values())


def _route_options(payload: dict[str, Any]) -> tuple[str | None, bool, bool, bool, float]:
    engine_session_key = payload.get("engineSessionKey") or payload.get("engine_session_key")
    engine_session_key = str(engine_session_key) if engine_session_key else None
    broadcast = _bool_from_payload(payload, "broadcast", default=engine_session_key is None)
    dry_run = _bool_from_payload(payload, "dryRun", "dry_run", default=False)
    require_ack = _bool_from_payload(payload, "requireAck", "require_ack", default=False)
    timeout_sec = _float_from_payload(payload, "timeoutSec", "timeout_sec", default=5.0)
    return engine_session_key, broadcast, dry_run, require_ack, timeout_sec


async def file_to_base64(file: UploadFile) -> str:
    """Read an uploaded image and return the Java-compatible raw base64 string."""

    content = await file.read()
    if not content:
        raise ValueError("File cannot be empty")
    return base64.b64encode(content).decode("utf-8")


async def _upload_file_to_data_url(file: UploadFile) -> tuple[str, dict[str, Any]]:
    content = await file.read()
    if not content:
        raise ValueError("File cannot be empty")
    content_type = file.content_type or "image/png"
    metadata: dict[str, Any] = {
        "filename": file.filename,
        "contentType": content_type,
        "sizeBytes": len(content),
    }
    try:
        with Image.open(io.BytesIO(content)) as image:
            metadata["width"] = image.width
            metadata["height"] = image.height
            metadata["pixelSize"] = _format_size(image.width, image.height)
    except Exception:
        metadata["pixelSize"] = None
    encoded = base64.b64encode(content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}", metadata


async def crop_to_base64(file: UploadFile, x: int = 37, y: int = 37, width: int = 380, height: int = 380) -> str:
    """Crop the map image with the same default rectangle as the Java utility."""

    content = await file.read()
    if not content:
        raise ValueError("File cannot be empty")
    image = Image.open(io.BytesIO(content))
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("Invalid crop parameters: x, y, width, height must be positive numbers")
    if x + width > image.width or y + height > image.height:
        raise ValueError(
            f"Crop region exceeds image boundaries! Image size: {image.width}x{image.height}, "
            f"crop region: ({x},{y},{width},{height})"
        )
    cropped = image.crop((x, y, x + width, y + height))
    output = io.BytesIO()
    fmt = "JPEG" if (file.filename or "").lower().endswith(("jpg", "jpeg")) else "PNG"
    cropped.save(output, format=fmt)
    return base64.b64encode(output.getvalue()).decode("utf-8")


async def uav_recon(file: UploadFile) -> bool:
    """Detect fire by executing the `uav_recon` LangGraph task."""

    encoded = await file_to_base64(file)
    result = await invoke_agent(
        "uav_recon",
        {"image_base64": encoded, "metadata": {"source": "sim/uav/recon"}},
    )
    return bool(result.get("result"))


async def analyze_topdown_fire(file: UploadFile) -> dict[str, Any]:
    """Analyze a single topdown UAV image and return structured fire metadata."""

    encoded = await file_to_base64(file)
    image_url = f"data:{file.content_type or 'image/png'};base64,{encoded}"
    prompt = _load_singledrone_prompt(
        "topdown_target_fire.txt",
        DEFAULT_TOPDOWN_TARGET_FIRE_PROMPT,
    )
    raw_response = await ai_analysis(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                ],
            }
        ]
    )
    result = parse_model_json(raw_response)
    _validate_topdown_fire_result(result)
    return {
        "raw_response": raw_response,
        "result": result,
    }


async def plan_single_drone_fire(
    global_file: UploadFile,
    topdown_file: UploadFile,
    recognition: dict[str, Any],
) -> dict[str, Any]:
    """Plan the next UAV offset from global/topdown images and recognition metadata."""

    global_url, global_meta = await _upload_file_to_data_url(global_file)
    topdown_url, topdown_meta = await _upload_file_to_data_url(topdown_file)
    prompt = _load_singledrone_prompt(
        "plan.txt",
        DEFAULT_SINGLEDRONE_FIRE_PLAN_PROMPT,
    )
    recognition_text = json.dumps({"recognition": recognition}, ensure_ascii=False, indent=2)
    raw_response = await ai_analysis(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "text", "text": f"The previous step's recognition result is as follows:\n{recognition_text}"},
                    {"type": "text", "text": "Image 1: global map."},
                    {"type": "image_url", "image_url": {"url": global_url, "detail": "high"}},
                    {"type": "text", "text": "Image 2: UAV downward-looking view."},
                    {"type": "image_url", "image_url": {"url": topdown_url, "detail": "high"}},
                ],
            }
        ]
    )
    result = parse_model_json(raw_response)
    _validate_single_drone_fire_plan(result)
    return {
        "raw_response": raw_response,
        "result": result,
        "inputMetadata": {
            "global": global_meta,
            "topdown": topdown_meta,
        },
    }


async def analyze_singlefire_images(
    *,
    global_file: UploadFile,
    topdown_file: UploadFile | None = None,
    task_id: str,
    drone_id: str = "UAV-FIRE-001",
    global_length_m: Any = 6000,
    global_width_m: Any = 6000,
    topdown_length_m: Any = 400,
    topdown_width_m: Any = 300,
) -> dict[str, Any]:
    """Save/crop UE images and analyze them with examples/singledrone_fire/prompt.txt."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")

    global_content = await global_file.read()
    if not global_content:
        raise ValueError("globalFile cannot be empty")

    crop_mode = topdown_file is None
    if crop_mode:
        global_content, topdown_content = _crop_singlefire_screenshot(global_content)
        global_filename = "singlefire_global_crop.png"
        topdown_filename = "singlefire_topdown_crop.png"
        global_content_type = "image/png"
        topdown_content_type = "image/png"
    else:
        topdown_content = await topdown_file.read()
        if not topdown_content:
            raise ValueError("topdownFile cannot be empty")
        global_filename = global_file.filename
        topdown_filename = topdown_file.filename
        global_content_type = global_file.content_type
        topdown_content_type = topdown_file.content_type

    global_saved = _save_singledrone_fire_image_bytes(
        global_content,
        filename=global_filename,
        content_type=global_content_type,
        task_id=task_id,
        drone_id=drone_id,
        image_type="global_rgb",
        length_m=global_length_m,
        width_m=global_width_m,
    )
    topdown_saved = _save_singledrone_fire_image_bytes(
        topdown_content,
        filename=topdown_filename,
        content_type=topdown_content_type,
        task_id=task_id,
        drone_id=drone_id,
        image_type="topdown_rgb",
        length_m=topdown_length_m,
        width_m=topdown_width_m,
    )

    prompt = _load_singledrone_legacy_prompt(DEFAULT_SINGLEDRONE_FIRE_PLAN_PROMPT)
    global_url = _data_url_from_bytes(global_content, global_content_type or "image/png")
    topdown_url = _data_url_from_bytes(topdown_content, topdown_content_type or "image/png")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "text", "text": "Image 1: global map."},
                {"type": "image_url", "image_url": {"url": global_url, "detail": "high"}},
                {"type": "text", "text": "Image 2: downward-looking camera image."},
                {"type": "image_url", "image_url": {"url": topdown_url, "detail": "high"}},
            ],
        }
    ]
    try:
        raw_response = await ai_analysis(messages)
        result = parse_model_json(raw_response)
        _validate_singlefire_result(result)
    except Exception as exc:
        _write_singlefire_error_result(task_id, drone_id, exc, global_saved, topdown_saved)
        raise
    result_path = _write_singlefire_result(task_id, drone_id, result, raw_response, global_saved, topdown_saved)
    return {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-FIRE-001"),
        "savedImages": {
            "global_rgb": global_saved,
            "topdown_rgb": topdown_saved,
        },
        "cropMode": crop_mode,
        "cropBoxes": (
            {
                "global_rgb": _SINGLEFIRE_GLOBAL_CROP,
                "topdown_rgb": _SINGLEFIRE_TOPDOWN_CROP,
            }
            if crop_mode
            else None
        ),
        "resultPath": str(result_path),
        "raw_response": raw_response,
        "result": result,
    }


async def analyze_deliverytask_traffic_image(
    *,
    file: UploadFile,
    task_id: str,
    drone_id: str = "UAV-DELIVERY-001",
    route_point_index: Any = 0,
    route_point: Any = None,
) -> dict[str, Any]:
    """Save a deliverytask UAV topdown image and analyze route blockage."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    content = await file.read()
    if not content:
        raise ValueError("file cannot be empty")
    saved = _save_deliverytask_image_bytes(
        content,
        filename=file.filename,
        content_type=file.content_type,
        task_id=task_id,
        entity_id=drone_id,
        image_type="uav_topdown",
    )
    if isinstance(route_point, str) and route_point.strip():
        try:
            route_point_payload = json.loads(route_point)
        except json.JSONDecodeError as exc:
            raise ValueError(f"routePoint must be a JSON string: {exc}") from exc
    elif isinstance(route_point, dict):
        route_point_payload = route_point
    else:
        route_point_payload = None

    from examples.deliverytask.policy import analyze_uav_traffic_image

    analysis_result = await analyze_uav_traffic_image(
        task_id=task_id,
        drone_id=drone_id,
        image_path=Path(saved["path"]),
        route_point_index=int(route_point_index or 0),
        route_point=route_point_payload,
    )
    return {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-DELIVERY-001"),
        "savedImage": saved,
        **analysis_result,
    }


async def analyze_deliverytask_dog_target_house(
    *,
    front_file: UploadFile,
    target_file: UploadFile | None = None,
    target_side_file: UploadFile | None = None,
    task_id: str,
    dog_id: str = "UGV-DELIVERY-001",
    step_index: Any = 0,
) -> dict[str, Any]:
    """Save dog front/reference images and analyze target-house visibility."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    front_content = await front_file.read()
    if not front_content:
        raise ValueError("frontFile cannot be empty")
    front_saved = _save_deliverytask_image_bytes(
        front_content,
        filename=front_file.filename,
        content_type=front_file.content_type,
        task_id=task_id,
        entity_id=dog_id,
        image_type="dog_front",
    )

    target_saved_list: list[dict[str, Any]] = []
    target_paths: list[Path] = []
    if target_file is not None:
        target_content = await target_file.read()
        if target_content:
            target_saved = _save_deliverytask_image_bytes(
                target_content,
                filename=target_file.filename,
                content_type=target_file.content_type,
                task_id=task_id,
                entity_id=dog_id,
                image_type="target_house_front_reference",
            )
            target_saved_list.append(target_saved)
            target_paths.append(Path(target_saved["path"]))
    if target_side_file is not None:
        side_content = await target_side_file.read()
        if side_content:
            side_saved = _save_deliverytask_image_bytes(
                side_content,
                filename=target_side_file.filename,
                content_type=target_side_file.content_type,
                task_id=task_id,
                entity_id=dog_id,
                image_type="target_house_side_reference",
            )
            target_saved_list.append(side_saved)
            target_paths.append(Path(side_saved["path"]))

    if not target_paths:
        for name in ("sideair.png",):
            path = DELIVERYTASK_TARGET_IMAGE_ROOT / name
            if not path.exists():
                raise ValueError(f"Missing local target-house reference image: {path}")
            target_paths.append(path)

    from examples.deliverytask.policy import analyze_dog_target_house_images

    analysis_result = await analyze_dog_target_house_images(
        task_id=task_id,
        dog_id=dog_id,
        front_image_path=Path(front_saved["path"]),
        target_image_paths=target_paths,
        step_index=int(step_index or 0),
    )
    return {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "dogId": _safe_path_component(dog_id, "UGV-DELIVERY-001"),
        "savedImages": {
            "front": front_saved,
            "targets": target_saved_list,
            "localTargets": [str(path) for path in target_paths if str(path).startswith(str(DELIVERYTASK_TARGET_IMAGE_ROOT))],
        },
        **analysis_result,
    }


async def analyze_deliverytask_uav_dog_path(
    *,
    file: UploadFile,
    task_id: str,
    drone_id: str = "UAV-DELIVERY-001",
    step_index: Any = 0,
    current_height_m: Any = None,
) -> dict[str, Any]:
    """Save UAV topdown image and analyze dog PathPlanning waypoints."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    content = await file.read()
    if not content:
        raise ValueError("file cannot be empty")
    saved = _save_deliverytask_image_bytes(
        content,
        filename=file.filename,
        content_type=file.content_type,
        task_id=task_id,
        entity_id=drone_id,
        image_type="uav_dog_path_topdown",
    )
    from examples.deliverytask.policy import analyze_uav_dog_path_plan_image
    reference_path = DELIVERYTASK_TARGET_IMAGE_ROOT / "topdownair.png"
    if not reference_path.exists():
        raise ValueError(f"Missing local target-house UAV top-down reference image: {reference_path}")

    analysis_result = await analyze_uav_dog_path_plan_image(
        task_id=task_id,
        drone_id=drone_id,
        image_path=Path(saved["path"]),
        reference_image_path=reference_path,
        step_index=int(step_index or 0),
        current_height_m=_optional_float(current_height_m),
    )
    return {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-DELIVERY-001"),
        "savedImage": saved,
        **analysis_result,
    }


async def analyze_singledog_navigation(
    *,
    front_file: UploadFile,
    task_id: str,
    dog_id: str = "UGV-SINGLEDOG-001",
    subtask_index: Any = 1,
    step_index: Any = 0,
) -> dict[str, Any]:
    """Save a singledog front-view image and decide the next Go2 action."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    content = await front_file.read()
    if not content:
        raise ValueError("frontFile cannot be empty")
    saved = _save_singledog_image_bytes(
        content,
        filename=front_file.filename,
        content_type=front_file.content_type,
        task_id=task_id,
        entity_id=dog_id,
        image_type="front",
    )
    from examples.singledog.policy import analyze_singledog_navigation_image

    analysis_result = await analyze_singledog_navigation_image(
        task_id=task_id,
        dog_id=dog_id,
        image_path=Path(saved["path"]),
        subtask_index=int(subtask_index or 1),
        step_index=int(step_index or 0),
    )
    return {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "dogId": _safe_path_component(dog_id, "UGV-SINGLEDOG-001"),
        "savedImage": saved,
        **analysis_result,
    }


async def analyze_bridge_inspection(
    *,
    file: UploadFile,
    task_id: str,
    drone_id: str = "UAV-BRIDGE-001",
    step_index: Any = 0,
    topdown_length_m: Any = None,
    topdown_width_m: Any = None,
    memo: str = "",
) -> dict[str, Any]:
    """Save a bridge topdown image and analyze fracture/next movement."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    content = await file.read()
    if not content:
        raise ValueError("file cannot be empty")
    saved = _save_bridge_image_bytes(
        content,
        filename=file.filename,
        content_type=file.content_type,
        task_id=task_id,
        entity_id=drone_id,
        image_type="topdown",
    )
    from examples.bridge.policy import analyze_bridge_topdown_image

    try:
        analysis_result = await analyze_bridge_topdown_image(
            task_id=task_id,
            drone_id=drone_id,
            image_path=Path(saved["path"]),
            step_index=int(step_index or 0),
            topdown_length_m=_optional_float(topdown_length_m),
            topdown_width_m=_optional_float(topdown_width_m),
            memo=memo,
        )
    except Exception as exc:
        error_path = _write_bridge_error_result(task_id, drone_id, int(step_index or 0), exc, saved)
        raise RuntimeError(f"bridge_inspection image analysis failed; error result has been saved: {error_path}: {exc}") from exc
    return {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-BRIDGE-001"),
        "savedImage": saved,
        **analysis_result,
    }


async def analyze_bridge_front_view(
    *,
    file: UploadFile,
    task_id: str,
    drone_id: str = "UAV-BRIDGE-001",
    step_index: Any = 0,
    memo: str = "",
) -> dict[str, Any]:
    """Save a bridge front-view image and judge sea/bridge direction (used when the top-down view lost the bridge)."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    content = await file.read()
    if not content:
        raise ValueError("file cannot be empty")
    saved = _save_bridge_image_bytes(
        content,
        filename=file.filename,
        content_type=file.content_type,
        task_id=task_id,
        entity_id=drone_id,
        image_type="front",
    )
    from examples.bridge.policy import analyze_bridge_front_view as _analyze_front

    try:
        analysis_result = await _analyze_front(
            task_id=task_id,
            drone_id=drone_id,
            image_path=Path(saved["path"]),
            step_index=int(step_index or 0),
            memo=memo,
        )
    except Exception as exc:
        error_path = _write_bridge_error_result(task_id, drone_id, int(step_index or 0), exc, saved)
        raise RuntimeError(f"bridge_front image analysis failed; error result has been saved: {error_path}: {exc}") from exc
    return {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-BRIDGE-001"),
        "savedImage": saved,
        **analysis_result,
    }


async def analyze_uavdog_path_planning(
    *,
    file: UploadFile,
    task_id: str,
    drone_id: str = "UAV-UAVDOG-001",
    dog_id: str = "UGV-UAVDOG-001",
    step_index: Any = 0,
    current_height_m: Any = None,
) -> dict[str, Any]:
    """Save UAV topdown image and plan dog waypoints for the uavdog task."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    content = await file.read()
    if not content:
        raise ValueError("file cannot be empty")
    saved = _save_uavdog_image_bytes(
        content,
        filename=file.filename,
        content_type=file.content_type,
        task_id=task_id,
        entity_id=drone_id,
        image_type="topdown",
    )
    from examples.uavdog.policy import analyze_uavdog_path_plan_image, load_collision_context

    normalized_step_index = int(step_index or 0)
    analysis_result = await analyze_uavdog_path_plan_image(
        task_id=task_id,
        drone_id=drone_id,
        dog_id=dog_id,
        image_path=Path(saved["path"]),
        step_index=normalized_step_index,
        current_height_m=_optional_float(current_height_m),
        collision_context=load_collision_context(task_id, normalized_step_index),
    )
    return {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-UAVDOG-001"),
        "dogId": _safe_path_component(dog_id, "UGV-UAVDOG-001"),
        "savedImage": saved,
        **analysis_result,
    }


def _pick_file(files: dict[str, UploadFile], *names: str) -> UploadFile | None:
    for name in names:
        if name in files:
            return files[name]
        lower_name = name.lower()
        for key, value in files.items():
            if key.lower() == lower_name:
                return value
    return None


def _compact_upload_result_for_image(result: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "status",
        "message",
        "savedImage",
        "result",
        "finalMetrics",
        "taskId",
        "droneId",
        "dogId",
        "carId",
        "metadata",
    ):
        if key in result:
            compact[key] = result[key]
    if "result" not in compact:
        extracted = {
            key: value
            for key, value in result.items()
            if key not in {"raw_response", "metadata", "savedImage"}
        }
        if extracted:
            compact["result"] = extracted
    if "raw_response" in result:
        raw = str(result["raw_response"])
        compact["raw_response_preview"] = raw[:1000]
    return compact


async def _finalize_common_vision_upload_result(
    result: dict[str, Any],
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    photo_id = metadata.get("photoid") or metadata.get("photoId") or ""
    command = {
        "commandType": "imageUploadResult",
        "taskId": metadata.get("taskId"),
        "photoid": photo_id,
        "photoId": photo_id,
        "taskType": metadata.get("taskType"),
        "agentId": metadata.get("agentId"),
        "agentType": metadata.get("agentType"),
        "viewType": metadata.get("viewType"),
        "analysisType": metadata.get("analysisType"),
        "stepIndex": metadata.get("stepIndex"),
        "subtaskIndex": metadata.get("subtaskIndex", 0),
        "uploadStatus": result.get("status", "processed"),
        "data": _compact_upload_result_for_image(result),
    }
    targets = realtime_manager.resolve_lj_engine_targets(
        dispatch_mode="unicast",
        session_key="LJ-ENGINE_image",
    )
    dispatch: dict[str, Any]
    if targets:
        try:
            await realtime_manager.send_command_to_engine(command, targets=targets)
            dispatch = {
                "sent": True,
                "targetSessionKey": "LJ-ENGINE_image",
                "commandType": command["commandType"],
            }
        except Exception as exc:  # noqa: BLE001
            dispatch = {
                "sent": False,
                "targetSessionKey": "LJ-ENGINE_image",
                "error": str(exc),
            }
    else:
        dispatch = {
            "sent": False,
            "targetSessionKey": "LJ-ENGINE_image",
            "error": "LJ-ENGINE_image is not connected",
        }
    finalized = {
        **result,
        "imageReturnCommand": command,
        "imageReturnDispatch": dispatch,
    }
    realtime_manager.persist_task_data(
        str(metadata.get("taskId") or ""),
        {
            "phase": "vision_upload_result",
            "metadata": metadata,
            "imageReturnDispatch": dispatch,
            "imageReturnCommand": command,
        },
    )
    return finalized


async def handle_common_vision_upload(
    *,
    files: dict[str, UploadFile],
    task_id: str,
    task_type: str,
    agent_type: str,
    agent_id: str,
    view_type: str,
    analysis_type: str,
    step_index: Any = 0,
    subtask_index: Any = None,
    route_point_index: Any = None,
    route_point: Any = None,
    global_length_m: Any = "6000",
    global_width_m: Any = "6000",
    topdown_length_m: Any = "400",
    topdown_width_m: Any = "300",
    current_height_m: Any = None,
    photoid: Any = "",
    memo: Any = "",
) -> dict[str, Any]:
    """Common vision upload entry that dispatches by task/analysis type."""

    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    if not str(agent_id or "").strip():
        raise ValueError("agentId cannot be empty")
    normalized_task_type = str(task_type or "").strip().lower()
    normalized_agent_type = str(agent_type or "").strip().lower()
    normalized_view_type = str(view_type or "").strip().lower()
    normalized_analysis_type = str(analysis_type or "").strip().lower()
    if not normalized_task_type:
        raise ValueError("taskType cannot be empty")
    if not normalized_analysis_type:
        raise ValueError("analysisType cannot be empty")
    if not files:
        raise ValueError("At least one image file must be uploaded")

    metadata = {
        "taskId": task_id,
        "taskType": normalized_task_type,
        "agentType": normalized_agent_type,
        "agentId": agent_id,
        "viewType": normalized_view_type,
        "analysisType": normalized_analysis_type,
        "stepIndex": int(step_index or 0),
    }
    if str(photoid or "").strip():
        metadata["photoid"] = str(photoid).strip()
    if subtask_index not in (None, ""):
        metadata["subtaskIndex"] = int(subtask_index)

    # Image-analysis backbone override: if run_case registered a model override for this taskId via
    # /sim/vision/override, inject it here into the contextvar so that all subsequent branches'
    # analyze_* -> ai_analysis within this request can read it. Each upload request is an independent
    # asyncio Task (each with its own context copy), so setting without resetting will not leak into
    # other concurrent requests.
    from app.modules.ai.service import get_vision_override, vision_override_ctx
    _vision_ov = get_vision_override(task_id)
    if _vision_ov:
        vision_override_ctx().set(_vision_ov)

    async def done(payload: dict[str, Any]) -> dict[str, Any]:
        return await _finalize_common_vision_upload_result(payload, metadata=metadata)

    # First check the task registry: each task places its image-analysis code in a vision.py under its
    # own directory and uses @register; on a hit, directly call that task's analyzer instead of piling
    # task-specific branches into this file.
    from app.modules.uav.analyzer_registry import (
        ensure_task_analyzers_loaded,
        get_analyzer,
    )

    ensure_task_analyzers_loaded()
    task_analyzer = get_analyzer(normalized_analysis_type)
    if task_analyzer is not None:
        result = await task_analyzer(
            files=files,
            task_id=task_id,
            task_type=normalized_task_type,
            agent_id=agent_id,
            agent_type=normalized_agent_type,
            view_type=normalized_view_type,
            step_index=step_index,
            subtask_index=subtask_index,
            route_point_index=route_point_index,
            route_point=route_point,
            current_height_m=current_height_m,
            metadata=metadata,
        )
        return await done(result)

    if normalized_analysis_type == "singlefire":
        global_file = _pick_file(files, "globalFile", "global", "file")
        topdown_file = _pick_file(files, "topdownFile", "topdown")
        if global_file is None:
            raise ValueError("When analysisType=singlefire, globalFile/global/file must be uploaded")
        result = await analyze_singlefire_images(
            global_file=global_file,
            topdown_file=topdown_file,
            task_id=task_id,
            drone_id=agent_id,
            global_length_m=global_length_m,
            global_width_m=global_width_m,
            topdown_length_m=topdown_length_m,
            topdown_width_m=topdown_width_m,
        )
        return await done({"status": "analyzed", "metadata": metadata, **result})

    if normalized_analysis_type in {"traffic_inspection", "delivery_traffic_inspection"}:
        if normalized_task_type != "deliverytask":
            raise ValueError("analysisType=traffic_inspection is only for taskType=deliverytask")
        image_file = _pick_file(files, "topdownFile", "topdown", "file")
        if image_file is None:
            raise ValueError("When analysisType=traffic_inspection, topdownFile/topdown/file must be uploaded")
        result = await analyze_deliverytask_traffic_image(
            file=image_file,
            task_id=task_id,
            drone_id=agent_id,
            route_point_index=route_point_index if route_point_index is not None else step_index,
            route_point=route_point,
        )
        return await done({"status": "analyzed", "metadata": metadata, **result})

    if normalized_analysis_type == "dog_target_house":
        if normalized_task_type != "deliverytask":
            raise ValueError("analysisType=dog_target_house is only for taskType=deliverytask")
        front_file = _pick_file(files, "frontFile", "front", "file")
        target_file = _pick_file(files, "targetFile", "targetFrontFile", "target_front", "target", "referenceFile", "reference")
        target_side_file = _pick_file(files, "targetSideFile", "target_side", "sideFile", "side")
        if front_file is None:
            raise ValueError("When analysisType=dog_target_house, frontFile/front/file must be uploaded")
        result = await analyze_deliverytask_dog_target_house(
            front_file=front_file,
            target_file=target_file,
            target_side_file=target_side_file,
            task_id=task_id,
            dog_id=agent_id,
            step_index=step_index,
        )
        return await done({"status": "analyzed", "metadata": metadata, **result})

    if normalized_analysis_type == "dog_path_planning":
        if normalized_task_type != "deliverytask":
            raise ValueError("analysisType=dog_path_planning is only for taskType=deliverytask")
        image_file = _pick_file(files, "topdownFile", "topdown", "file")
        if image_file is None:
            raise ValueError("When analysisType=dog_path_planning, topdownFile/topdown/file must be uploaded")
        result = await analyze_deliverytask_uav_dog_path(
            file=image_file,
            task_id=task_id,
            drone_id=agent_id,
            step_index=step_index,
            current_height_m=current_height_m,
        )
        return await done({"status": "analyzed", "metadata": metadata, **result})

    if normalized_analysis_type == "singledog_navigation":
        if normalized_task_type != "singledog":
            raise ValueError("analysisType=singledog_navigation is only for taskType=singledog")
        front_file = _pick_file(files, "frontFile", "front", "file")
        if front_file is None:
            raise ValueError("When analysisType=singledog_navigation, frontFile/front/file must be uploaded")
        result = await analyze_singledog_navigation(
            front_file=front_file,
            task_id=task_id,
            dog_id=agent_id,
            subtask_index=subtask_index if subtask_index not in (None, "") else 1,
            step_index=step_index,
        )
        return await done({"status": "analyzed", "metadata": metadata, **result})

    if normalized_analysis_type == "bridge_inspection":
        if normalized_task_type != "bridge":
            raise ValueError("analysisType=bridge_inspection is only for taskType=bridge")
        image_file = _pick_file(files, "topdownFile", "topdown", "file")
        if image_file is None:
            raise ValueError("When analysisType=bridge_inspection, topdownFile/topdown/file must be uploaded")
        result = await analyze_bridge_inspection(
            file=image_file,
            task_id=task_id,
            drone_id=agent_id,
            step_index=step_index,
            topdown_length_m=topdown_length_m,
            topdown_width_m=topdown_width_m,
            memo=str(memo or ""),
        )
        return await done({"status": "analyzed", "metadata": metadata, **result})

    if normalized_analysis_type == "bridge_front":
        if normalized_task_type != "bridge":
            raise ValueError("analysisType=bridge_front is only for taskType=bridge")
        image_file = _pick_file(files, "frontFile", "front", "file")
        if image_file is None:
            raise ValueError("When analysisType=bridge_front, frontFile/front/file must be uploaded")
        result = await analyze_bridge_front_view(
            file=image_file,
            task_id=task_id,
            drone_id=agent_id,
            step_index=step_index,
            memo=str(memo or ""),
        )
        return await done({"status": "analyzed", "metadata": metadata, **result})

    if normalized_analysis_type == "uavdog_path_planning":
        if normalized_task_type != "uavdog":
            raise ValueError("analysisType=uavdog_path_planning is only for taskType=uavdog")
        image_file = _pick_file(files, "topdownFile", "topdown", "file")
        if image_file is None:
            raise ValueError("When analysisType=uavdog_path_planning, topdownFile/topdown/file must be uploaded")
        result = await analyze_uavdog_path_planning(
            file=image_file,
            task_id=task_id,
            drone_id=agent_id,
            dog_id="UGV-UAVDOG-001",
            step_index=step_index,
            current_height_m=current_height_m,
        )
        return await done({"status": "analyzed", "metadata": metadata, **result})

    if normalized_task_type == "multiagentstasks":
        image_file = _pick_file(files, "topdownFile", "topdown", "file")
        if image_file is None:
            image_file = next(iter(files.values()))
        content = await image_file.read()
        saved = _save_multiagentstasks_image_bytes(
            content,
            filename=image_file.filename,
            content_type=image_file.content_type,
            task_id=task_id,
            entity_id=agent_id,
            image_type=normalized_view_type or normalized_analysis_type or "topdown",
        )
        return await done({
            "status": "saved",
            "metadata": metadata,
            "savedImage": saved,
            "message": "The multiagentstasks initial flow currently only saves the image and does not call the LLM.",
        })

    # Unknown analysis types still get safely persisted for debugging.
    image_file = _pick_file(files, "file", "image", normalized_view_type)
    if image_file is None:
        image_file = next(iter(files.values()))
    content = await image_file.read()
    saved = _save_deliverytask_image_bytes(
        content,
        filename=image_file.filename,
        content_type=image_file.content_type,
        task_id=task_id,
        entity_id=agent_id,
        image_type=normalized_view_type or normalized_analysis_type or "unknown_view",
    )
    return await done({
        "status": "saved",
        "metadata": metadata,
        "savedImage": saved,
        "message": f"analysisType={analysis_type} is not yet bound to an image-analysis flow; only the image is saved.",
    })


def _validate_topdown_fire_result(result: dict[str, Any]) -> None:
    required = {
        "target_visible",
        "target_confidence",
        "target_evidence",
        "target_pixel_coord",
        "fire_detected",
        "confidence",
        "evidence",
        "fire_pixel_coord",
        "offset_from_center_m",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"LLM output is missing fields {missing}: {result}")
    if not isinstance(result["target_visible"], bool):
        raise ValueError(f"target_visible must be a JSON boolean: {result}")
    target_confidence = float(result["target_confidence"])
    if not 0.0 <= target_confidence <= 1.0:
        raise ValueError(f"target_confidence must be between 0 and 1: {result}")
    if result["target_visible"]:
        _numeric_pair(result["target_pixel_coord"], "target_pixel_coord")
    if not isinstance(result["fire_detected"], bool):
        raise ValueError(f"fire_detected must be a JSON boolean: {result}")
    confidence = float(result["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0 and 1: {result}")
    if result["fire_detected"]:
        _numeric_pair(result["fire_pixel_coord"], "fire_pixel_coord")
        _numeric_pair(result["offset_from_center_m"], "offset_from_center_m")


def _validate_single_drone_fire_plan(result: dict[str, Any]) -> None:
    required = {"status", "mode", "reason", "predicted_target_coord", "current_coord", "offset"}
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"LLM planning output is missing fields {missing}: {result}")
    if result["status"] not in {"continue", "stop"}:
        raise ValueError(f"status can only be continue or stop: {result}")
    if result["mode"] not in {"local_search", "global_relocalization", "stop"}:
        raise ValueError(f"mode is invalid: {result}")
    if result["predicted_target_coord"] is not None:
        _numeric_pair(result["predicted_target_coord"], "predicted_target_coord")
    if result["current_coord"] is not None:
        _numeric_pair(result["current_coord"], "current_coord")
    offset_x, offset_y = _numeric_pair(result["offset"], "offset")
    if result["status"] == "stop":
        result["offset"] = [0.0, 0.0]
    else:
        result["offset"] = [offset_x, offset_y]


def _validate_singlefire_result(result: dict[str, Any]) -> None:
    required = {
        "thought_process",
        "status",
        "fire_detected",
        "target_visible",
        "coord_frame",
        "fire_pixel_coord",
        "fire_offset_px",
        "target_pixel_coord",
        "current_coord",
        "action_offset_px",
        "reason",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"LLM singlefire output is missing fields {missing}: {result}")
    if result["status"] not in {"continue", "stop"}:
        raise ValueError(f"status can only be continue or stop: {result}")
    if not isinstance(result["fire_detected"], bool):
        raise ValueError(f"fire_detected must be a JSON boolean: {result}")
    if not isinstance(result["target_visible"], bool):
        raise ValueError(f"target_visible must be a JSON boolean: {result}")
    if result["coord_frame"] not in {"topdown", "global", "none"}:
        raise ValueError(f"coord_frame can only be topdown/global/none: {result}")
    if result["fire_pixel_coord"] is not None:
        result["fire_pixel_coord"] = list(_numeric_pair(result["fire_pixel_coord"], "fire_pixel_coord"))
    if result["fire_offset_px"] is not None:
        result["fire_offset_px"] = list(_numeric_pair(result["fire_offset_px"], "fire_offset_px"))
    if result["target_pixel_coord"] is not None:
        result["target_pixel_coord"] = list(_numeric_pair(result["target_pixel_coord"], "target_pixel_coord"))
    if result["current_coord"] is not None:
        result["current_coord"] = list(_numeric_pair(result["current_coord"], "current_coord"))
    offset_x, offset_y = _numeric_pair(result["action_offset_px"], "action_offset_px")
    if result["status"] == "stop" or result["fire_detected"]:
        result["status"] = "stop"
        result["fire_detected"] = True
        result["coord_frame"] = "topdown"
        if result["fire_pixel_coord"] is None:
            raise ValueError(f"When fire_detected=true, fire_pixel_coord cannot be empty: {result}")
        if result["fire_offset_px"] is None:
            raise ValueError(f"When fire_detected=true, fire_offset_px cannot be empty: {result}")
        result["action_offset_px"] = [0.0, 0.0]
    else:
        result["status"] = "continue"
        if result["target_visible"] and result["coord_frame"] != "topdown":
            raise ValueError(f"When target_visible=true and no fire is detected, coord_frame must be topdown: {result}")
        if not result["target_visible"] and result["coord_frame"] != "global":
            raise ValueError(f"When target_visible=false and no fire is detected, coord_frame must be global: {result}")
        result["action_offset_px"] = [offset_x, offset_y]


def _crop_singlefire_screenshot(content: bytes) -> tuple[bytes, bytes]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            global_content = _crop_png_bytes(image, _SINGLEFIRE_GLOBAL_CROP, "global_rgb")
            topdown_content = _crop_png_bytes(image, _SINGLEFIRE_TOPDOWN_CROP, "topdown_rgb")
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("The singlefire uploaded file is not a valid image and cannot be cropped") from exc
    return global_content, topdown_content


def _crop_png_bytes(image: Image.Image, box: tuple[int, int, int, int], label: str) -> bytes:
    x1, y1, x2, y2 = box
    if image.width < x2 or image.height < y2:
        raise ValueError(
            f"The singlefire source image is too small to crop {label}: "
            f"image size={image.width}x{image.height}, requires at least {x2}x{y2}"
        )
    cropped = image.crop(box)
    output = io.BytesIO()
    cropped.save(output, format="PNG")
    return output.getvalue()


def _validation_error_m(validation: dict[str, Any] | None) -> float | None:
    if not isinstance(validation, dict):
        return None
    for key in ("error_m", "errorM", "localization_error_m", "localizationErrorM", "distance_m"):
        if validation.get(key) is not None:
            return float(validation[key])
    true_coord = validation.get("true_fire_world") or validation.get("trueFireWorld")
    observed_coord = validation.get("observed_fire_world") or validation.get("observedFireWorld")
    if isinstance(true_coord, dict) and isinstance(observed_coord, dict):
        tx = float(true_coord.get("x") or true_coord.get("X"))
        ty = float(true_coord.get("y") or true_coord.get("Y"))
        ox = float(observed_coord.get("x") or observed_coord.get("X"))
        oy = float(observed_coord.get("y") or observed_coord.get("Y"))
        return ((tx - ox) ** 2 + (ty - oy) ** 2) ** 0.5
    return None


def _numeric_pair(value: Any, field_name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field_name} must be an array of length 2: {value}")
    return float(value[0]), float(value[1])


async def save_singledrone_fire_image(
    file: UploadFile,
    *,
    task_id: str,
    drone_id: str = "UAV-FIRE-001",
    image_type: str = "global_rgb",
    length_m: Any = None,
    width_m: Any = None,
    side_length_m: Any = None,
) -> dict[str, Any]:
    """Save an uploaded image under examples/singledrone_fire/uploads."""

    content = await file.read()
    if not content:
        raise ValueError("File cannot be empty")
    return _save_singledrone_fire_image_bytes(
        content,
        filename=file.filename,
        content_type=file.content_type,
        task_id=task_id,
        drone_id=drone_id,
        image_type=image_type,
        length_m=length_m,
        width_m=width_m,
        side_length_m=side_length_m,
    )


def _save_singledrone_fire_image_bytes(
    content: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    task_id: str,
    drone_id: str = "UAV-FIRE-001",
    image_type: str = "global_rgb",
    length_m: Any = None,
    width_m: Any = None,
    side_length_m: Any = None,
) -> dict[str, Any]:
    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    if not content:
        raise ValueError("File cannot be empty")

    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and not normalized_content_type.startswith("image/"):
        raise ValueError(f"File type must be an image; current type: {normalized_content_type}")

    try:
        image = Image.open(io.BytesIO(content))
        width, height = image.size
        image.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("The uploaded file is not a valid image") from exc

    side_m = _optional_float(side_length_m)
    image_length_m = _optional_float(length_m)
    image_width_m = _optional_float(width_m)
    if side_m is not None:
        image_length_m = image_length_m if image_length_m is not None else side_m
        image_width_m = image_width_m if image_width_m is not None else side_m

    safe_task_id = _safe_path_component(task_id, "unknown_task")
    safe_drone_id = _safe_path_component(drone_id, "UAV-FIRE-001")
    safe_image_type = _safe_path_component(image_type, "global_rgb")

    original_name = Path(filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_IMAGE_SUFFIXES:
        suffix = _IMAGE_SUFFIX_BY_CONTENT_TYPE.get(normalized_content_type, ".jpg")

    target_dir = SINGLEDRONE_FIRE_UPLOAD_ROOT / safe_task_id / safe_drone_id / safe_image_type
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{safe_image_type}_{timestamp}{suffix}"
    target_path = target_dir / filename
    target_path.write_bytes(content)

    relative_path = target_path.relative_to(REPO_ROOT)
    return {
        "taskId": safe_task_id,
        "droneId": safe_drone_id,
        "imageType": safe_image_type,
        "filename": filename,
        "contentType": normalized_content_type or None,
        "width": width,
        "height": height,
        "pixelSize": _format_size(width, height),
        "lengthM": image_length_m,
        "widthM": image_width_m,
        "physicalSizeM": (
            _format_size(image_length_m, image_width_m)
            if image_length_m is not None and image_width_m is not None
            else None
        ),
        "sizeBytes": len(content),
        "path": str(target_path),
        "relativePath": str(relative_path),
    }


def _save_deliverytask_image_bytes(
    content: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    task_id: str,
    entity_id: str,
    image_type: str = "uav_topdown",
) -> dict[str, Any]:
    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    if not content:
        raise ValueError("File cannot be empty")

    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and not normalized_content_type.startswith("image/"):
        raise ValueError(f"File type must be an image; current type: {normalized_content_type}")

    try:
        image = Image.open(io.BytesIO(content))
        width, height = image.size
        image.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("The uploaded file is not a valid image") from exc

    safe_task_id = _safe_path_component(task_id, "unknown_task")
    safe_entity_id = _safe_path_component(entity_id, "unknown_entity")
    safe_image_type = _safe_path_component(image_type, "uav_topdown")

    original_name = Path(filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_IMAGE_SUFFIXES:
        suffix = _IMAGE_SUFFIX_BY_CONTENT_TYPE.get(normalized_content_type, ".jpg")

    target_dir = DELIVERYTASK_UPLOAD_ROOT / safe_task_id / safe_entity_id / safe_image_type
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{safe_image_type}_{timestamp}{suffix}"
    target_path = target_dir / filename
    target_path.write_bytes(content)

    return {
        "taskId": safe_task_id,
        "entityId": safe_entity_id,
        "imageType": safe_image_type,
        "filename": filename,
        "contentType": normalized_content_type or None,
        "width": width,
        "height": height,
        "pixelSize": _format_size(width, height),
        "sizeBytes": len(content),
        "path": str(target_path),
        "relativePath": str(target_path.relative_to(REPO_ROOT)),
    }


def _save_multiagentstasks_image_bytes(
    content: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    task_id: str,
    entity_id: str,
    image_type: str = "topdown",
) -> dict[str, Any]:
    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    if not content:
        raise ValueError("File cannot be empty")

    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and not normalized_content_type.startswith("image/"):
        raise ValueError(f"File type must be an image; current type: {normalized_content_type}")

    try:
        image = Image.open(io.BytesIO(content))
        width, height = image.size
        image.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("The uploaded file is not a valid image") from exc

    safe_task_id = _safe_path_component(task_id, "unknown_task")
    safe_entity_id = _safe_path_component(entity_id, "unknown_entity")
    safe_image_type = _safe_path_component(image_type, "topdown")

    original_name = Path(filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_IMAGE_SUFFIXES:
        suffix = _IMAGE_SUFFIX_BY_CONTENT_TYPE.get(normalized_content_type, ".jpg")

    target_dir = MULTIAGENTSTASKS_UPLOAD_ROOT / safe_task_id / safe_entity_id / safe_image_type
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    saved_filename = f"{safe_image_type}_{timestamp}{suffix}"
    target_path = target_dir / saved_filename
    target_path.write_bytes(content)

    return {
        "taskId": safe_task_id,
        "entityId": safe_entity_id,
        "imageType": safe_image_type,
        "filename": saved_filename,
        "contentType": normalized_content_type or None,
        "width": width,
        "height": height,
        "pixelSize": _format_size(width, height),
        "sizeBytes": len(content),
        "path": str(target_path),
        "relativePath": str(target_path.relative_to(REPO_ROOT)),
    }


def _save_singledog_image_bytes(
    content: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    task_id: str,
    entity_id: str,
    image_type: str = "front",
) -> dict[str, Any]:
    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    if not content:
        raise ValueError("File cannot be empty")

    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and not normalized_content_type.startswith("image/"):
        raise ValueError(f"File type must be an image; current type: {normalized_content_type}")

    try:
        image = Image.open(io.BytesIO(content))
        width, height = image.size
        image.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("The uploaded file is not a valid image") from exc

    safe_task_id = _safe_path_component(task_id, "unknown_task")
    safe_entity_id = _safe_path_component(entity_id, "UGV-SINGLEDOG-001")
    safe_image_type = _safe_path_component(image_type, "front")

    original_name = Path(filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_IMAGE_SUFFIXES:
        suffix = _IMAGE_SUFFIX_BY_CONTENT_TYPE.get(normalized_content_type, ".jpg")

    target_dir = SINGLEDOG_UPLOAD_ROOT / safe_task_id / safe_entity_id / safe_image_type
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    saved_filename = f"{safe_image_type}_{timestamp}{suffix}"
    target_path = target_dir / saved_filename
    target_path.write_bytes(content)

    return {
        "taskId": safe_task_id,
        "entityId": safe_entity_id,
        "imageType": safe_image_type,
        "filename": saved_filename,
        "contentType": normalized_content_type or None,
        "width": width,
        "height": height,
        "pixelSize": _format_size(width, height),
        "sizeBytes": len(content),
        "path": str(target_path),
        "relativePath": str(target_path.relative_to(REPO_ROOT)),
    }


def _save_bridge_image_bytes(
    content: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    task_id: str,
    entity_id: str,
    image_type: str = "topdown",
) -> dict[str, Any]:
    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    if not content:
        raise ValueError("File cannot be empty")

    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and not normalized_content_type.startswith("image/"):
        raise ValueError(f"File type must be an image; current type: {normalized_content_type}")

    try:
        image = Image.open(io.BytesIO(content))
        width, height = image.size
        image.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("The uploaded file is not a valid image") from exc

    safe_task_id = _safe_path_component(task_id, "unknown_task")
    safe_entity_id = _safe_path_component(entity_id, "UAV-BRIDGE-001")
    safe_image_type = _safe_path_component(image_type, "topdown")

    original_name = Path(filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_IMAGE_SUFFIXES:
        suffix = _IMAGE_SUFFIX_BY_CONTENT_TYPE.get(normalized_content_type, ".jpg")

    target_dir = BRIDGE_UPLOAD_ROOT / safe_task_id / safe_entity_id / safe_image_type
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    saved_filename = f"{safe_image_type}_{timestamp}{suffix}"
    target_path = target_dir / saved_filename
    target_path.write_bytes(content)

    return {
        "taskId": safe_task_id,
        "entityId": safe_entity_id,
        "imageType": safe_image_type,
        "filename": saved_filename,
        "contentType": normalized_content_type or None,
        "width": width,
        "height": height,
        "pixelSize": _format_size(width, height),
        "sizeBytes": len(content),
        "path": str(target_path),
        "relativePath": str(target_path.relative_to(REPO_ROOT)),
    }


def _save_uavdog_image_bytes(
    content: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    task_id: str,
    entity_id: str,
    image_type: str = "topdown",
) -> dict[str, Any]:
    if not str(task_id or "").strip():
        raise ValueError("taskId cannot be empty")
    if not content:
        raise ValueError("File cannot be empty")

    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and not normalized_content_type.startswith("image/"):
        raise ValueError(f"File type must be an image; current type: {normalized_content_type}")

    try:
        image = Image.open(io.BytesIO(content))
        width, height = image.size
        image.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("The uploaded file is not a valid image") from exc

    safe_task_id = _safe_path_component(task_id, "unknown_task")
    safe_entity_id = _safe_path_component(entity_id, "UAV-UAVDOG-001")
    safe_image_type = _safe_path_component(image_type, "topdown")

    original_name = Path(filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_IMAGE_SUFFIXES:
        suffix = _IMAGE_SUFFIX_BY_CONTENT_TYPE.get(normalized_content_type, ".jpg")

    target_dir = UAVDOG_UPLOAD_ROOT / safe_task_id / safe_entity_id / safe_image_type
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    saved_filename = f"{safe_image_type}_{timestamp}{suffix}"
    target_path = target_dir / saved_filename
    target_path.write_bytes(content)

    return {
        "taskId": safe_task_id,
        "entityId": safe_entity_id,
        "imageType": safe_image_type,
        "filename": saved_filename,
        "contentType": normalized_content_type or None,
        "width": width,
        "height": height,
        "pixelSize": _format_size(width, height),
        "sizeBytes": len(content),
        "path": str(target_path),
        "relativePath": str(target_path.relative_to(REPO_ROOT)),
    }


def _data_url_from_bytes(content: bytes, content_type: str) -> str:
    encoded = base64.b64encode(content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def _write_singlefire_result(
    task_id: str,
    drone_id: str,
    result: dict[str, Any],
    raw_response: str,
    global_saved: dict[str, Any],
    topdown_saved: dict[str, Any],
) -> Path:
    task_key = _safe_path_component(task_id, "task")
    results_dir = REPO_ROOT / "examples" / "singledrone_fire" / "results" / task_key
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = results_dir / f"singlefire_{task_key}_{timestamp}.json"
    payload = {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-FIRE-001"),
        "result": result,
        "raw_response": raw_response,
        "savedImages": {
            "global_rgb": global_saved,
            "topdown_rgb": topdown_saved,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def _write_singlefire_error_result(
    task_id: str,
    drone_id: str,
    exc: Exception,
    global_saved: dict[str, Any],
    topdown_saved: dict[str, Any],
) -> Path:
    task_key = _safe_path_component(task_id, "task")
    results_dir = REPO_ROOT / "examples" / "singledrone_fire" / "results" / task_key
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = results_dir / f"singlefire_{task_key}_{timestamp}.json"
    payload = {
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-FIRE-001"),
        "status": "failed",
        "error_type": exc.__class__.__name__,
        "error": str(exc) or exc.__class__.__name__,
        "savedImages": {
            "global_rgb": global_saved,
            "topdown_rgb": topdown_saved,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def _write_bridge_error_result(
    task_id: str,
    drone_id: str,
    step_index: int,
    exc: Exception,
    saved: dict[str, Any],
) -> Path:
    task_key = _safe_path_component(task_id, "task")
    results_dir = BRIDGE_RESULTS_ROOT / task_key
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = results_dir / f"bridge_inspection_error_{task_key}_{timestamp}.json"
    payload = {
        "type": "bridge_inspection_error",
        "taskId": _safe_path_component(task_id, "unknown_task"),
        "droneId": _safe_path_component(drone_id, "UAV-BRIDGE-001"),
        "stepIndex": step_index,
        "status": "failed",
        "error_type": exc.__class__.__name__,
        "error": str(exc) or exc.__class__.__name__,
        "savedImage": saved,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


async def dispatch_singledrone_fire_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch the examples/singledrone_fire scenario to LJ-ENGINE clients."""

    from app.modules.envs.scenario import ScenarioSpec
    from app.modules.envs.task_id import make_task_id
    from examples.singledrone_fire.scenario import build_single_drone_fire_scenario

    task_id = str(
        payload.get("taskId")
        or payload.get("task_id")
        or make_task_id(prefix="singledrone_fire")
    )
    command_type = "resetScenario"
    engine_session_key, broadcast, dry_run, require_ack, timeout_sec = _route_options(
        {**payload, "requireAck": payload.get("requireAck", payload.get("require_ack", True))}
    )
    if engine_session_key and not broadcast:
        target_keys, targets = _connected_engine_targets(engine_session_key)
    elif engine_session_key and broadcast:
        target_keys, targets = _connected_engine_targets(engine_session_key)
    else:
        target_keys, targets = _connected_engine_targets()

    scenario_payload = payload.get("scenario")
    if isinstance(scenario_payload, dict):
        spec = ScenarioSpec.from_obj(scenario_payload)
    else:
        spec = ScenarioSpec.from_definition(build_single_drone_fire_scenario())
    spec.task_id = task_id
    command = {
        "commandType": command_type,
        "taskId": task_id,
        "scenario": spec.to_engine_payload(),
    }
    result: dict[str, Any] = {
        "taskId": task_id,
        "commandType": command_type,
        "targets": target_keys,
        "targetCount": len(targets),
        "requiresAck": require_ack,
        "dryRun": dry_run,
        "command": command,
    }
    if dry_run:
        result["status"] = "dry_run"
        return result
    if not targets:
        raise RuntimeError("LJ-ENGINE is not connected; cannot dispatch the scenario")

    if require_ack:
        result["response"] = await realtime_manager.request_to_engine(
            command,
            timeout=timeout_sec,
            targets=targets,
        )
    else:
        await realtime_manager.send_command_to_engine(command, targets=targets)
        result["response"] = {"status": "sent"}
    result["status"] = "sent"
    return result


def _build_airsim_action_command(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("command"), dict):
        command = dict(payload["command"])
    elif isinstance(payload.get("dronesAction"), list) or isinstance(payload.get("drones_action"), list):
        command = {key: value for key, value in payload.items() if key not in _ROUTING_KEYS}
        if "drones_action" in command and "dronesAction" not in command:
            command["dronesAction"] = command.pop("drones_action")
    else:
        task_id = str(payload.get("taskId") or payload.get("task_id") or "")
        if not task_id:
            raise ValueError("taskId cannot be empty")
        drone_id = payload.get("dronesId") or payload.get("droneId") or "UAV-FIRE-001"
        instruction_type = str(payload.get("instructionType") or payload.get("instruction_type") or "takeoff")
        action_command = payload.get("actionCommand") or payload.get("action_command")
        if not isinstance(action_command, dict):
            if instruction_type in {"setDestination", "setDestinationLoc"}:
                action_command = {
                    "x": _float_from_payload(payload, "x", "X", default=0.0),
                    "y": _float_from_payload(payload, "y", "Y", default=0.0),
                }
                if payload.get("z") is not None or payload.get("Z") is not None:
                    action_command["z"] = _float_from_payload(payload, "z", "Z", default=0.0)
            else:
                action_command = {
                    "mile": _float_from_payload(payload, "mile", default=200.0),
                    "raw": _float_from_payload(payload, "raw", default=0.0),
                    "speed": _float_from_payload(payload, "speed", default=20.0),
                }
        command = {
            "commandType": str(payload.get("commandType") or "executeAction"),
            "taskId": task_id,
            "dronesAction": [
                {
                    "dronesId": drone_id,
                    "instructionType": instruction_type,
                    "command": action_command,
                }
            ],
        }

    command.setdefault("commandType", "executeAction")
    if not command.get("taskId") and payload.get("task_id"):
        command["taskId"] = payload["task_id"]
    if not command.get("taskId"):
        raise ValueError("taskId cannot be empty")
    if not isinstance(command.get("dronesAction"), list) or not command["dronesAction"]:
        raise ValueError("dronesAction cannot be empty")
    return command


async def dispatch_airsim_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a raw AirSim executeAction command to LJ-ENGINE clients."""

    engine_session_key, broadcast, dry_run, require_ack, timeout_sec = _route_options(payload)
    if not engine_session_key:
        engine_session_key = "LJ-ENGINE_airsim"
        broadcast = False
    wait_execution_completed = _bool_from_payload(
        payload, "waitExecutionCompleted", "wait_execution_completed", default=False
    )
    execution_timeout_sec = _float_from_payload(
        payload,
        "executionTimeoutSec",
        "execution_timeout_sec",
        default=max(timeout_sec, 30.0),
    )
    execution_timeout: float | None = None if execution_timeout_sec <= 0 else float(execution_timeout_sec)
    if engine_session_key and not broadcast:
        target_keys, targets = _connected_engine_targets(engine_session_key)
    elif engine_session_key and broadcast:
        target_keys, targets = _connected_engine_targets(engine_session_key)
    else:
        target_keys, targets = _connected_engine_targets()

    command = _build_airsim_action_command(payload)
    result: dict[str, Any] = {
        "taskId": command.get("taskId"),
        "commandType": command.get("commandType"),
        "targets": target_keys,
        "targetCount": len(targets),
        "requiresAck": require_ack,
        "dryRun": dry_run,
        "command": command,
    }
    if dry_run:
        result["status"] = "dry_run"
        return result
    if not targets:
        raise RuntimeError("LJ-ENGINE is not connected; cannot dispatch the action")

    drone_id = None
    first_action = command["dronesAction"][0]
    if isinstance(first_action, dict):
        drone_id = first_action.get("dronesId") or first_action.get("droneId")
    wait_drone_id = payload.get("waitDroneId") or payload.get("wait_drone_id") or drone_id
    completion_task = None
    if wait_execution_completed:
        completion_task = asyncio.create_task(
            realtime_manager.wait_for_engine_event(
                "executionCompleted",
                filters={"droneId": str(wait_drone_id)} if wait_drone_id is not None else {},
                session_key=engine_session_key,
                timeout=execution_timeout,
            )
        )

    if require_ack:
        try:
            result["response"] = await realtime_manager.request_to_engine(
                command,
                timeout=timeout_sec,
                targets=targets,
            )
        except Exception:
            if completion_task is not None:
                completion_task.cancel()
            raise
    else:
        try:
            await realtime_manager.send_command_to_engine(command, targets=targets)
        except Exception:
            if completion_task is not None:
                completion_task.cancel()
            raise
        result["response"] = {"status": "sent"}
    if completion_task is not None:
        result["executionCompleted"] = await completion_task
    result["status"] = "sent"
    return result


async def dispatch_airsim_set_destination(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch an AirSim fixed UE-coordinate command to a single AirSim engine session."""

    normalized = {
        **payload,
        "instructionType": "setDestinationLoc",
        "engineSessionKey": payload.get("engineSessionKey")
        or payload.get("engine_session_key")
        or "LJ-ENGINE_airsim",
        "broadcast": False,
    }
    return await dispatch_airsim_action(normalized)


async def dispatch_fire_recognition_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Broadcast a fire-recognition result and optionally wait for validation."""

    task_id = str(payload.get("taskId") or payload.get("task_id") or "")
    if not task_id:
        raise ValueError("taskId cannot be empty")
    drone_id = str(payload.get("droneId") or payload.get("drone_id") or "UAV-FIRE-001")
    recognition = payload.get("recognition")
    if not isinstance(recognition, dict):
        recognition = {}
    status = str(payload.get("status") or ("stop" if recognition.get("fire_detected") else "continue"))
    offset = payload.get("offset") or recognition.get("offset_from_center_m") or [0, 0]
    if status == "stop":
        offset = recognition.get("offset_from_center_m") or offset or [0, 0]
    _numeric_pair(offset, "offset")

    engine_session_key = str(
        payload.get("engineSessionKey") or payload.get("engine_session_key") or "LJ-ENGINE_airsim"
    )
    dry_run = _bool_from_payload(payload, "dryRun", "dry_run", default=False)
    wait_validation = _bool_from_payload(payload, "waitValidation", "wait_validation", default=True)
    validation_timeout_sec = _float_from_payload(
        payload,
        "validationTimeoutSec",
        "validation_timeout_sec",
        default=60.0,
    )
    command = {
        "commandType": "fireRecognitionResult",
        "taskId": task_id,
        "droneId": drone_id,
        "status": status,
        "offset": offset,
        "recognition": recognition,
        "firePixelCoord": recognition.get("fire_pixel_coord"),
        "offsetFromCenterM": recognition.get("offset_from_center_m"),
    }
    target_keys, targets = _connected_engine_targets(engine_session_key)
    result: dict[str, Any] = {
        "taskId": task_id,
        "commandType": command["commandType"],
        "targets": target_keys,
        "targetCount": len(targets),
        "ueBroadcast": True,
        "waitValidation": wait_validation,
        "dryRun": dry_run,
        "command": command,
    }
    if dry_run:
        result["status"] = "dry_run"
        return result
    if not targets:
        raise RuntimeError(f"{engine_session_key} is not connected; cannot report the fire-spot recognition result")

    validation_task = None
    if wait_validation:
        validation_task = asyncio.create_task(
            realtime_manager.wait_for_engine_event(
                "fireValidationResult",
                filters={"taskId": task_id},
                timeout=float(validation_timeout_sec),
            )
        )
    try:
        await realtime_manager.send_command_to_engine(command, targets=targets)
        await realtime_manager.send_by_user_type({"type": "COMMAND", "data": command}, "LJ-UE")
    except Exception:
        if validation_task is not None:
            validation_task.cancel()
        raise
    result["status"] = "sent"
    if validation_task is not None:
        validation = await validation_task
        result["validation"] = validation
        result["validation_error_m"] = _validation_error_m(validation)
    return result


async def dispatch_singlefire_analysis_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Send selected singlefire LLM fields to UE and AirSim."""

    task_id = str(payload.get("taskId") or payload.get("task_id") or "")
    if not task_id:
        raise ValueError("taskId cannot be empty")
    drone_id = str(payload.get("droneId") or payload.get("drone_id") or "UAV-FIRE-001")
    source = payload.get("result")
    if not isinstance(source, dict):
        source = payload

    llm_result = {
        "thought_process": source.get("thought_process"),
        "status": source.get("status"),
        "fire_detected": source.get("fire_detected"),
        "target_visible": source.get("target_visible"),
        "coord_frame": source.get("coord_frame"),
        "fire_pixel_coord": source.get("fire_pixel_coord"),
        "fire_offset_px": source.get("fire_offset_px"),
        "target_pixel_coord": source.get("target_pixel_coord"),
        "current_coord": source.get("current_coord"),
        "action_offset_px": source.get("action_offset_px"),
        "reason": source.get("reason"),
    }
    _validate_singlefire_result(llm_result)

    engine_session_key = str(
        payload.get("engineSessionKey") or payload.get("engine_session_key") or "LJ-ENGINE_airsim"
    )
    dry_run = _bool_from_payload(payload, "dryRun", "dry_run", default=False)
    command = {
        "commandType": "singlefireAnalysisResult",
        "taskId": task_id,
        "droneId": drone_id,
        **llm_result,
    }
    target_keys, targets = _connected_engine_targets(engine_session_key)
    result: dict[str, Any] = {
        "taskId": task_id,
        "commandType": command["commandType"],
        "targets": target_keys,
        "targetCount": len(targets),
        "ueBroadcast": True,
        "dryRun": dry_run,
        "command": command,
    }
    if dry_run:
        result["status"] = "dry_run"
        return result
    if not targets:
        raise RuntimeError(f"{engine_session_key} is not connected; cannot send the singlefire analysis result")

    await realtime_manager.send_command_to_engine(command, targets=targets)
    await realtime_manager.send_by_user_type({"type": "COMMAND", "data": command}, "LJ-UE")
    result["status"] = "sent"
    result["response"] = {"status": "sent"}
    return result


async def uav_route_plan(file: UploadFile, map_file: UploadFile) -> dict[str, Any]:
    """Plan routes by executing the `uav_route_plan` LangGraph task."""

    image_base64 = await file_to_base64(file)
    map_base64 = await crop_to_base64(map_file)
    result = await invoke_agent(
        "uav_route_plan",
        {
            "image_base64": image_base64,
            "map_base64": map_base64,
            "metadata": {"source": "sim/uav/route/plan"},
        },
    )
    return result.get("route_plan", {})


async def uav_takeoff(request: dict[str, Any]) -> None:
    """Compatibility wrapper for UAV takeoff/control commands."""

    payload = dict(request)
    payload.setdefault("engineSessionKey", "LJ-ENGINE_airsim")
    payload["broadcast"] = False
    await dispatch_airsim_action(payload)


async def dispatch_command(request: dict[str, Any]) -> None:
    """Forward an arbitrary command to the requested WebSocket user type."""

    user_type = request.get("userType") or request.get("user_type")
    command = request.get("command")
    await realtime_manager.send_by_user_type({"type": "COMMAND", "data": command}, user_type)
