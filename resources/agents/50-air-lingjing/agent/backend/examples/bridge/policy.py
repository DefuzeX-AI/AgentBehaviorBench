"""LLM policy for UAV bridge fracture inspection."""

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

VALID_STATUS = {"approach", "inspect", "completed", "failed"}


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


VALID_INSTRUCTION = {"forward", "left", "right", "stop"}
_INSTRUCTION_SYNONYMS = {
    "forward": "forward", "go_forward": "forward", "ahead": "forward", "move_forward": "forward", "fwd": "forward",
    "left": "left", "turn_left": "left", "rotate_left": "left",
    "right": "right", "turn_right": "right", "rotate_right": "right",
    "stop": "stop", "hover": "stop", "hold": "stop", "stay": "stop", "none": "stop",
}


def _norm_instruction(value: Any) -> str:
    key = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _INSTRUCTION_SYNONYMS.get(key, "stop")


def validate_bridge_result(result: dict[str, Any]) -> dict[str, Any]:
    """Validate the top-down bridge policy output.

    The drone is driven by **direct directional commands** (forward/left/right/stop), NOT absolute
    setDestination coordinates. The model treats image-up as the drone's forward heading and returns the
    next single action: turn to face the bridge/sea, fly forward to approach/inspect, or stop at a fracture.
    """
    required = {"status", "bridge_visible", "fracture_detected", "confidence", "instructionType", "reason"}
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"bridge image-analysis output is missing fields {missing}: {result}")
    if result["status"] not in VALID_STATUS:
        raise ValueError(f"status can only be approach/inspect/completed/failed: {result}")
    if not isinstance(result["bridge_visible"], bool):
        raise ValueError(f"bridge_visible must be a JSON boolean: {result}")
    if not isinstance(result["fracture_detected"], bool):
        raise ValueError(f"fracture_detected must be a JSON boolean: {result}")
    result["confidence"] = float(result["confidence"])
    if not 0.0 <= result["confidence"] <= 1.0:
        raise ValueError(f"confidence must be between 0 and 1: {result}")

    # Normalize the directional action (tolerant to synonyms / missing numeric fields).
    it = _norm_instruction(result.get("instructionType"))
    mile = result.get("mile")
    raw = result.get("raw")
    speed = result.get("speed")
    result["mile"] = float(mile) if isinstance(mile, (int, float)) else 0.0
    result["raw"] = float(raw) if isinstance(raw, (int, float)) else 0.0
    result["speed"] = float(speed) if isinstance(speed, (int, float)) else 20.0

    if result["fracture_detected"]:
        result["status"] = "completed"
        result["bridge_visible"] = True
        it = "stop"
        result["mile"] = 0.0
        result["raw"] = 0.0
    else:
        if result["status"] == "completed":
            raise ValueError(f"when status=completed, fracture_detected must be true: {result}")
        # "inspect" means close to a visible bridge; "approach" may be a search step toward the sea
        # while the bridge is NOT yet in frame, so only require visibility for inspect.
        if result["status"] == "inspect" and not result["bridge_visible"]:
            raise ValueError(f"when status=inspect, bridge_visible must be true: {result}")
    result["instructionType"] = it
    return result


async def analyze_bridge_topdown_image(
    *,
    task_id: str,
    drone_id: str,
    image_path: Path,
    step_index: int = 0,
    topdown_length_m: float | None = None,
    topdown_width_m: float | None = None,
    memo: str = "",
) -> dict[str, Any]:
    """Analyze one UAV topdown image for bridge fracture and next movement."""

    prompt = _load_prompt("bridge_inspection.txt")
    context = {
        "taskId": task_id,
        "droneId": drone_id,
        "stepIndex": step_index,
        "topdownLengthM": topdown_length_m,
        "topdownWidthM": topdown_width_m,
        "imageOrder": ["current_uav_topdown"],
    }
    content = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": f"Bridge inspection context: {json.dumps(context, ensure_ascii=False)}"},
    ]
    if str(memo or "").strip():
        content.append({"type": "text", "text": f"Flight memory (use it to keep a consistent heading and NOT search the reverse direction): {memo}"})
    content.append({"type": "text", "text": "Current image: UAV topdown bridge inspection view."})
    content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(image_path), "detail": "high"}})
    messages = [{"role": "user", "content": content}]
    raw_response = await ai_analysis(messages)
    result = validate_bridge_result(parse_model_json(raw_response))
    result_path = write_policy_result(
        task_id,
        {
            "type": "bridge_inspection",
            "taskId": task_id,
            "droneId": drone_id,
            "stepIndex": step_index,
            "imagePath": str(image_path),
            "inputMetadata": {
                "topdownLengthM": topdown_length_m,
                "topdownWidthM": topdown_width_m,
            },
            "raw_response": raw_response,
            "result": result,
        },
    )
    return {
        "result": result,
        "raw_response": raw_response,
        "result_path": str(result_path),
    }


VALID_BEARING = {"left", "center", "right"}


def validate_front_result(result: dict[str, Any]) -> dict[str, Any]:
    required = {"visible", "bearing", "confidence", "reason"}
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"bridge front-view output is missing fields {missing}: {result}")
    if not isinstance(result["visible"], bool):
        raise ValueError(f"visible must be a JSON boolean: {result}")
    bearing = str(result.get("bearing") or "center").strip().lower()
    if bearing not in VALID_BEARING:
        bearing = "center"
    result["bearing"] = bearing
    result["confidence"] = float(result["confidence"])
    if not 0.0 <= result["confidence"] <= 1.0:
        raise ValueError(f"confidence must be between 0 and 1: {result}")
    return result


async def analyze_bridge_front_view(
    *,
    task_id: str,
    drone_id: str,
    image_path: Path,
    step_index: int = 0,
    memo: str = "",
) -> dict[str, Any]:
    """Analyze one UAV front view to decide the sea/bridge search direction when the top-down view lost the bridge."""

    prompt = _load_prompt("bridge_front.txt")
    context = {
        "taskId": task_id,
        "droneId": drone_id,
        "stepIndex": step_index,
        "imageOrder": ["current_uav_front"],
    }
    content = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": f"Bridge front-view context: {json.dumps(context, ensure_ascii=False)}"},
    ]
    if str(memo or "").strip():
        content.append({"type": "text", "text": f"Flight memory (use it to keep a consistent scan direction and NOT search the reverse way): {memo}"})
    content.append({"type": "text", "text": "Current image: UAV forward-facing view along the heading."})
    content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(image_path), "detail": "high"}})
    messages = [{"role": "user", "content": content}]
    raw_response = await ai_analysis(messages)
    result = validate_front_result(parse_model_json(raw_response))
    result_path = write_policy_result(
        task_id,
        {
            "type": "bridge_front",
            "taskId": task_id,
            "droneId": drone_id,
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

