"""Framework callbacks are the step record: LangChain model and tool spans.

The interceptor wire record joins a callback only through the recorded span id.
Agent-exported OTel stays evidence: a span is linked to the callback it matches
by identifier and never becomes a model step of its own.
"""
from copy import deepcopy

from agentbench.observe.tool_links import compatible
from agentbench.trajectory.content import model_input, model_output, framework_input, framework_output
from agentbench.trajectory.sources import _data, framework_calls, wire_calls, wire_stream, tool_log, tool_rows
from ..contracts import EvidenceIssue, stable_id
from .base import Recorded, _scope, _span_key, otel_tool, references


class LangGraphSource:
    name = "langgraph"
    # The delivered result is projected as its own step unless a model step carries it.
    reply_steps = True
    exported_steps = False
    reads_network = False

    def recorded(self, index, *, include_network, issues):
        return _recorded(index, include_network, issues)

    def adopt(self, item, issues):
        """An exported tool span no callback recorded is still an observed execution."""
        return otel_tool(item) if item["kind"] == "tool" else None

    def complete(self, models, tools, native, issues, other_spans):
        pass


def _recorded(index, include_network, issues):
    spans, native = {}, []
    for row in index.rows:
        records = index.groups[row["id"]]
        start_record = next((r for r in records if r["raw"].get("event") == "span_start"), None)
        if start_record:
            data = _data(start_record)
            key = _span_key(start_record, data.get("span_id"))
            spans[key] = {**_scope(row), "id": key, "row_id": row["id"],
                "native_id": data.get("span_id"), "source_file": start_record["file"],
                "status": row.get("status", "unknown"),
                "parent": _span_key(start_record, data.get("parent_span_id")),
                "kind": data.get("kind"), "name": data.get("name"), "input": data.get("input"),
                "metadata": data.get("metadata") or {}, "tool_call_id": row.get("tool_call_id"),
                "evidence": references(records)}
            starts = [r for r in records if r["raw"].get("event") == "span_start"]
            if len({stable_id(r["file"], _data(r)) for r in starts}) > 1:
                spans[key]["identity_conflicts"] = ["duplicate_span_boundary"]
                issues.append(EvidenceIssue("duplicate_span_boundary", "Incompatible starts share a grouped span ID", [row["id"]]))
        for record in records:
            if record["raw"].get("event") in ("native_event", "native_model_call"):
                native.append({"data": deepcopy(_data(record)), "evidence": references([record]), **_scope(row)})

    frameworks = framework_calls(index)
    wires = wire_calls(index) if include_network else []
    matched = {wire["id"]: [f for f in frameworks if f.get("framework_span_id")
        and f["framework_span_id"] == wire.get("framework_span_id") and compatible(wire, f)] for wire in wires}
    counts = {f["id"]: sum(f in values for values in matched.values()) for f in frameworks}
    used, models = set(), []

    def framework_key(row):
        return _span_key(row.get("_request"), row.get("framework_span_id"))

    for wire in wires:
        records = index.groups[wire["id"]]
        request, response = _data(wire.get("_request")), _data(wire.get("_response"))
        candidates = matched[wire["id"]]
        framework = candidates[0] if len(candidates) == 1 else None
        merge = framework is not None and counts[framework["id"]] == 1
        stream = wire_stream(records)
        output = model_output(response.get("payload") if wire.get("_response") else stream)
        status = "error" if wire.get("status") == "failed" else "complete" if wire.get("_response") else "incomplete"
        errors = [_data(r) for r in records if r["raw"].get("event") == "llm_error"]
        # Successful HTTP transport does not establish successful model output.
        # Preserve actual provider terminal events, including incomplete Responses.
        for payload in (response.get("payload"), response.get("client_payload"), stream):
            if not isinstance(payload, dict):
                continue
            for part in [payload, *(payload.get("events") or [])]:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "response.incomplete":
                    if status != "error":
                        status = "incomplete"
                    errors.append(part)
                elif part.get("error") or part.get("type") in ("error", "response.failed"):
                    status = "error"
                    errors.append(part)
        entry = {**_scope(wire), "id": wire["id"], "kind": "model", "call_id": wire.get("call_id"),
            "span": framework_key(framework) if framework else None,
            "input": model_input(request.get("payload")), "output": output,
            "client_output": model_output(response["client_payload"]) if response.get("client_payload") is not None else None,
            "raw_request": deepcopy(request), "raw_response": deepcopy(response),
            "stream": deepcopy(stream),
            "status": status, "error": errors or None, "timestamp": wire.get("timestamp"), "ended_at": wire.get("ended"),
            "evidence": references(records), "source": "wire", "framework_output": None}
        # The legacy normalizer treats an empty OpenAI argument string as {}.
        # An interrupted stream has not supplied an empty-object argument yet.
        if status != "complete" and stream:
            fragments = {}
            for frame in stream.get("events", []):
                for choice in frame.get("choices", []) if isinstance(frame, dict) else []:
                    for part in (choice.get("delta") or {}).get("tool_calls", []):
                        item = fragments.setdefault(part.get("index", 0), {"id": None, "text": ""})
                        item["id"] = part.get("id") or item["id"]
                        item["text"] += (part.get("function") or {}).get("arguments") or ""
            empty = {part["id"] for part in fragments.values() if not part["text"].strip()}
            for call in output.get("tool_calls", []):
                if call.get("id") in empty:
                    call["arguments"] = ""
        if merge:
            used.add(framework["id"])
            entry.update(source="wire+framework", framework_output=framework_output(_data(framework.get("_response")).get("output")))
            entry["evidence"] += references(index.groups[framework["id"]])
            for key, value in _scope(framework).items():
                if not entry.get(key):
                    entry[key] = value
        if len(candidates) > 1:
            issues.append(EvidenceIssue("ambiguous_framework", "Multiple compatible model spans", [entry["id"]]))
        if status != "complete":
            issues.append(EvidenceIssue("unfinished_or_failed_model", status, [entry["id"]]))
        models.append(entry)
    for row in frameworks:
        if row["id"] in used:
            continue
        # A callback shared by retries is retained as evidence, not another inference.
        if counts[row["id"]]:
            for entry in models:
                if entry["span"] == framework_key(row):
                    entry["evidence"] += references(index.groups[row["id"]])
                    entry["shared_framework_output"] = deepcopy(_data(row.get("_response")).get("output"))
            continue
        models.append({**_scope(row), "id": row["id"], "kind": "model", "span": framework_key(row),
            "input": framework_input(_data(row.get("_request")).get("input")),
            "output": framework_output(_data(row.get("_response")).get("output")),
            "raw_request": deepcopy(_data(row.get("_request"))), "raw_response": deepcopy(_data(row.get("_response"))),
            "status": "error" if row.get("status") == "failed" else "complete" if row.get("_response") else "incomplete",
            "timestamp": row.get("timestamp"), "ended_at": row.get("ended"), "source": "framework",
            "evidence": references(index.groups[row["id"]])})
    tools = []
    for row in tool_rows(index):
        log = tool_log(index, row)
        if log["execution_status"] != "succeeded":
            issues.append(EvidenceIssue("tool_" + log["execution_status"], "Tool execution did not record success", [row["id"]]))
        tools.append({**_scope(row), **log, "id": row["id"], "kind": "tool",
            "span": framework_key(row), "timestamp": row.get("timestamp"),
            "evidence": references(index.groups[row["id"]]),
            "raw_records": [deepcopy(r["raw"]) for r in index.groups[row["id"]]]})
    return Recorded(models, tools, spans, native)
