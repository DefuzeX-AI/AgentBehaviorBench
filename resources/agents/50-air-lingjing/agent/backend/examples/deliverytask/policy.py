"""LLM policies for the delivery task example."""

from __future__ import annotations

import base64
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from app.modules.ai.service import analysis as ai_analysis
from app.modules.ai.service import parse_model_json

CASE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = CASE_DIR / "prompts"
RESULTS_DIR = CASE_DIR / "results"
FIXED_DOG_PLAN_HEIGHT_M = 280.0


def _safe_component(value: str | None, default: str = "unknown") -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "").strip())
    return (safe.strip("._") or default)[:120]


def _load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"prompt is empty: {path}")
    return text


def _image_to_data_url(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"image does not exist: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('utf-8')}"


def _numeric_pair(value: Any, field: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field} must be an array of length 2: {value}")
    return [float(value[0]), float(value[1])]


def validate_traffic_inspection_result(result: dict[str, Any]) -> dict[str, Any]:
    required = {
        "status",
        "road_visible",
        "obstacle_detected",
        "confidence",
        "obstacle_pixel_coord",
        "obstruction_offset_px",
        "blocked_route_point",
        "reason",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"delivery route-inspection image-analysis output is missing fields {missing}: {result}")
    if result["status"] not in {"clear", "blocked", "uncertain"}:
        raise ValueError(f"status can only be clear/blocked/uncertain: {result}")
    if not isinstance(result["road_visible"], bool):
        raise ValueError(f"road_visible must be a JSON boolean: {result}")
    if not isinstance(result["obstacle_detected"], bool):
        raise ValueError(f"obstacle_detected must be a JSON boolean: {result}")
    confidence = float(result["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0 and 1: {result}")
    result["confidence"] = confidence
    if result["obstacle_pixel_coord"] is not None:
        result["obstacle_pixel_coord"] = _numeric_pair(result["obstacle_pixel_coord"], "obstacle_pixel_coord")
    if result["obstruction_offset_px"] is not None:
        result["obstruction_offset_px"] = _numeric_pair(result["obstruction_offset_px"], "obstruction_offset_px")
    if result["status"] == "blocked":
        result["obstacle_detected"] = True
        if result["obstacle_pixel_coord"] is None:
            raise ValueError(f"when status=blocked, obstacle_pixel_coord cannot be empty: {result}")
    if result["status"] == "clear":
        result["obstacle_detected"] = False
        result["obstacle_pixel_coord"] = None
        result["obstruction_offset_px"] = None
    return result


def validate_dog_target_house_result(result: dict[str, Any]) -> dict[str, Any]:
    required = {
        "target_house_visible",
        "confidence",
        "target_pixel_coord",
        "navigation_hint",
        "arrived",
        "reason",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"robot dog target-house image-analysis output is missing fields {missing}: {result}")
    if not isinstance(result["target_house_visible"], bool):
        raise ValueError(f"target_house_visible must be a JSON boolean: {result}")
    confidence = float(result["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0 and 1: {result}")
    result["confidence"] = confidence
    if result["target_pixel_coord"] is not None:
        result["target_pixel_coord"] = _numeric_pair(result["target_pixel_coord"], "target_pixel_coord")
    if result["navigation_hint"] not in {
        "forward",
        "left",
        "right",
        "search_left",
        "search_right",
        "arrived",
        "unknown",
    }:
        raise ValueError(f"navigation_hint is invalid: {result}")
    if not isinstance(result["arrived"], bool):
        raise ValueError(f"arrived must be a JSON boolean: {result}")
    if result["arrived"]:
        result["target_house_visible"] = True
        result["navigation_hint"] = "arrived"
    return result


def validate_uav_dog_path_plan_result(result: dict[str, Any]) -> dict[str, Any]:
    required = {
        "dog_visible",
        "target_visible",
        "need_altitude_increase",
        "altitude_delta_m",
        "confidence",
        "waypoints",
        "reason",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"UAV-for-robot-dog path-planning output is missing fields {missing}: {result}")
    if not isinstance(result["dog_visible"], bool):
        raise ValueError(f"dog_visible must be a JSON boolean: {result}")
    if not isinstance(result["target_visible"], bool):
        raise ValueError(f"target_visible must be a JSON boolean: {result}")
    if not isinstance(result["need_altitude_increase"], bool):
        raise ValueError(f"need_altitude_increase must be a JSON boolean: {result}")
    result["need_altitude_increase"] = False
    result["altitude_delta_m"] = 0.0
    confidence = float(result["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0 and 1: {result}")
    result["confidence"] = confidence
    waypoints = result.get("waypoints")
    if not result["dog_visible"] or not result["target_visible"]:
        result["waypoints"] = []
        return result
    result["need_altitude_increase"] = False
    result["altitude_delta_m"] = 0.0
    if not isinstance(waypoints, list) or not 1 <= len(waypoints) <= 6:
        raise ValueError(f"when target_visible=true, waypoints must contain 1 to 6 intersection offset points: {result}")
    normalized = []
    for index, waypoint in enumerate(waypoints, start=1):
        if not isinstance(waypoint, dict):
            raise ValueError(f"waypoints[{index}] must be a JSON object: {result}")
        offset = waypoint.get("targetOffsetPx")
        if offset is None:
            offset = waypoint.get("target_offset_px")
        target_offset_px = _numeric_pair(offset, f"waypoints[{index}].targetOffsetPx")
        normalized.append(
            {
                "targetOffsetPx": target_offset_px,
                "uavHeightM": FIXED_DOG_PLAN_HEIGHT_M,
            }
        )
    result["waypoints"] = normalized
    return result


async def analyze_uav_traffic_image(
    *,
    task_id: str,
    drone_id: str,
    image_path: Path,
    route_point_index: int,
    route_point: dict[str, Any] | None,
) -> dict[str, Any]:
    """Analyze one UAV topdown image for route blockage."""

    prompt = _load_prompt("uav_traffic_inspection.txt")
    context = {
        "taskId": task_id,
        "droneId": drone_id,
        "routePointIndex": route_point_index,
        "routePoint": route_point,
    }
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "text", "text": f"Current route inspection context: {json.dumps(context, ensure_ascii=False)}"},
                {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path), "detail": "high"}},
            ],
        }
    ]
    raw_response = await ai_analysis(messages)
    result = validate_traffic_inspection_result(parse_model_json(raw_response))
    if result.get("status") == "blocked" and result.get("blocked_route_point") is None:
        result["blocked_route_point"] = route_point
    result_path = write_policy_result(
        task_id,
        {
            "type": "uav_traffic_inspection",
            "taskId": task_id,
            "droneId": drone_id,
            "routePointIndex": route_point_index,
            "routePoint": route_point,
            "imagePath": str(image_path),
            "raw_response": raw_response,
            "result": result,
        },
    )
    return {
        "result": result,
        "raw_response": raw_response,
        "result_path": str(result_path),
    }


