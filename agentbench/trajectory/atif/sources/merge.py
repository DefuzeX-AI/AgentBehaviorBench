"""Merge an ACP Agent's three records into one set of step records.

A run is recorded three times, each with its own clock:

- ``trace``: the spans the Agent exported (model calls and tool executions);
- ``network``: the interceptor's wire record of every model call;
- ``acp``: the Agent's ACP messages (prompts, tool call reports, reply text).

One operation seen by several of them becomes one record that names its
``sources``; an operation only one of them recorded is kept as it is.

- A model call is the same in ``trace`` and ``network`` when its output is: the
  ids of the tool calls it emitted, or its text when it emitted none. Equal
  outputs pair in recorded order.
- A tool execution is the same in ``trace`` and ``acp`` when the tool call id is.
- Reply text a session sent over ACP is the text of the model call that
  produced it. When one model call alone has that text, it ran in that session.

Every record gets a ``clock`` for the shared timeline: the span start, else
the ACP report, else the wire request moved back by ``NETWORK_LEAD``.
"""
from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from agentbench.observe.tool_links import compatible
from agentbench.trajectory.content import model_input, model_output
from agentbench.trajectory.sources import _data, wire_calls, wire_stream
from ..contracts import stable_id
from .base import references

NETWORK, TRACE, ACP = "network", "trace", "acp"
# The interceptor sees a request about this long after the Agent starts the
# span of the same call (median of recorded pairs).
NETWORK_LEAD = timedelta(milliseconds=140)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_TERMINAL = {"completed": "succeeded", "failed": "error"}


