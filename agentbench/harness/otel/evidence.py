"""Preserve OTLP span fields with their resource, scope and evidence origin.

Every received export is archived byte for byte under raw/ before any span row
is derived from it. The archive is unredacted and stays local to the attempt.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from threading import Lock

from agentbench.observe.store import atomic_json, environment_secrets, redact

RAW_DIRECTORY = "raw"
_EXTENSIONS = {"application/x-protobuf": ".pb", "application/grpc+proto": ".pb", "application/json": ".json"}


def _identifier(value, length):
    if not isinstance(value, str) or not re.fullmatch(f"[0-9a-fA-F]{{{length}}}", value) or int(value, 16) == 0:
        raise ValueError("Invalid OTLP identifier")
    return value.lower()


def _redact_attributes(value, secrets):
    if isinstance(value, list):
        return [_redact_attributes(item, secrets) for item in value]
    if isinstance(value, dict):
        if isinstance(value.get("key"), str) and "value" in value:
            key = value["key"]
            safe = redact({key: value["value"]}, secrets)[key]
            if isinstance(safe, str):
                safe = {"stringValue": safe}
            return {**value, "value": _redact_attributes(safe, secrets)}
        return {k: _redact_attributes(v, secrets) for k, v in value.items()}
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            decoded = json.loads(value)
        except (ValueError, RecursionError):
            return value
        if isinstance(decoded, (dict, list)):
            safe = redact(_redact_attributes(decoded, secrets), secrets)
            if safe != decoded:
                return json.dumps(safe, ensure_ascii=False)
    return value


def _attribute_value(value):
    if "arrayValue" in value:
        return [_attribute_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return _key_values(value["kvlistValue"].get("values", []))
    return next(iter(value.values()), None)


def _key_values(attributes):
    return {item["key"]: _attribute_value(item.get("value", {})) for item in attributes}


def attribute_map(span):
    return _key_values(span.get("attributes", []))


def _time(ns):
    return datetime.fromtimestamp(int(ns) // 10**9, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{int(ns) % 10**9:09d}Z"


def display_span(row):
    span = row["span"]
    data = dict(origin=row["origin"], scope=row["scope"], resource=row["resource"],
                trace_id=span["traceId"], span_id=span["spanId"], parent_span_id=span.get("parentSpanId"),
                name=span.get("name", ""), kind=span.get("kind"), status=span.get("status", {}),
                attributes=attribute_map(span), events=span.get("events", []), links=span.get("links", []))
    for side in ("start", "end"):
        ns = span.get(side + "TimeUnixNano")
        if ns:
            data[side + "_time_unix_nano"] = str(ns)
            data[side + "_time"] = _time(ns)
    return data


def legacy_origin(data):
    if data.get("origin"):
        return data["origin"]
    attrs = data.get("attributes") or {}
    if attrs.get("abb.invocation_id") and (attrs.get("abb.framework_span_id") or data.get("name") == "abb.execute"):
        return "framework_projection"
    return "unknown"


class EvidenceWriter:
    def __init__(self, directory, config):
        self.directory = directory
        self.config = config
        self.lock = Lock()
        self.count = 0
        self.by_origin = Counter()
        self.context = {}
        self.error = None
        self.rejected_batches = 0
        self.raw_batches = 0
        self.observation_note = None
        self.secrets = environment_secrets()
        directory.mkdir(parents=True, exist_ok=True)
        self.status("running")

    def archive(self, body, *, transport, content_type=None, content_encoding=None, name=None):
        """Store one export exactly as received and return the pointer its span rows carry."""
        with self.lock:
            self.raw_batches += 1
            batch = self.raw_batches
            raw = self.directory / RAW_DIRECTORY
            raw.mkdir(mode=0o700, exist_ok=True)
            if name:
                filename = f"{batch:06d}-{os.path.basename(name)}"
            else:
                filename = f"{batch:06d}{_EXTENSIONS.get(content_type, '.bin')}"
                if content_encoding == "gzip":
                    filename += ".gz"
            # Unredacted Agent exports: owner-only, never replaced.
            descriptor = os.open(raw / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
            source = {"file": f"otel/{RAW_DIRECTORY}/{filename}", "batch": batch}
            self._index({"event": "received", **source, "sha256": hashlib.sha256(body).hexdigest(),
                         "bytes": len(body), "transport": transport, "content_type": content_type,
                         "content_encoding": content_encoding,
                         "received_at": datetime.now(timezone.utc).isoformat()})
            self.status("running")
        return source

    def _index(self, entry):
        path = self.directory / RAW_DIRECTORY / "index.jsonl"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n")

    def reject(self, reason, source=None, count=True):
        with self.lock:
            if count:
                self.rejected_batches += 1
                self.error = reason
            if source is not None:
                self._index({"event": "rejected", "batch": source["batch"], "reason": reason})
            self.status("running")

    def status(self, state):
        reason = self.error or self.config.reason or self.observation_note
        if not reason and state == "zero_spans":
            reason = "No spans exported during this Case attempt"
        atomic_json(self.directory / "status.json", {"schema": "abb.agent-otel.v1", "profile": self.config.profile,
                    "status": state, "span_count": self.count, "protocol": self.config.protocol if self.config.profile != "file-export" else self.config.file_format,
                    "record_count": sum(self.by_origin.values()), "origin_counts": dict(self.by_origin),
                    "rejected_batches": self.rejected_batches, "raw_batches": self.raw_batches,
                    "raw_redacted": False, "reason": reason or None})

    def accept_json(self, batch, *, transport, file_record=None, source=None):
        rows = []
        if not isinstance(batch, dict):
            raise ValueError("Expected an OTLP request object")
        for rs in batch.get("resourceSpans", []):
            for ss in rs.get("scopeSpans", []):
                for original in ss.get("spans", []):
                    span = dict(original)
                    span["traceId"] = _identifier(span["traceId"], 32)
                    span["spanId"] = _identifier(span["spanId"], 16)
                    if span.get("parentSpanId"):
                        span["parentSpanId"] = _identifier(span["parentSpanId"], 16)
                    origin = "auto_instrumented" if self.config.profile.endswith("-auto") else "agent_native"
                    rows.append({"schema": "abb.agent-otel.v1", "context": self.context, "origin": origin, "transport": transport,
                                 "resource": rs.get("resource", {}), "resource_schema_url": rs.get("schemaUrl"),
                                 "scope": ss.get("scope", {}), "scope_schema_url": ss.get("schemaUrl"), "span": span})
                    if file_record is not None:
                        rows[-1]["file_record"] = file_record
        rows = [redact(_redact_attributes(row, self.secrets), self.secrets) for row in rows]
        with self.lock:
            first = sum(self.by_origin.values()) + 1
            for n, row in enumerate(rows, first):
                row["ref"] = {"file": "otel/spans.jsonl", "line": n}
                if source is not None:
                    row["archive"] = source
            lines = [json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows]
            with (self.directory / "spans.jsonl").open("a", encoding="utf-8") as stream:
                stream.writelines(lines)
            if source is not None:
                self._index({"event": "accepted", "batch": source["batch"],
                             "span_lines": [first, first + len(rows) - 1] if rows else []})
            self.by_origin.update(row["origin"] for row in rows)
            self.count = self.by_origin["agent_native"] + self.by_origin["auto_instrumented"]
            self.status("running")


def publish_capture(source, destination):
    """Copy a closed Agent-owned spool through the existing safe channel reader."""
    from agentbench.sdk.integration.channel import collect_response
    import tempfile
    if not source.exists():
        return
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".otel-") as temp:
        from pathlib import Path
        staged = Path(temp) / "otel"
        staged.mkdir()
        collect_response(source, staged)
        restrict_raw(staged)
        staged.rename(destination)


def restrict_raw(directory):
    """Copies do not keep modes; the unredacted archive stays owner-only."""
    raw = directory / RAW_DIRECTORY
    if not raw.is_dir() or raw.is_symlink():
        return
    raw.chmod(0o700)
    for path in raw.iterdir():
        if path.is_file() and not path.is_symlink():
            path.chmod(0o600)
