"""Contract and shared record builders of the ATIF step sources."""
from dataclasses import asdict
from typing import NamedTuple, Protocol

from agentbench.observe.artifact_paths import SESSION_OUTPUT
from agentbench.trajectory.agent_otel import content, inference
from agentbench.trajectory.sources import _data
from ..contracts import EvidenceIssue, EvidenceRef, stable_id


class Recorded(NamedTuple):
    """Records a source reads before Agent-exported OTel is correlated."""
    models: list
    tools: list
    spans: dict
    native_events: list


class StepSource(Protocol):
    """Decides which recorded evidence becomes the model and tool steps."""
    name: str
    reply_steps: bool      # the delivered result becomes a step of its own
    exported_steps: bool   # Agent-exported spans are the step record
    reads_network: bool    # the source reads the interceptor's wire record itself (``read_network``)

    def recorded(self, index, *, include_network, issues) -> Recorded: ...

    def adopt(self, item, issues):
        """The record of an exported span nothing else recorded, or None to keep it as evidence only."""

    def complete(self, models, tools, native, issues, other_spans):
        """Last pass over the collected records, once sessions are bound.

        ``other_spans`` are the exported spans that became no record."""


def references(records):
    return [asdict(EvidenceRef(r["file"], r["line"], stable_id(r["raw"]))) for r in records]


def _scope(row):
    return {k: row.get(k) for k in ("run_id", "case_id", "attempt_id", "input_id",
            "invocation_id", "native_session_id", "identity_conflicts")}


def _span_key(record, sid):
    if record and sid and record["file"] == SESSION_OUTPUT + "/framework.jsonl":
        return stable_id("framework", record["file"], _data(record).get("invocation_id"), sid)
    return stable_id("framework", record["file"], sid) if record and sid else None


def _exported(item, kind):
    return {**_scope(item), "kind": kind, "source": item["origin"],
            "id": stable_id("agent_otel", item["trace_id"], item["span_id"]), "span": None,
            "timestamp": item.get("start_time"), "ended_at": item.get("end_time"), "evidence": []}


def otel_tool(item):
    """A tool execution as the Agent exported it."""
    values = content(item)
    output = values["outputs"]
    failed = item.get("status", {}).get("code") == 2 or isinstance(output, dict) and output.get("isError") is True
    return {**_exported(item, "tool"), **values, "tool_call_id": item["tool_call_id"],
            "started_at": item.get("start_time"),
            "execution_status": "error" if failed else "succeeded" if item.get("end_time") else "not_observed"}


def otel_model(item, issues):
    """An inference as the Agent exported it, or None when the span recorded no assistant message."""
    values = inference(item)
    if values is None:
        return None
    failed = item.get("status", {}).get("code") == 2
    record = {**_exported(item, "model"), **values, "call_id": None, "client_output": None,
              "framework_output": None, "raw_request": {}, "raw_response": {}, "stream": None, "error": None,
              "status": "error" if failed else "complete" if item.get("end_time") else "incomplete"}
    if record["status"] != "complete":
        issues.append(EvidenceIssue("unfinished_or_failed_model", record["status"], [record["id"]]))
    return record
