"""LLM policy for assigning task points to multiple cars."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.modules.ai.service import analysis as ai_analysis
from app.modules.ai.service import parse_model_json
from examples.multicars.scenario import car_ids

CASE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = CASE_DIR / "prompts"
RESULTS_DIR = CASE_DIR / "results"


def safe_component(value: str | None, default: str = "unknown") -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "").strip())
    return (safe.strip("._") or default)[:120]


def _load_prompt() -> str:
    path = PROMPT_DIR / "task_allocation.txt"
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"prompt is empty: {path}")
    return text


async def allocate_tasks_with_llm(
    *,
    task_id: str,
    cars: list[dict[str, Any]],
    task_points: list[dict[str, Any]],
    distance_report: dict[str, Any],
) -> dict[str, Any]:
    prompt = _load_prompt()
    context = {
        "taskId": task_id,
        "cars": cars,
        "task_points": task_points,
        "allDistancesReport": distance_report,
    }
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "text", "text": json.dumps(context, ensure_ascii=False)},
            ],
        }
    ]
    raw_response = await ai_analysis(messages)
    result = validate_allocation_result(
        parse_model_json(raw_response),
        expected_car_ids=[str(car["code"]) for car in cars],
        expected_point_ids=[str(point["id"]) for point in task_points],
    )
    result_path = write_policy_result(
        task_id,
        {
            "type": "multicars_task_allocation",
            "taskId": task_id,
            "raw_response": raw_response,
            "distance_report": distance_report,
            "result": result,
        },
    )
    return {"result": result, "raw_response": raw_response, "result_path": str(result_path)}


def allocate_tasks_sync(
    *,
    task_id: str,
    cars: list[dict[str, Any]],
    task_points: list[dict[str, Any]],
    distance_report: dict[str, Any],
) -> dict[str, Any]:
    return asyncio.run(
        allocate_tasks_with_llm(
            task_id=task_id,
            cars=cars,
            task_points=task_points,
            distance_report=distance_report,
        )
    )


def validate_allocation_result(
    result: dict[str, Any],
    *,
    expected_car_ids: list[str],
    expected_point_ids: list[str],
) -> dict[str, Any]:
    required = {
        "status",
        "assignments",
        "unassignedTaskPointIds",
        "duplicateTaskPointIds",
        "totalEstimatedDistance",
        "reason",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"multi-car allocation output is missing fields {missing}: {result}")
    if not isinstance(result["assignments"], list):
        raise ValueError(f"assignments must be an array: {result}")

    expected_cars = set(expected_car_ids)
    expected_points = set(expected_point_ids)
    seen_points: list[str] = []
    normalized_assignments: list[dict[str, Any]] = []
    seen_cars: set[str] = set()
    for assignment in result["assignments"]:
        if not isinstance(assignment, dict):
            raise ValueError(f"assignment must be an object: {assignment}")
        car_id = str(assignment.get("autocarId") or "")
        if car_id not in expected_cars:
            raise ValueError(f"unknown autocarId={car_id}, expected {sorted(expected_cars)}")
        seen_cars.add(car_id)
        ordered_ids = assignment.get("orderedTaskPointIds") or assignment.get("taskPointIds") or []
        if not isinstance(ordered_ids, list):
            raise ValueError(f"orderedTaskPointIds must be an array: {assignment}")
        ordered_ids = [str(point_id) for point_id in ordered_ids]
        for point_id in ordered_ids:
            if point_id not in expected_points:
                raise ValueError(f"unknown task point id={point_id}, expected {sorted(expected_points)}")
        seen_points.extend(ordered_ids)
        normalized_assignments.append(
            {
                "autocarId": car_id,
                "taskPointIds": [str(item) for item in assignment.get("taskPointIds") or ordered_ids],
                "orderedTaskPointIds": ordered_ids,
                "estimatedDistance": float(assignment.get("estimatedDistance") or 0.0),
                "reason": str(assignment.get("reason") or ""),
            }
        )

    for missing_car in sorted(expected_cars - seen_cars):
        normalized_assignments.append(
            {
                "autocarId": missing_car,
                "taskPointIds": [],
                "orderedTaskPointIds": [],
                "estimatedDistance": 0.0,
                "reason": "The LLM did not explicitly assign this car; the backend fills in an empty task.",
            }
        )

    duplicate_points = sorted({point_id for point_id in seen_points if seen_points.count(point_id) > 1})
    unassigned_points = sorted(expected_points - set(seen_points), key=lambda item: int(item) if item.isdigit() else item)
    result["assignments"] = sorted(normalized_assignments, key=lambda item: car_ids().index(item["autocarId"]) if item["autocarId"] in car_ids() else item["autocarId"])
    result["duplicateTaskPointIds"] = duplicate_points
    result["unassignedTaskPointIds"] = unassigned_points
    result["totalEstimatedDistance"] = float(result.get("totalEstimatedDistance") or 0.0)
    result["status"] = "ok" if not duplicate_points and not unassigned_points else "failed"
    if result["status"] != "ok":
        raise ValueError(f"LLM task allocation is incomplete: {result}")
    return result


def write_policy_result(task_id: str, payload: dict[str, Any]) -> Path:
    task_dir = RESULTS_DIR / safe_component(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = task_dir / f"{payload.get('type', 'policy')}_{safe_component(task_id)}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
