"""LLM policy for UAV-guided dog path planning."""

from __future__ import annotations

import base64
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from app.modules.ai.service import analysis as ai_analysis
from app.modules.ai.service import parse_model_json
from examples.uavdog.scenario import DOG_DEF, UAV_DEF, UAV_HEIGHT_M

CASE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = CASE_DIR / "prompts"
RESULTS_DIR = CASE_DIR / "results"


def _safe_component(value: str | None, default: str = "unknown") -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "").strip())
    return (safe.strip("._") or default)[:120]


def _load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"prompt is empty: {path}")
    return text


def collision_context_path(task_id: str) -> Path:
    return RESULTS_DIR / _safe_component(task_id) / "collision_context.json"


def load_collision_context(task_id: str, step_index: int) -> dict[str, Any] | None:
    path = collision_context_path(task_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "hasCollision": True,
            "nextStepIndex": step_index,
            "instruction": "A collision context file exists but failed to parse; please carefully avoid the area of the path that was suspected to fail in the previous round.",
        }
    if int(payload.get("nextStepIndex") or -1) != int(step_index):
        return None
    payload["contextPath"] = str(path)
    return payload


def _image_to_data_url(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"image does not exist: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('utf-8')}"


def _numeric_pair(value: Any, field: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field} must be an array of length 2: {value}")
    return [float(value[0]), float(value[1])]


def validate_uavdog_path_plan_result(result: dict[str, Any]) -> dict[str, Any]:
    required = {
        "status",
        "arrived",
        "dog_visible",
        "dog_heading_visible",
        "target_visible",
        "collision_replan",
        "confidence",
        "dog_pixel_coord",
        "target_pixel_coord",
        "waypoints",
        "reason",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"uavdog path-planning output is missing fields {missing}: {result}")

    if result["status"] not in {"continue", "completed", "failed"}:
        raise ValueError(f"status can only be continue/completed/failed: {result}")
    for field in ("arrived", "dog_visible", "dog_heading_visible", "target_visible", "collision_replan"):
        if not isinstance(result[field], bool):
            raise ValueError(f"{field} must be a JSON boolean: {result}")

    confidence = float(result["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0 and 1: {result}")
    result["confidence"] = confidence

    if result["dog_visible"]:
        result["dog_pixel_coord"] = _numeric_pair(result["dog_pixel_coord"], "dog_pixel_coord")
    else:
        result["dog_pixel_coord"] = None
    if result["target_visible"]:
        result["target_pixel_coord"] = _numeric_pair(result["target_pixel_coord"], "target_pixel_coord")
    else:
        result["target_pixel_coord"] = None

    if result["arrived"]:
        result["status"] = "completed"
        result["waypoints"] = []
        return result

    if not result["dog_visible"] or not result["target_visible"]:
        result["status"] = "failed"
        result["waypoints"] = []
        return result

    waypoints = result.get("waypoints")
    if result["status"] == "continue":
        if not isinstance(waypoints, list) or len(waypoints) != 1:
            raise ValueError(f"when status=continue, waypoints must contain exactly 1 offset point centered on the current dog position: {result}")
        normalized: list[dict[str, Any]] = []
        for index, waypoint in enumerate(waypoints, start=1):
            if not isinstance(waypoint, dict):
                raise ValueError(f"waypoints[{index}] must be a JSON object: {result}")
            offset = waypoint.get("targetOffsetPx")
            if offset is None:
                offset = waypoint.get("target_offset_px")
            normalized.append(
                {
                    "targetOffsetPx": _numeric_pair(offset, f"waypoints[{index}].targetOffsetPx"),
                    "uavHeightM": UAV_HEIGHT_M,
                }
            )
        result["waypoints"] = normalized
    else:
        result["waypoints"] = []
    return result


async def analyze_uavdog_path_plan_image(
    *,
    task_id: str,
    drone_id: str,
    dog_id: str,
    image_path: Path,
    step_index: int,
    current_height_m: float | None = None,
    collision_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze one UAV topdown image and plan dog route waypoints."""

    prompt = _load_prompt("uavdog_path_planning.txt")
    context = {
        "taskId": task_id,
        "droneId": drone_id,
        "dogId": dog_id,
        "stepIndex": step_index,
        "uavHeightM": current_height_m or UAV_HEIGHT_M,
        "uavDefinition": UAV_DEF,
        "dogDefinition": DOG_DEF,
        "collisionContext": collision_context or {},
        "imageOrder": ["current_uav_topdown"],
    }
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "text", "text": f"UAV-dog planning context: {json.dumps(context, ensure_ascii=False)}"},
                {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path), "detail": "high"}},
            ],
        }
    ]
    raw_response = await ai_analysis(messages)
    result = validate_uavdog_path_plan_result(parse_model_json(raw_response))
    result_path = write_policy_result(
        task_id,
        {
            "type": "uavdog_path_planning",
            "taskId": task_id,
            "droneId": drone_id,
            "dogId": dog_id,
            "stepIndex": step_index,
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