def clock(timestamp, lead=timedelta(0)):
    """A recorded ISO timestamp as a timeline position, or None when it is not one."""
    if not isinstance(timestamp, str):
        return None
    try:
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    moment -= lead
    elapsed = moment - _EPOCH
    micros = (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds
    return {"start_time": moment.isoformat(), "unix_nano": micros * 1000}


def started(record):
    """Timeline position of a record: its exported span, else its own clock."""
    spans = [ref for ref in record.get("agent_otel", []) if ref.get("start_time") and ref.get("unix_nano")]
    if len(spans) == 1:
        return {**spans[0], "unix_nano": int(spans[0]["unix_nano"])}
    return record.get("clock")


def _parsed(data):
    """A wire record without the unparsed copies of the body it already holds parsed."""
    return deepcopy({key: value for key, value in data.items() if key not in ("raw_body", "source_raw_body", "source_payload")})


def network_models(index):
    """Every model call the interceptor recorded, in the shape of a model record."""
    models = []
    for wire in wire_calls(index):
        records = index.groups[wire["id"]]
        request, response = _data(wire.get("_request")), _data(wire.get("_response"))
        answered = wire.get("_response") is not None
        stream = None if answered else wire_stream(records)
        # An answered call is its request and its response; the stream frames
        # between them repeat the response and are not cited one by one.
        cited = [wire["_request"], wire["_response"]] if answered else records
        models.append({
            "run_id": wire.get("run_id"), "case_id": wire.get("case_id"), "attempt_id": wire.get("attempt_id"),
            # The wire names no Input, invocation or session of its own.
            "input_id": None, "invocation_id": None, "native_session_id": None,
            "identity_conflicts": wire.get("identity_conflicts"),
            "id": wire["id"], "kind": "model", "source": "wire", "call_id": wire.get("call_id"), "span": None,
            "input": model_input(request.get("payload")),
            "output": model_output(response.get("payload") if answered else stream),
            "client_output": model_output(response["client_payload"]) if response.get("client_payload") is not None else None,
            "framework_output": None, "raw_request": _parsed(request), "raw_response": _parsed(response),
            "stream": deepcopy(stream), "error": None,
            "status": "error" if wire.get("status") == "failed" else "complete" if answered else "incomplete",
            "timestamp": wire.get("timestamp"), "ended_at": wire.get("ended"), "evidence": references(cited),
            "sources": [NETWORK], "clock": clock(wire.get("timestamp"), NETWORK_LEAD)})
    return models


def output_key(record):
    """What identifies a model call's output in both ``trace`` and ``network``."""
    output = record.get("client_output") or record.get("output") or {}
    ids = tuple(sorted(call["id"] for call in output.get("tool_calls") or []
                       if isinstance(call, dict) and isinstance(call.get("id"), str)))
    text = output.get("text")
    return ("tool_calls", ids) if ids else ("text", text.strip() if isinstance(text, str) else "")


def _in_order(records):
    return sorted(records, key=lambda record: ((started(record) or {}).get("unix_nano", 0),
                                               min((ref["file"], ref["line"]) for ref in record["evidence"])))


def pair_models(trace, network):
    """(trace record, network record) for each model call both recorded."""
    waiting = defaultdict(deque)
    for record in _in_order(network):
        waiting[output_key(record)].append(record)
    pairs = []
    for record in _in_order(trace):
        queue = waiting.get(output_key(record))
        if queue and compatible(record, queue[0]):
            pairs.append((record, queue.popleft()))
    return pairs


def acp_tool_reports(native):
    """The ACP messages about each tool call, by (session, tool call id)."""
    reports = defaultdict(list)
    for event in native:
        data = event.get("data") or {}
        update = data.get("update")
        if (event.get("event") == "session_update" and isinstance(update, dict)
                and update.get("sessionUpdate") in ("tool_call", "tool_call_update")
                and isinstance(update.get("toolCallId"), str) and update["toolCallId"]):
            reports[data.get("session_id"), update["toolCallId"]].append(event)
    return reports


def acp_tool(session, call_id, events):
    """A tool execution as the Agent reported it over ACP."""
    reported = {}
    for event in events:
        reported.update({key: value for key, value in event["data"]["update"].items() if value is not None})
    first, last = events[0], events[-1]
    data = first["data"]
    refs = [ref for event in events for ref in event.get("evidence", [])]
    return {"run_id": None, "case_id": data.get("case_id"), "attempt_id": data.get("attempt_id"),
            "input_id": data.get("input_id"), "invocation_id": data.get("invocation_id"),
            "native_session_id": session, "identity_conflicts": None,
            "id": stable_id("acp_tool", refs[0]["file"] if refs else None, session, call_id),
            "kind": "tool", "source": ACP, "span": None, "tool_call_id": call_id,
            # ACP names a tool by its display title; nothing is parsed out of it.
            "tool_name": reported.get("title") or reported.get("kind") or "unknown",
            "input_arguments": reported.get("rawInput"),
            "outputs": reported["rawOutput"] if "rawOutput" in reported else reported.get("content"),
            "execution_status": _TERMINAL.get(reported.get("status"), "not_observed"),
            "timestamp": first.get("timestamp"), "started_at": first.get("timestamp"),
            "ended_at": last.get("timestamp") if reported.get("status") in _TERMINAL else None,
            "evidence": list(refs), "session_evidence": list(refs),
            "sources": [ACP], "clock": clock(first.get("timestamp"))}


def reply_segments(native):
    """Text each session sent over ACP, cut where a tool call or a prompt boundary interrupts it."""
    segments, current = [], {}
    for event in native:
        name, data = event.get("event"), event.get("data") or {}
        if name in ("prompt_started", "prompt_completed", "failure"):
            current.clear()
            continue
        if name != "session_update" or not event.get("evidence"):
            continue
        session, update = data.get("session_id"), data.get("update") or {}
        kind = update.get("sessionUpdate")
        if kind in ("tool_call", "tool_call_update"):
            current.pop(session, None)
            continue
        content = update.get("content") or {}
        if kind != "agent_message_chunk" or content.get("type") != "text" or not isinstance(content.get("text"), str):
            continue
        if session not in current:
            current[session] = {"session": session, "text": "", "evidence": [], "clock": clock(event.get("timestamp")),
                                "scope": {key: data.get(key) for key in ("input_id", "invocation_id")}}
            segments.append(current[session])
        current[session]["text"] += content["text"]
        current[session]["evidence"].extend(event["evidence"])
    return [segment for segment in segments if segment["text"].strip()]


def _text(record):
    text = (record.get("client_output") or record.get("output") or {}).get("text")
    return text.strip() if isinstance(text, str) else ""


def merge(models, tools, network, native):
    """Fold the wire and ACP records into the exported ones, in place."""
    for record in models + tools:
        record["sources"] = [TRACE]
    paired = set()
    for record, wire in pair_models(models, network):
        paired.add(wire["id"])
        record["sources"] = [NETWORK, TRACE]
        record["call_id"] = record.get("call_id") or wire["call_id"]
        record["evidence"] = [*record["evidence"], *wire["evidence"]]
    models.extend(wire for wire in network if wire["id"] not in paired)
    reports = acp_tool_reports(native)
    used = set()
    for tool in tools:
        matches = [key for key, events in reports.items() if key[1] == tool.get("tool_call_id")
                   and all(compatible(tool, event["data"]) for event in events)]
        # One session reported this call: it is the same execution.
        if len(matches) == 1 and not tool.get("identity_conflicts"):
            used.add(matches[0])
            tool["sources"] = [TRACE, ACP]
            tool["evidence"] = [*tool["evidence"], *(ref for event in reports[matches[0]] for ref in event.get("evidence", []))]
    known = {tool.get("tool_call_id") for tool in tools}
    # A call id an exported tool carries but could not be matched to stays with that tool.
    tools.extend(acp_tool(session, call_id, events) for (session, call_id), events in reports.items()
                 if (session, call_id) not in used and call_id not in known)
    for segment in reply_segments(native):
        session = segment["session"]
        said = [model for model in _in_order(models) if ACP not in model["sources"]
                and _text(model) == segment["text"].strip() and compatible(model, {"native_session_id": session})]
        if not said:
            continue
        model = said[0]
        model["sources"] = [*model["sources"], ACP]
        model["evidence"] = [*model["evidence"], *segment["evidence"]]
        if len(said) == 1 and session and not model.get("native_session_id") and not model.get("identity_conflicts"):
            model["native_session_id"] = session
            model["session_evidence"] = list(segment["evidence"])
