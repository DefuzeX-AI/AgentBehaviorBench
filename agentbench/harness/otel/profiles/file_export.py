"""Import files emitted by the selected upstream exporter during one Case."""
import json
from pathlib import Path


def environment(config, endpoint, agent_id):
    return dict(config.enable_env)


def _value(value):
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_value(v) for v in value]}}
    if isinstance(value, dict):
        return {"kvlistValue": {"values": _attributes(value)}}
    return {"stringValue": str(value)}


def _attributes(values):
    return [{"key": k, "value": _value(v)} for k, v in (values or {}).items()]


def _nanos(hrtime):
    seconds, nanos = hrtime
    return str(seconds * 1_000_000_000 + nanos)


def _llxprt_batch(row):
    context = row.get("spanContext")
    if not isinstance(context, dict) or not context.get("spanId"):
        return None
    span = {k: row[k] for k in ("name", "parentSpanId", "status", "droppedAttributesCount",
                                "droppedEventsCount", "droppedLinksCount") if row.get(k) is not None}
    span.update(traceId=context["traceId"], spanId=context["spanId"],
                startTimeUnixNano=_nanos(row["startTime"]), endTimeUnixNano=_nanos(row["endTime"]),
                attributes=_attributes(row.get("attributes")))
    if isinstance(row.get("kind"), int):
        span["kind"] = row["kind"] + 1  # JS and OTLP use different enum offsets.
    span["events"] = [{"name": e["name"], "timeUnixNano": _nanos(e["time"]),
                       "attributes": _attributes(e.get("attributes"))} for e in row.get("events", [])]
    span["links"] = [{**{k: link["context"][k] for k in ("traceId", "spanId")},
                      "attributes": _attributes(link.get("attributes"))} for link in row.get("links", [])]
    scope = row.get("instrumentationScope", {})
    resource = row.get("resource") or {}
    return {"resourceSpans": [{"resource": {"attributes": _attributes(resource.get("attributes", resource))},
            "scopeSpans": [{"scope": scope, "spans": [span]}]}]}


def collect(config, workdir, sink):
    root = Path(workdir).resolve()
    source = root / config.file
    paths = [source]
    if config.file_format == "llxprt-jsonl":
        paths = sorted(source.parent.glob(source.name + ".*")) + paths
    found = False
    for path in paths:
        if not path.resolve().is_relative_to(root):
            raise ValueError("Trace file outside Agent export directory")
        if not path.is_file():
            continue
        found = True
        body = path.read_bytes()
        transport = {"llxprt-jsonl": "llxprt-file", "whip-session": "session-export"}.get(config.file_format, "file")
        # The Agent's own file is the original; archive it before deriving span rows.
        archived = sink.archive(body, transport=transport, name=path.name)
        text = body.decode("utf-8")
        if config.file_format == "llxprt-jsonl":
            for line in text.splitlines():
                if line.strip():
                    original = json.loads(line)
                    batch = _llxprt_batch(original)
                    if batch:
                        sink.accept_json(batch, transport=transport, file_record=original, source=archived)
        else:
            sink.accept_json(json.loads(text), transport=transport, source=archived)
    if not sink.count:
        sink.observation_note = "Exporter file contained no spans" if found else "Agent did not create the configured trace file"
