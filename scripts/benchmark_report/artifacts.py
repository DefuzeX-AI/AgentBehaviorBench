"""Read persisted Case, input, trace, OTEL and network artifacts safely."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


_SECRET_KEYS = re.compile(
    r"(?:api[_-]?key|authorization|cookie|secret|token|password|credential)", re.I
)
_SECRET_VALUES = re.compile(
    r"(?i)(?:bearer\s+)[A-Za-z0-9._~+\-/=]+|sk-(?:or-)?[A-Za-z0-9_-]{12,}"
)


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    # splitlines() also splits U+2028/U+2029 inside valid JSON string values.
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def redact(value: Any, *, key: str = "") -> Any:
    """Recursively redact credentials while retaining diagnostic structure."""
    if key and _SECRET_KEYS.search(key):
        if value in (None, "", [], {}):
            return value
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _SECRET_VALUES.sub("[REDACTED]", value)
    return value


def percentile(values: Iterable[float], p: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    phat = successes / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    half = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def event_artifact(root: Path, run: dict[str, Any], case_id: str) -> str | None:
    artifact = root / str(run.get("artifact", ""))
    events = load_json(artifact, [])
    if not isinstance(events, list):
        return None
    candidates: list[str] = []
    for event in events:
        if not isinstance(event, dict) or not event.get("artifact_directory"):
            continue
        if event.get("case_id") == case_id:
            candidates.append(str(event["artifact_directory"]))
    if not candidates:
        return None
    path = Path(candidates[-1])
    return relative(root, path if path.is_absolute() else root / path)


def framework_summary(path: Path) -> dict[str, Any]:
    records = read_jsonl(path)
    starts: dict[str, dict[str, Any]] = {}
    spans: list[dict[str, Any]] = []
    execution_start = execution_end = None
    for item in records:
        event = item.get("event")
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        if event == "execution_start":
            execution_start = item.get("timestamp")
        elif event == "execution_end":
            execution_end = item.get("timestamp")
        elif event == "span_start" and data.get("span_id"):
            starts[str(data["span_id"])] = {"timestamp": item.get("timestamp"), **data}
        elif event == "span_end":
            span_id = str(data.get("span_id", ""))
            start = starts.pop(span_id, {})
            spans.append(
                {
                    "name": start.get("name", "unknown"),
                    "kind": start.get("kind", "unknown"),
                    "status": data.get("tool_status") or data.get("status") or "completed",
                    "duration_ms": duration_ms(start.get("timestamp"), item.get("timestamp")),
                    "output_preview": preview(data.get("output"), 280),
                }
            )
    for start in starts.values():
        spans.append(
            {
                "name": start.get("name", "unknown"),
                "kind": start.get("kind", "unknown"),
                "status": "unfinished",
                "duration_ms": None,
                "output_preview": "",
            }
        )
    duration = duration_ms(execution_start, execution_end)
    kinds = Counter(str(span.get("kind", "unknown")) for span in spans)
    # Full raw traces remain linked; the HTML contains enough structure to inspect flow.
    display = sorted(spans, key=lambda s: (s["status"] != "unfinished", -(s["duration_ms"] or 0)))[:80]
    return {
        "event_count": len(records),
        "span_count": len(spans),
        "span_kinds": dict(kinds),
        "duration_ms": duration,
        "spans": display,
        "display_truncated": len(spans) > len(display),
    }


def otel_summary(path: Path, status_path: Path) -> dict[str, Any]:
    records = read_jsonl(path)
    spans: list[dict[str, Any]] = []
    for item in records:
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        status = data.get("status") if isinstance(data.get("status"), dict) else {}
        start_ns = data.get("start_time_unix_nano")
        end_ns = data.get("end_time_unix_nano")
        duration_ms = None
        try:
            duration_ms = (int(end_ns) - int(start_ns)) / 1_000_000
        except (TypeError, ValueError):
            duration_ms = duration_ms(data.get("start_time"), data.get("end_time"))
        spans.append(
            {
                "name": data.get("name", "unknown"),
                "kind": str(data.get("kind", "unknown")).removeprefix("SpanKind."),
                "status": status.get("status_code", "UNSET"),
                "duration_ms": duration_ms,
                "trace_id": data.get("trace_id"),
                "span_id": data.get("span_id"),
            }
        )
    display = sorted(spans, key=lambda s: -(s["duration_ms"] or 0))[:80]
    return {
        "status": load_json(status_path, {}),
        "span_count": len(spans),
        "spans": display,
        "display_truncated": len(spans) > len(display),
    }


def network_summary(path: Path) -> dict[str, Any]:
    records = read_jsonl(path)
    events = Counter(str(item.get("event", "unknown")) for item in records)
    endpoints: Counter[tuple[str, str, str, str]] = Counter()
    errors: list[dict[str, Any]] = []
    for item in records:
        event = str(item.get("event", ""))
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        if event.endswith("_response"):
            key = (
                event,
                str(data.get("host") or data.get("source_host") or ""),
                str(data.get("method") or ""),
                str(data.get("status") or ""),
            )
            endpoints[key] += 1
            try:
                status = int(data.get("status"))
            except (TypeError, ValueError):
                status = 0
            if status >= 400 and len(errors) < 30:
                errors.append(
                    {
                        "event": event,
                        "host": key[1],
                        "method": key[2],
                        "path": str(data.get("path") or data.get("source_path") or "")[:240],
                        "status": status,
                    }
                )
    endpoint_rows = [
        {"event": k[0], "host": k[1], "method": k[2], "status": k[3], "count": count}
        for k, count in endpoints.most_common()
    ]
    return {"event_count": len(records), "events": dict(events), "endpoints": endpoint_rows, "errors": errors}


def duration_ms(start: Any, end: Any) -> float | None:
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        return (b - a).total_seconds() * 1000
    except ValueError:
        return None


def preview(value: Any, limit: int = 200) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(redact(value), ensure_ascii=False)
        except TypeError:
            value = str(value)
    value = _SECRET_VALUES.sub("[REDACTED]", value)
    return value if len(value) <= limit else value[:limit] + "…"


def collect_input(root: Path, directory: Path) -> dict[str, Any]:
    result = redact(load_json(directory / "result.json", {}))
    submission = redact(load_json(directory / "submission.json", {}))
    return {
        "directory": relative(root, directory),
        "input": redact(load_json(directory / "input.json", {})),
        "request": redact(load_json(directory / "request.json", {})),
        "mapped_input": redact(load_json(directory / "mapped-input.json", {})),
        "result": result,
        "submission": submission,
        "context": redact(load_json(directory / "context.json", {})),
        "framework": framework_summary(directory / "framework.jsonl"),
        "otel": otel_summary(directory / "otel.jsonl", directory / "otel-status.json"),
        "raw_files": {
            name: relative(root, directory / name)
            for name in (
                "input.json",
                "request.json",
                "mapped-input.json",
                "result.json",
                "submission.json",
                "context.json",
                "evidence.json",
                "framework.jsonl",
                "otel.jsonl",
                "otel-status.json",
            )
            if (directory / name).exists()
        },
    }
