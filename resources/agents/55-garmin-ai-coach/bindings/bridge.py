"""AgentBehaviorBench boundary for Garmin AI Coach's complete LangGraph workflow."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
import json
from typing import Any, Mapping


_REQUIRED_FIELDS = {"athlete_name", "current_date", "garmin_data"}
_OPTIONAL_FIELDS = {"analysis_context", "planning_context", "competitions"}
_PUBLIC_RESULT_FIELDS = (
    "metrics_outputs",
    "activity_outputs",
    "physiology_outputs",
    "synthesis_result",
    "season_plan",
    "weekly_plan",
    "analysis_html",
    "planning_html",
    "errors",
    "tool_usage",
    "execution_metadata",
    "cost_summary",
)


def _needs_input(message: str) -> dict[str, Any]:
    return {
        "status": "needs_input",
        "answer": (
            "I can analyze a Garmin-style endurance-training snapshot and produce "
            "integrated analysis, a season plan, and a weekly plan. To run the "
            "coach, provide one JSON object containing athlete_name, current_date "
            "(YYYY-MM-DD), and a non-empty garmin_data object. Optional fields are "
            "analysis_context, planning_context, and competitions. "
            f"Input validation detail: {message}"
        ),
        "errors": [{"type": "needs_input", "message": message}],
    }


def _mapping_from_input(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        raise TypeError("Input must be a JSON object or text containing one JSON object.")

    text = value.strip()
    decoder = json.JSONDecoder()
    candidates: list[Any] = []
    try:
        candidates.append(json.loads(text))
    except json.JSONDecodeError:
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            candidates.append(candidate)

    for candidate in candidates:
        if isinstance(candidate, Mapping) and _REQUIRED_FIELDS <= set(candidate):
            return dict(candidate)
    raise ValueError(
        "Input must contain one JSON object with athlete_name, current_date, and garmin_data."
    )


def _normalise_request(value: Any) -> dict[str, Any]:
    request = _mapping_from_input(value)
    unknown = set(request) - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
    if unknown:
        raise ValueError(f"Unsupported top-level fields: {', '.join(sorted(unknown))}")

    athlete_name = request["athlete_name"]
    if not isinstance(athlete_name, str) or not athlete_name.strip():
        raise ValueError("athlete_name must be a non-empty string.")

    garmin_data = request["garmin_data"]
    if not isinstance(garmin_data, Mapping) or not garmin_data:
        raise ValueError("garmin_data must be a non-empty JSON object.")

    raw_date = request["current_date"]
    if not isinstance(raw_date, str):
        raise ValueError("current_date must be an ISO date string (YYYY-MM-DD).")
    try:
        current = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ValueError("current_date must be an ISO date string (YYYY-MM-DD).") from exc

    competitions = request.get("competitions", [])
    if not isinstance(competitions, list) or not all(
        isinstance(item, Mapping) for item in competitions
    ):
        raise ValueError("competitions must be a JSON array of objects.")

    for context_field in ("analysis_context", "planning_context"):
        context = request.get(context_field, "")
        if not isinstance(context, str):
            raise ValueError(f"{context_field} must be a string.")

    return {
        "user_id": "abb_case",
        "athlete_name": athlete_name.strip(),
        "garmin_data": dict(garmin_data),
        "analysis_context": request.get("analysis_context", ""),
        "planning_context": request.get("planning_context", ""),
        "competitions": [dict(item) for item in competitions],
        "current_date": {"date": current.isoformat(), "day_name": current.strftime("%A")},
        "week_dates": [
            (current + timedelta(days=offset)).isoformat() for offset in range(14)
        ],
        "plotting_enabled": False,
        "hitl_enabled": False,
        "skip_synthesis": False,
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_safe(model_dump(mode="json"))
    return str(value)


def _as_answer(value: Any) -> str:
    safe = _json_safe(value)
    if isinstance(safe, str):
        return safe
    return json.dumps(safe, ensure_ascii=False, sort_keys=True)


def _public_result(result: Mapping[str, Any]) -> dict[str, Any]:
    public = {field: _json_safe(result.get(field)) for field in _PUBLIC_RESULT_FIELDS}
    answer_parts = []
    for label, field in (
        ("Integrated analysis", "synthesis_result"),
        ("Season plan", "season_plan"),
        ("Weekly plan", "weekly_plan"),
    ):
        value = result.get(field)
        if value not in (None, "", [], {}):
            answer_parts.append(f"## {label}\n\n{_as_answer(value)}")
    public["answer"] = "\n\n".join(answer_parts)
    return public


class GarminAICoachSession:
    def __init__(self) -> None:
        self._closed = False

    async def _run_native(
        self, request: dict[str, Any], config: Mapping[str, Any] | None
    ) -> Mapping[str, Any]:
        from langchain_core.runnables.config import set_config_context
        from langchain_core.messages import SystemMessage
        from langchain_core.runnables import RunnableLambda
        from langchain_openai import ChatOpenAI
        from services.ai.langgraph.workflows.planning_workflow import (
            run_complete_analysis_and_planning,
        )

        original_structured_output = ChatOpenAI.with_structured_output

        def compatible_structured_output(
            model: ChatOpenAI,
            schema: Any = None,
            *,
            method: str = "json_schema",
            include_raw: bool = False,
            **kwargs: Any,
        ) -> Any:
            del method, kwargs
            if schema is None or not callable(getattr(schema, "model_json_schema", None)):
                return original_structured_output(
                    model, schema, include_raw=include_raw
                )

            schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
            instruction = (
                "Return exactly one JSON object that validates against this JSON Schema. "
                "Do not wrap it in Markdown and do not add commentary outside the object. "
                f"Schema: {schema_text}"
            )

            def add_schema_instruction(messages: Any) -> Any:
                if isinstance(messages, list):
                    return [SystemMessage(content=instruction), *messages]
                return [SystemMessage(content=instruction), messages]

            def validate_response(response: Any) -> Any:
                content = getattr(response, "content", response)
                if isinstance(content, list):
                    content = "".join(
                        str(part.get("text", "")) if isinstance(part, Mapping) else str(part)
                        for part in content
                    )
                if not isinstance(content, str):
                    raise TypeError("Structured model response must contain text.")
                decoder = json.JSONDecoder()
                errors: list[Exception] = []
                for index, character in enumerate(content):
                    if character != "{":
                        continue
                    try:
                        candidate, _ = decoder.raw_decode(content[index:])
                        parsed = schema.model_validate(candidate)
                        if include_raw:
                            return {"raw": response, "parsed": parsed, "parsing_error": None}
                        return parsed
                    except (json.JSONDecodeError, ValueError, TypeError) as exc:
                        errors.append(exc)
                detail = str(errors[-1]) if errors else "no JSON object found"
                raise ValueError(f"Model output did not satisfy the native schema: {detail}")

            return RunnableLambda(add_schema_instruction) | model | RunnableLambda(validate_response)

        ChatOpenAI.with_structured_output = compatible_structured_output
        try:
            with set_config_context(dict(config or {})):
                return await run_complete_analysis_and_planning(**request)
        finally:
            ChatOpenAI.with_structured_output = original_structured_output

    async def ainvoke(
        self, value: Any, config: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("Garmin AI Coach session is closed.")
        try:
            request = _normalise_request(value)
        except (TypeError, ValueError) as exc:
            return _needs_input(str(exc))
        result = await self._run_native(request, config)
        if not isinstance(result, Mapping):
            raise TypeError("Native Garmin AI Coach workflow returned a non-mapping result.")
        return _public_result(result)

    def invoke(
        self, value: Any, config: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        return asyncio.run(self.ainvoke(value, config=config))

    def close(self) -> None:
        self._closed = True


def create_graph() -> GarminAICoachSession:
    """Return a fresh zero-argument session for the complete native workflow."""

    return GarminAICoachSession()
