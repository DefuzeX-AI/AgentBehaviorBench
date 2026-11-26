"""An ACP Agent's own OTel export is the step record, completed by two more.

Model steps come from its inference spans and tool results from its tool
spans. The interceptor's wire record and the Agent's ACP messages recorded the
same run on their own clocks: an operation they share with a span is merged
into that span's record, and one only they recorded becomes a record of its
own (``merge.py``). The records ABB writes while relaying ACP
(``framework.jsonl``) are not read.
"""
from collections import defaultdict

from ..contracts import EvidenceIssue
from .base import Recorded, otel_model, otel_tool
from .merge import merge, network_models


class AcpOtelSource:
    name = "acp_otel"
    # The last model step of a turn is the reply; the delivered result is not repeated.
    reply_steps = False
    exported_steps = True
    reads_network = True

    def __init__(self):
        self.network = []

    def recorded(self, index, *, include_network, issues):
        return Recorded([], [], {}, [])

    def read_network(self, index):
        """Keep the wire calls until the spans are read; ``complete`` merges them."""
        self.network = network_models(index)

    def adopt(self, item, issues):
        if item["kind"] == "tool":
            return otel_tool(item)
        return otel_model(item, issues) if item["kind"] == "model" else None

    def complete(self, models, tools, native, issues, other_spans):
        if not models:
            issues.append(EvidenceIssue("agent_otel_models_missing",
                "The Agent exported no inference span with message content; the trajectory has no model step"))
        exported = models + tools
        # A span is exported when it ends, its parent last. An operation whose
        # parent never arrived means the export stopped before the run did, so
        # later operations of that run, such as its final reply, may be absent.
        received = {(ref["trace_id"], ref["span_id"]) for record in exported for ref in record.get("agent_otel", [])}
        received |= {(span["trace_id"], span["span_id"]) for span in other_spans}
        cut = [record["id"] for record in exported for ref in record.get("agent_otel", [])
               if ref.get("parent_span_id") and (ref["trace_id"], ref["parent_span_id"]) not in received]
        if cut:
            issues.append(EvidenceIssue("agent_otel_export_incomplete",
                "Operations name a parent span that was never received; the run's export is incomplete", cut))
        merge(models, tools, self.network, native)
        for record in models:
            if record["source"] == "wire" and record["status"] != "complete":
                issues.append(EvidenceIssue("unfinished_or_failed_model", record["status"], [record["id"]]))
        _inherit_sessions(models, tools)


def _inherit_sessions(models, tools):
    """Spread a tool's ACP session to the operations recorded beside it.

    An inference names the session of the tool calls it emitted. Operations
    exported under one parent span belong to one run of the Agent, so an
    operation without a session takes the only session known under that span.
    """
    by_call = {tool["tool_call_id"]: tool for tool in tools if tool.get("tool_call_id")}
    for model in models:
        emitted = [by_call[call["id"]] for call in model["output"].get("tool_calls") or [] if call.get("id") in by_call]
        _take(model, [tool for tool in emitted if tool.get("native_session_id")])
    groups = defaultdict(list)
    for record in models + tools:
        parents = {ref.get("parent_span_id") for ref in record.get("agent_otel", [])}
        if len(parents) == 1 and None not in parents:
            groups[(record["agent_otel"][0]["trace_id"], parents.pop())].append(record)
    for group in groups.values():
        known = [record for record in group if record.get("native_session_id")]
        for record in group:
            _take(record, known)


def _take(record, holders):
    sessions = {holder["native_session_id"] for holder in holders}
    if record.get("native_session_id") or len(sessions) != 1 or record.get("identity_conflicts"):
        return
    record["native_session_id"] = sessions.pop()
    record["session_evidence"] = [ref for holder in holders for ref in holder.get("session_evidence", [])]
