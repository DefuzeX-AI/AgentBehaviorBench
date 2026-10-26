"""Friendly structured-output errors shared by CLI and API-key LLM backends."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Type

from pydantic import BaseModel, ValidationError


class LLMResponseFormatError(RuntimeError):
    """Raised when an LLM returns empty, non-JSON, or schema-invalid content."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "format",
        raw: str = "",
        validation_error: ValidationError | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.raw = raw
        self.validation_error = validation_error


def _excerpt(raw: Any, limit: int = 220) -> str:
    text = "" if raw is None else str(raw)
    return " ".join(text.strip().split())[:limit]


def _field_summary(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:6]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
        parts.append(f"{loc}: {err.get('msg')}")
    return "；".join(parts) if parts else str(exc)


def parse_structured_json(
    schema_model: Type[BaseModel],
    raw: str,
    *,
    backend_label: str,
    extract_json: Callable[[str], str] | None = None,
) -> BaseModel:
    """Parse LLM text into a Pydantic model with user-facing failure reasons."""
    if not (raw or "").strip():
        raise LLMResponseFormatError(
            f"{backend_label} 回覆空白，請重試或切換模型。",
            kind="empty",
            raw=raw or "",
        )

    json_text = extract_json(raw) if extract_json else raw
    json_text = (json_text or "").strip()
    if not json_text:
        raise LLMResponseFormatError(
            f"{backend_label} 回覆空白，請重試或切換模型。",
            kind="empty",
            raw=raw,
        )

    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise LLMResponseFormatError(
            f"{backend_label} 回覆不是合法 JSON，請重試或切換模型。回覆片段：{_excerpt(raw)!r}",
            kind="json",
            raw=raw,
        ) from exc

    try:
        return schema_model.model_validate(payload)
    except ValidationError as exc:
        raise LLMResponseFormatError(
            f"{backend_label} 回覆格式不符合要求：{_field_summary(exc)}",
            kind="schema",
            raw=raw,
            validation_error=exc,
        ) from exc


def ensure_structured_result(
    schema_model: Type[BaseModel],
    result: Any,
    *,
    backend_label: str,
) -> BaseModel:
    """Validate structured-output results returned by API-key chat backends."""
    if result is None:
        raise LLMResponseFormatError(
            f"{backend_label} 回覆空白，請重試或切換模型。",
            kind="empty",
        )
    if isinstance(result, schema_model):
        return result
    if isinstance(result, BaseModel):
        result = result.model_dump()
    if isinstance(result, str):
        return parse_structured_json(schema_model, result, backend_label=backend_label)
    try:
        return schema_model.model_validate(result)
    except ValidationError as exc:
        raise LLMResponseFormatError(
            f"{backend_label} 回覆格式不符合要求：{_field_summary(exc)}",
            kind="schema",
            validation_error=exc,
        ) from exc


def normalize_structured_exception(backend_label: str, exc: Exception) -> Exception:
    """Convert parser/schema failures from provider wrappers into clear messages."""
    if isinstance(exc, LLMResponseFormatError):
        return exc
    if isinstance(exc, ValidationError):
        return LLMResponseFormatError(
            f"{backend_label} 回覆格式不符合要求：{_field_summary(exc)}",
            kind="schema",
            validation_error=exc,
        )
    text = str(exc)
    lowered = text.lower()
    format_markers = (
        "json",
        "schema",
        "structured",
        "validation",
        "parse",
        "parsing",
        "invalid tool",
    )
    if any(marker in lowered for marker in format_markers):
        return LLMResponseFormatError(
            f"{backend_label} 回覆格式不正確：{_excerpt(text)}",
            kind="format",
        )
    return exc