async def analyze_dog_target_house_images(
    *,
    task_id: str,
    dog_id: str,
    front_image_path: Path,
    target_image_paths: list[Path],
    step_index: int = 0,
) -> dict[str, Any]:
    """Analyze dog front-view image against the target-house reference photo."""

    prompt = _load_prompt("dog_target_house.txt")
    context = {
        "taskId": task_id,
        "dogId": dog_id,
        "stepIndex": step_index,
        "imageOrder": ["target_house_reference_images", "dog_current_view"],
    }
    content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": f"Dog target-house context: {json.dumps(context, ensure_ascii=False)}"},
    ]
    for index, path in enumerate(target_image_paths, start=1):
        content.append({"type": "text", "text": f"Reference image {index}: target house reference ({path.name})."})
        content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(path), "detail": "high"}})
    content.extend(
        [
            {"type": "text", "text": "Current image: dog camera image after walking the planned route."},
            {"type": "image_url", "image_url": {"url": _image_to_data_url(front_image_path), "detail": "high"}},
        ]
    )
    messages = [
        {
            "role": "user",
            "content": content,
        }
    ]
    raw_response = await ai_analysis(messages)
    result = validate_dog_target_house_result(parse_model_json(raw_response))
    result_path = write_policy_result(
        task_id,
        {
            "type": "dog_target_house",
            "taskId": task_id,
            "dogId": dog_id,
            "stepIndex": step_index,
            "frontImagePath": str(front_image_path),
            "targetImagePaths": [str(path) for path in target_image_paths],
            "raw_response": raw_response,
            "result": result,
        },
    )
    return {
        "result": result,
        "raw_response": raw_response,
        "result_path": str(result_path),
    }


async def analyze_uav_dog_path_plan_image(
    *,
    task_id: str,
    drone_id: str,
    image_path: Path,
    reference_image_path: Path,
    step_index: int = 0,
    current_height_m: float | None = None,
) -> dict[str, Any]:
    """Analyze UAV topdown image against the target topdown reference."""

    prompt = _load_prompt("uav_dog_path_planning.txt")
    context = {
        "taskId": task_id,
        "droneId": drone_id,
        "stepIndex": step_index,
        "dogStart": "image_center",
        "currentUavHeightM": current_height_m,
        "imageOrder": ["target_house_topdown_reference", "current_uav_topdown"],
    }
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "text", "text": f"UAV dog-path planning context: {json.dumps(context, ensure_ascii=False)}"},
                {"type": "text", "text": "Image 1: target house UAV topdown reference image."},
                {"type": "image_url", "image_url": {"url": _image_to_data_url(reference_image_path), "detail": "high"}},
                {"type": "text", "text": "Image 2: current UAV topdown image. Plan the dog route in this image."},
                {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path), "detail": "high"}},
            ],
        }
    ]
    raw_response = await ai_analysis(messages)
    result = validate_uav_dog_path_plan_result(parse_model_json(raw_response))
    result_path = write_policy_result(
        task_id,
        {
            "type": "uav_dog_path_planning",
            "taskId": task_id,
            "droneId": drone_id,
            "stepIndex": step_index,
            "currentUavHeightM": current_height_m,
            "referenceImagePath": str(reference_image_path),
            "imagePath": str(image_path),
            "raw_response": raw_response,
            "result": result,
        },
    )
    return {
        "result": result,
        "raw_response": raw_response,
        "result_path": str(result_path),
    }


def write_policy_result(task_id: str, payload: dict[str, Any]) -> Path:
    task_dir = RESULTS_DIR / _safe_component(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = task_dir / f"{payload.get('type', 'policy')}_{_safe_component(task_id)}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
