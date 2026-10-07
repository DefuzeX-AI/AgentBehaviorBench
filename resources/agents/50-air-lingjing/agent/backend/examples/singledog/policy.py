"""LLM policy for the single-dog visual navigation example."""

from __future__ import annotations

import base64
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from app.modules.ai.service import analysis as ai_analysis
from app.modules.ai.service import parse_model_json
from examples.singledog.scenario import SUBTASKS

CASE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = CASE_DIR / "prompts"
REFERENCE_DIR = CASE_DIR / "reference_images"
LEGACY_IMAGE_DIR = CASE_DIR / "image"
RESULTS_DIR = CASE_DIR / "results"

VALID_STATUS = {"continue", "finished", "blocked"}
VALID_INSTRUCTION_TYPES = {"forward", "left", "right", "stop"}


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


def _reference_image_for_subtask(subtask_index: int) -> Path | None:
    names = [
        f"subtask{subtask_index}.png",
        f"subtask{subtask_index}.jpg",
        f"subtask{subtask_index}.jpeg",
        f"subtask{subtask_index}.webp",
        f"reference{subtask_index}.png",
        f"reference{subtask_index}.jpg",
        f"figure{subtask_index}.png",
        f"figure{subtask_index}.jpg",
    ]
    for name in names:
        path = REFERENCE_DIR / name
        if path.exists():
            return path
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        path = LEGACY_IMAGE_DIR / f"{subtask_index}{suffix}"
        if path.exists():
            return path
    return None


def subtask_instruction(subtask_index: int) -> str:
    if subtask_index < 1 or subtask_index > len(SUBTASKS):
        raise ValueError(f"subtaskIndex must be between 1 and {len(SUBTASKS)}, current value is {subtask_index}")
    return SUBTASKS[subtask_index - 1]


def validate_navigation_result(result: dict[str, Any], *, subtask_index: int) -> dict[str, Any]:
    required = {
        "subtask_index",
        "task_finished",
        "status",
        "instructionType",
        "mile",
        "raw",
        "speed",
        "reference_matched",
        "obstacle_detected",
        "confidence",
        "reason",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"singledog navigation output is missing fields {missing}: {result}")
    result["subtask_index"] = int(result["subtask_index"])
    if result["subtask_index"] != subtask_index:
        raise ValueError(f"LLM output subtask_index does not match the current subtask: expected={subtask_index}, actual={result['subtask_index']}")
    if not isinstance(result["task_finished"], bool):
        raise ValueError(f"task_finished must be a JSON boolean: {result}")
    if result["status"] not in VALID_STATUS:
        raise ValueError(f"status can only be continue/finished/blocked: {result}")
    if result["instructionType"] not in VALID_INSTRUCTION_TYPES:
        raise ValueError(f"instructionType is invalid: {result}")
    if not isinstance(result["reference_matched"], bool):
        raise ValueError(f"reference_matched must be a JSON boolean: {result}")
    if not isinstance(result["obstacle_detected"], bool):
        raise ValueError(f"obstacle_detected must be a JSON boolean: {result}")

    result["mile"] = float(result["mile"])
    result["raw"] = float(result["raw"])
    result["speed"] = float(result["speed"])
    result["confidence"] = float(result["confidence"])
    if not 0.0 <= result["confidence"] <= 1.0:
        raise ValueError(f"confidence must be between 0 and 1: {result}")

    if result["task_finished"]:
        result["status"] = "finished"
        result["instructionType"] = "stop"
        result["mile"] = 0.0
        result["raw"] = 0.0
    elif result["status"] == "blocked":
        result["instructionType"] = "stop"
        result["mile"] = 0.0
        result["raw"] = 0.0
        result["obstacle_detected"] = True
    elif result["instructionType"] == "forward":
        if not 5.0 <= result["mile"] <= 50.0:
            raise ValueError(f"for forward, mile must be between 5 and 50 meters: {result}")
        result["raw"] = 0.0
    elif result["instructionType"] in {"left", "right"}:
        if not 1.0 <= result["raw"] <= 90.0:
            raise ValueError(f"for {result['instructionType']}, raw must be between 1 and 90 degrees: {result}")
        result["mile"] = 0.0
    else:
        result["mile"] = 0.0
        result["raw"] = 0.0
    return result


async def analyze_singledog_navigation_image(
    *,
    task_id: str,
    dog_id: str,
    image_path: Path,
    subtask_index: int,
    step_index: int = 0,
) -> dict[str, Any]:
    """Analyze one dog front-view image and decide the next single-step action."""

    prompt = _load_prompt("navigation.txt")
    current_instruction = subtask_instruction(subtask_index)
    reference_path = _reference_image_for_subtask(subtask_index)
    context = {
        "taskId": task_id,
        "dogId": dog_id,
        "stepIndex": step_index,
        "subtaskIndex": subtask_index,
        "currentSubtaskInstruction": current_instruction,
        "referenceImageAvailable": reference_path is not None,
        "imageOrder": (
            ["subtask_reference_image", "current_dog_front_view"]
            if reference_path is not None
            else ["current_dog_front_view"]
        ),
    }
    content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": "This time, execute only the following current subtask; do not execute other subtasks ahead of time:\n" + current_instruction},
        {"type": "text", "text": f"Singledog navigation context: {json.dumps(context, ensure_ascii=False)}"},
    ]
    if reference_path is not None:
        content.append({"type": "text", "text": f"Reference image for current subtask {subtask_index}: {reference_path.name}"})
        content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(reference_path), "detail": "high"}})
    else:
        content.append({"type": "text", "text": f"The reference image for the current subtask {subtask_index} is not yet provided; please make your judgment based only on the language instruction and the current front view."})
    content.extend(
        [
            {"type": "text", "text": "Current image: dog front camera view."},
            {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path), "detail": "high"}},
        ]
    )

    raw_response = await ai_analysis([{"role": "user", "content": content}])
    result = validate_navigation_result(parse_model_json(raw_response), subtask_index=subtask_index)
    result_path = write_policy_result(
        task_id,
        {
            "type": "singledog_navigation",
            "taskId": task_id,
            "dogId": dog_id,
            "subtaskIndex": subtask_index,
            "stepIndex": step_index,
            "subtaskInstruction": current_instruction,
            "referenceImagePath": str(reference_path) if reference_path is not None else None,
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
