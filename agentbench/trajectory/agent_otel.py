"""Join Agent-exported operations only through recorded, unique identifiers."""
from collections import Counter, defaultdict
from .content import bounded
import json
from agentbench.harness.otel.evidence import display_span
from agentbench.observe.tool_links import SCOPE_KEYS, compatible


def rows(api):
    try:
        path = api.file("otel/spans.jsonl")
    except FileNotFoundError:
        return
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as stream:
        for line, text in enumerate(stream, 1):
            if text.strip():
                yield {"file": "otel/spans.jsonl", "line": line, "raw": json.loads(text)}


def operations(records):
    seen = set()
    for ref in records:
        if ref["file"] != "otel/spans.jsonl":
            continue
        row = ref["raw"]
        if row.get("schema") != "abb.agent-otel.v1" or row.get("origin") not in ("agent_native", "auto_instrumented"):
            continue
        data = display_span(row)
        key = (data["trace_id"], data["span_id"])
        if key in seen:
            continue
        seen.add(key)
        attrs = data["attributes"]
        op = attrs.get("gen_ai.operation.name", "")
        typ = attrs.get("openinference.span.kind")
        kind = ("tool" if op == "execute_tool" or typ == "TOOL" else
                "model" if op in ("chat", "generate_content", "text_completion") or typ == "LLM" else "span")
        yield {**data, "kind": kind, "ref": ref,
               "tool_call_id": attrs.get("gen_ai.tool.call.id"), "call_id": attrs.get("abb.call_id"),
               "input_id": row.get("context", {}).get("input_id") or attrs.get("abb.input_id"),
               "case_id": row.get("context", {}).get("case_id"),
               "invocation_id": row.get("context", {}).get("invocation_id") or attrs.get("abb.invocation_id"),
               "native_session_id": attrs.get("openclaw.session.key") or attrs.get("gen_ai.conversation.id")}


def _decoded(value):
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def content(item):
    attrs = item["attributes"]
    if item["kind"] == "tool":
        return {"tool_name": attrs.get("gen_ai.tool.name") or attrs.get("tool.name") or item["name"],
                "input_arguments": _decoded(attrs.get("gen_ai.tool.call.arguments", attrs.get("input.value"))),
                "outputs": _decoded(attrs.get("gen_ai.tool.call.result", attrs.get("output.value")))}
    if item["kind"] == "model":
        return {"input": _decoded(attrs.get("gen_ai.input.messages", attrs.get("input.value"))),
                "output": _decoded(attrs.get("gen_ai.output.messages", attrs.get("output.value")))}
    return {}


def emitted_ids(item):
    messages = content(item).get("output")
    if not isinstance(messages, list):
        return ()
    return tuple(sorted({part["id"] for msg in messages if isinstance(msg, dict) and msg.get("role") == "assistant"
                         for part in (msg.get("parts") or []) if isinstance(part, dict)
                         and part.get("type") == "tool_call" and isinstance(part.get("id"), str)}))


def correlate(records, operations):
    """Return matched records; conflicting/missing IDs stay in the raw inventory."""
    by_key = defaultdict(list)
    for record in records:
        field = "tool_call_id" if record["kind"] == "tool" else "call_id"
        if record.get(field):
            by_key[(field, record[field])].append(record)
        if record["kind"] == "model":
            output = record.get("client_output") or record.get("output") or {}
            calls = output.get("tool_calls") if isinstance(output, dict) else None
            ids = tuple(sorted({c["id"] for c in calls or [] if isinstance(c, dict) and isinstance(c.get("id"), str)}))
            if ids:
                by_key[("emitted", ids)].append(record)
    selected = []
    counts = Counter()
    for item in operations:
        field = "tool_call_id" if item["kind"] == "tool" else "call_id"
        candidates = by_key.get((field, item[field]), ()) if item["kind"] in ("model", "tool") else ()
        if not candidates and item["kind"] == "model":
            candidates = by_key.get(("emitted", emitted_ids(item)), ())
        matches = [record for record in candidates if compatible(record, item)]
        match = matches[0] if len(matches) == 1 else None
        if match:
            counts[id(match)] += 1
        selected.append((item, match))
    for item, match in selected:
        yield item, match if match is not None and counts[id(match)] == 1 else None


def flat_evidence(api, steps, indexed_rows, limit):
    scopes = {row["id"]: {key: row.get(key) for key in (*SCOPE_KEYS, "identity_conflicts")} for row in indexed_rows}
    records = []
    for step in steps:
        if step["kind"] == "model":
            records.append({**scopes.get(step["evidence"].get("interaction_id"), {}), "kind": "model", **step["evidence"], "output": step.get("output") or {}, "target": step["evidence"]})
        for log in step["tool_logs"]:
            records.append({**scopes.get(log["evidence"].get("interaction_id") or step.get("evidence", {}).get("interaction_id"), {}),
                            "kind": "tool", "log": log, "tool_call_id": log.get("tool_call_id"), "target": log["evidence"]})
    remaining = []
    for item, match in correlate(records, operations(rows(api))):
        ref = {k: item["ref"][k] for k in ("file", "line")}
        ref.update(trace_id=item["trace_id"], span_id=item["span_id"], origin=item["origin"])
        if match:
            match["target"].setdefault("agent_otel", []).append(ref)
            log = match.get("log")
            if log is not None and log.get("execution_status") == "not_observed" and log.get("link") != "ambiguous":
                values = content(item)
                if item.get("end_time") and values["outputs"] is not None:
                    failed = item["status"].get("code") == 2 or isinstance(values["outputs"], dict) and values["outputs"].get("isError") is True
                    log.update(outputs=bounded(values["outputs"], limit), execution_status="error" if failed else "succeeded",
                               link="exact", source=item["origin"], started_at=item.get("start_time"), ended_at=item.get("end_time"))
        else:
            remaining.append({**ref, "operation": item["kind"], "name": item["name"], "parent_span_id": item["parent_span_id"],
                              "native_session_id": item["native_session_id"], **bounded(content(item), limit)})
    return remaining
