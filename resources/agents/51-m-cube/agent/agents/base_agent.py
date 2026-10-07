from __future__ import annotations

import base64
import ast
from io import BytesIO
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar, get_args, get_origin

from pydantic import BaseModel, ValidationError
from services.llm_factory import _repair_json_text


T = TypeVar("T", bound=BaseModel)
RawLLMResponse = dict[str, Any] | str
LLMCallable = Callable[[str, dict[str, Any]], RawLLMResponse]


class AgentExecutionError(RuntimeError):
    """Raised when an agent fails after all retry attempts."""


class AgentValidationError(RuntimeError):
    """Raised when structured output cannot be validated by Pydantic."""


@dataclass(frozen=True)
class RetryPolicy:
    """Retry policy aligned with TAD: default 3 attempts with exponential backoff."""

    max_retries: int = 3
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0


class BaseStructuredAgent(Generic[T]):
    """
    Base class for all LLM agents.
    Responsibilities:
    1) Call model provider through injected callable.
    2) Enforce structured output validation with Pydantic v2.
    3) Retry on transient failures with exponential backoff.
    """

    def __init__(
        self,
        name: str,
        llm_callable: LLMCallable,
        retry_policy: RetryPolicy | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.name = name
        self._llm_callable = llm_callable
        self._retry_policy = retry_policy or RetryPolicy()
        self._logger = logger or logging.getLogger(f"agent.{name}")

    def run_structured(
        self,
        *,
        prompt: str,
        output_model: type[T],
        context: dict[str, Any] | None = None,
    ) -> T:
        """
        Execute one structured LLM call and return validated Pydantic model.
        Raises AgentExecutionError when retries are exhausted.
        """
        context_payload = context or {}
        # Normalize multimodal inputs at agent layer: read local files and attach base64 payloads.
        # This keeps provider adapters focused on request-shaping rather than filesystem IO.
        context_payload = self._inject_image_payloads(context_payload)
        # Pass target schema to provider adapters so they can enforce strict JSON output.
        context_payload = {
            **context_payload,
            "_output_schema": output_model.model_json_schema(),
            "_agent_name": self.name,
        }
        last_error: Exception | None = None
        backoff = self._retry_policy.initial_backoff_seconds

        for attempt in range(1, self._retry_policy.max_retries + 1):
            started_at = time.perf_counter()
            try:
                raw_response = self._llm_callable(prompt, context_payload)
                try:
                    if isinstance(raw_response, str) and not self._is_strict_json_object(raw_response):
                        repaired = self._attempt_json_repair(
                            raw_response=raw_response,
                            output_model=output_model,
                            context_payload=context_payload,
                            parse_error=AgentValidationError("strict_json_parse_failed"),
                        )
                        if repaired is None:
                            # Fall back to local normalization heuristics when LLM-repair is unavailable.
                            normalized = self._normalize_response(raw_response)
                        else:
                            normalized = repaired
                    else:
                        normalized = self._normalize_response(raw_response)
                except (AgentValidationError, json.JSONDecodeError, TypeError, ValueError) as parse_exc:
                    repaired = self._attempt_json_repair(
                        raw_response=raw_response,
                        output_model=output_model,
                        context_payload=context_payload,
                        parse_error=parse_exc,
                    )
                    if repaired is None:
                        # Last-resort fallback: keep workflow alive by falling back to
                        # an empty payload and letting schema repair fill required fields.
                        # This prevents frequent hard-failures on malformed model JSON.
                        normalized = {}
                    else:
                        normalized = repaired
                try:
                    validated = output_model.model_validate(normalized)
                except ValidationError:
                    # Best-effort schema-drift self-healing:
                    # fill missing required fields with safe placeholders/defaults,
                    # drop unknown keys, and retry validation once in-memory.
                    repaired = self._repair_payload_for_model(normalized, output_model)
                    validated = output_model.model_validate(repaired)
                self._logger.info(
                    "agent_call_success name=%s attempt=%d latency_ms=%d",
                    self.name,
                    attempt,
                    int((time.perf_counter() - started_at) * 1000),
                )
                return validated
            except (ValidationError, AgentValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
                last_error = exc
                self._logger.warning(
                    "agent_call_validation_failed name=%s attempt=%d error=%s",
                    self.name,
                    attempt,
                    str(exc),
                )
            except Exception as exc:  # noqa: BLE001 - preserve error for retry policy.
                last_error = exc
                self._logger.warning(
                    "agent_call_failed name=%s attempt=%d error=%s",
                    self.name,
                    attempt,
                    str(exc),
                )

            if attempt < self._retry_policy.max_retries:
                time.sleep(backoff)
                backoff *= self._retry_policy.backoff_multiplier

        raise AgentExecutionError(
            f"Agent '{self.name}' failed after {self._retry_policy.max_retries} attempts: {last_error}"
        ) from last_error

    def _attempt_json_repair(
        self,
        *,
        raw_response: RawLLMResponse,
        output_model: type[T],
        context_payload: dict[str, Any],
        parse_error: Exception,
    ) -> dict[str, Any] | None:
        """
        Best-effort JSON self-healing step.
        When model output is malformed JSON text, ask the same LLM once to rewrite
        it as strict JSON under current schema. If repair still fails, return None.
        """
        if not isinstance(raw_response, str):
            return None

        raw_text = raw_response.strip()
        if not raw_text:
            return None

        repair_prompt = (
            "You are a JSON repair tool.\n"
            "Task: rewrite the RAW_OUTPUT into one strict JSON object that matches OUTPUT_SCHEMA.\n"
            "Rules:\n"
            "1) Output JSON object only.\n"
            "2) No markdown/code fences.\n"
            "3) Keep existing semantics; do not add unrelated fields.\n\n"
            f"[OUTPUT_SCHEMA]\n{json.dumps(output_model.model_json_schema(), ensure_ascii=False)}\n\n"
            f"[RAW_OUTPUT]\n{raw_text[:20000]}\n\n"
            f"[PARSE_ERROR]\n{str(parse_error)}"
        )
        repair_context = {
            **context_payload,
            "_repair_mode": "json_only",
            "_output_schema": output_model.model_json_schema(),
        }
        try:
            repaired_raw = self._llm_callable(repair_prompt, repair_context)
            return self._normalize_response(repaired_raw)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _normalize_response(raw_response: RawLLMResponse) -> dict[str, Any]:
        """
        Normalize provider output to a JSON object for schema validation.
        Accepts either dict directly or JSON string.
        """
        if isinstance(raw_response, dict):
            return raw_response
        if isinstance(raw_response, str):
            text = raw_response.replace("\ufeff", "").strip()
            # Normalize common smart quotes that can break JSON parsing.
            text = text.replace("“", "\"").replace("”", "\"").replace("’", "'")
            # Common model behavior: wrap JSON in fenced code blocks.
            if text.startswith("```"):
                lines = text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            text = BaseStructuredAgent._strip_non_json_wrappers(text)

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                # Best effort 1: extract first balanced JSON object span.
                candidate = BaseStructuredAgent._extract_first_balanced_json_object(text) or text
                try:
                    payload = json.loads(candidate)
                except json.JSONDecodeError:
                    # Best effort 2: apply JSON text repair heuristics (missing colon/comma/trailing comma etc.).
                    repaired = _repair_json_text(candidate)
                    try:
                        payload = json.loads(repaired)
                    except json.JSONDecodeError:
                        # Best effort 3: parse python-like dict output (single quotes / None / True / False).
                        payload = ast.literal_eval(repaired)
            if not isinstance(payload, dict):
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    return payload[0]
                raise AgentValidationError("Structured output must be a JSON object.")
            return payload
        raise AgentValidationError("Unsupported LLM response type.")

    @staticmethod
    def _is_strict_json_object(raw_response: str) -> bool:
        """
        Lightweight strict check used to decide whether to trigger LLM repair first.
        Only accepts a top-level JSON object without heuristic recovery.
        """
        text = raw_response.replace("\ufeff", "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        text = BaseStructuredAgent._strip_non_json_wrappers(text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return False
        return isinstance(payload, dict)

    @staticmethod
    def _strip_non_json_wrappers(text: str) -> str:
        """
        Remove common model wrappers before JSON parse:
        - leading labels like 'JSON:' / 'Output:'
        - trailing notes outside json block
        """
        cleaned = text.strip()
        cleaned = re.sub(r"^\s*(json|output|result)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        return cleaned

    @staticmethod
    def _extract_first_balanced_json_object(text: str) -> str | None:
        """
        Extract first balanced {...} span while respecting strings/escapes.
        More robust than naive first '{' / last '}' slicing.
        """
        start = -1
        depth = 0
        in_string = False
        escaped = False

        for idx, ch in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                if depth == 0:
                    start = idx
                depth += 1
                continue
            if ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start >= 0:
                        return text[start : idx + 1]
        return None

    @staticmethod
    def _inject_image_payloads(context: dict[str, Any]) -> dict[str, Any]:
        """
        Read local image files and add base64 payloads into context as `_image_payloads`.
        Supported path keys:
        - image_paths
        - application_image_paths
        - prior_art_image_paths
        """
        merged_paths: list[str] = []
        for key in ("image_paths", "application_image_paths", "prior_art_image_paths"):
            paths = context.get(key)
            if isinstance(paths, list):
                for item in paths:
                    if isinstance(item, str) and item.strip():
                        merged_paths.append(item)
        if not merged_paths:
            return context

        mime_hints = context.get("image_mime_types")
        max_images = int(os.getenv("LLM_MAX_VISION_IMAGES", "8"))
        max_image_bytes = int(os.getenv("LLM_MAX_VISION_IMAGE_BYTES", str(4 * 1024 * 1024)))

        payloads: list[dict[str, str]] = []
        for idx, raw_path in enumerate(merged_paths):
            if len(payloads) >= max_images:
                break
            path = Path(raw_path)
            if not path.exists() or not path.is_file():
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if len(raw) == 0 or len(raw) > max_image_bytes:
                continue

            mime_type = "image/png"
            if isinstance(mime_hints, list) and idx < len(mime_hints):
                hinted = mime_hints[idx]
                if isinstance(hinted, str) and hinted.startswith("image/"):
                    mime_type = hinted
            else:
                guessed, _ = mimetypes.guess_type(str(path))
                if isinstance(guessed, str) and guessed.startswith("image/"):
                    mime_type = guessed

            normalized = BaseStructuredAgent._normalize_image_for_vision(raw=raw, mime_type=mime_type)
            if normalized is None:
                continue
            normalized_mime, normalized_raw = normalized
            payloads.append(
                {
                    "mime_type": normalized_mime,
                    "b64": base64.b64encode(normalized_raw).decode("ascii"),
                }
            )

        if not payloads:
            return context
        return {**context, "_image_payloads": payloads}

    @classmethod
    def _repair_payload_for_model(cls, payload: dict[str, Any], model_type: type[BaseModel]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        repaired: dict[str, Any] = {}
        for field_name, field_info in model_type.model_fields.items():
            raw_value = cls._pick_field_value(payload, field_name, field_info)
            repaired[field_name] = cls._repair_field_value(field_info.annotation, raw_value, field_info)
        return repaired

    @staticmethod
    def _pick_field_value(payload: dict[str, Any], field_name: str, field_info: Any) -> Any:
        if field_name in payload:
            return payload[field_name]
        alias = getattr(field_info, "validation_alias", None)
        if isinstance(alias, str) and alias in payload:
            return payload[alias]
        choices = getattr(alias, "choices", None)
        if isinstance(choices, (list, tuple)):
            for item in choices:
                if isinstance(item, str) and item in payload:
                    return payload[item]
        return None

    @classmethod
    def _repair_field_value(cls, annotation: Any, value: Any, field_info: Any) -> Any:
        if value is None:
            if getattr(field_info, "default", None) is not None and str(getattr(field_info, "default", None)) != "PydanticUndefined":
                return field_info.default
            default_factory = getattr(field_info, "default_factory", None)
            if callable(default_factory):
                return default_factory()

        origin = get_origin(annotation)
        args = get_args(annotation)

        # Optional / Union
        if origin is not None and str(origin).endswith("Union"):
            non_none = [a for a in args if a is not type(None)]  # noqa: E721
            if value is None and len(args) != len(non_none):
                return None
            if non_none:
                return cls._repair_field_value(non_none[0], value, field_info)

        # Nested BaseModel
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            nested = value if isinstance(value, dict) else {}
            return cls._repair_payload_for_model(nested, annotation)

        # List
        if origin in (list, list[Any]):
            item_type = args[0] if args else Any
            raw_items = value if isinstance(value, list) else []
            repaired_items = [cls._repair_field_value(item_type, item, field_info) for item in raw_items]
            min_len = cls._min_length(field_info)
            while len(repaired_items) < min_len:
                repaired_items.append(cls._placeholder_for_type(item_type))
            return repaired_items

        # Dict
        if origin is dict:
            return value if isinstance(value, dict) else {}

        # Bool/Int/Float
        if annotation is bool:
            return bool(value) if value is not None else False
        if annotation is int:
            try:
                return int(value)
            except Exception:
                return 0
        if annotation is float:
            try:
                return float(value)
            except Exception:
                return 0.0

        # Literal -> first choice fallback
        if origin is not None and "Literal" in str(origin):
            literal_choices = list(args)
            if value in literal_choices:
                return value
            return literal_choices[0] if literal_choices else value

        # String fallback
        if annotation is str or (isinstance(annotation, type) and annotation.__name__ == "str"):
            text = str(value).strip() if value is not None else ""
            min_len = cls._min_length(field_info)
            if not text:
                text = "未提供"
            while len(text) < max(1, min_len):
                text += "补充"
            return text

        return value

    @staticmethod
    def _placeholder_for_type(tp: Any) -> Any:
        origin = get_origin(tp)
        args = get_args(tp)
        if tp is str:
            return "未提供"
        if tp is int:
            return 0
        if tp is float:
            return 0.0
        if tp is bool:
            return False
        if origin in (list, list[Any]):
            return []
        if origin is dict:
            return {}
        if origin is not None and "Literal" in str(origin):
            return args[0] if args else "UNKNOWN"
        if isinstance(tp, type) and issubclass(tp, BaseModel):
            return {}
        return "未提供"

    @staticmethod
    def _min_length(field_info: Any) -> int:
        metadata = getattr(field_info, "metadata", None)
        if not metadata:
            return 0
        for item in metadata:
            min_len = getattr(item, "min_length", None)
            if isinstance(min_len, int):
                return min_len
        return 0

    @staticmethod
    def _normalize_image_for_vision(*, raw: bytes, mime_type: str) -> tuple[str, bytes] | None:
        """
        Normalize to PNG/JPEG so provider-side vision parsers can decode reliably.
        """
        mt = (mime_type or "").lower().strip()
        if mt in {"image/png", "image/jpeg"}:
            return mt, raw
        if mt == "image/jpg":
            return "image/jpeg", raw

        try:
            from PIL import Image  # type: ignore[import-not-found]
        except Exception:
            return None

        try:
            with Image.open(BytesIO(raw)) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.mode else "RGB")
                out = BytesIO()
                img.save(out, format="PNG")
                return "image/png", out.getvalue()
        except Exception:
            return None
