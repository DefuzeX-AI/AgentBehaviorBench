"""Recognize native OpenClaw sessions_spawn receipts and the operations of their child runs.

A child's operations are attributed in one of two ways, both from recorded identifiers:

1. Session: an operation names the child session key of exactly one accepted receipt.
2. Run structure, for exports whose spans name no session (diagnostics-otel 2026.9.5):
   - every model call and tool execution is a child span of the ``openclaw.run`` it ran in;
   - a run is a child span of its ``openclaw.harness.run``;
   - the harness span of a spawned run is a child span of the spawning run's harness span.
   - a nested run whose inference input carries the id of a tool call made in the spawning
     run continues that run's conversation (OpenClaw's completion notice to the requester).
     It is not a child, provided every spawn of that run was ``context: isolated``; a child
     that inherits the conversation would carry the same ids.
   When one run executed exactly one accepted spawn and exactly one other run is nested
   under its harness span, that nested run is the spawned child. Any other count pairs nothing.
"""
from collections import Counter, defaultdict
import re

from agentbench.observe.tool_links import compatible
from ..contracts import DelegationEvidence, DelegationLink, EvidenceIssue, ExecutionNode, execution_key


RUN, HARNESS = "openclaw.run", "openclaw.harness.run"


class _Runs:
    """The run structure of the exported spans."""

    def __init__(self, evidence):
        self.spans = {(span["trace_id"], span["span_id"]): span for span in evidence.unassigned_agent_spans}
        self.members, self.nested = defaultdict(list), defaultdict(list)
        for record in evidence.models + evidence.tools:
            run = self.of(record)
            if run:
                self.members[run].append(record)
        for key, span in self.spans.items():
            harness = self.harness(key) if span["name"] == RUN else None
            outer = self._parent(harness, HARNESS) if harness else None
            if outer:
                self.nested[outer].append(key)

    def _parent(self, key, name):
        parent = (key[0], self.spans[key].get("parent_span_id"))
        return parent if self.spans.get(parent, {}).get("name") == name else None

    def of(self, record):
        """The ``openclaw.run`` span an exported operation is a child of."""
        refs = record.get("agent_otel") or []
        if len(refs) != 1:
            return None
        run = (refs[0]["trace_id"], refs[0].get("parent_span_id"))
        return run if self.spans.get(run, {}).get("name") == RUN else None

    def harness(self, run):
        return self._parent(run, HARNESS)

    def reference(self, key):
        return {name: self.spans[key][name] for name in ("file", "line", "digest")}


def _plain(call_id):
    """OpenClaw replays a session's history with tool call ids reduced to letters and digits."""
    return re.sub(r"[^A-Za-z0-9]", "", call_id)


def _history_calls(model):
    """Tool call ids in the conversation an inference was given, in their replayed spelling."""
    messages = (model.get("input") or {}).get("messages")
    return {_plain(part["id"]) for message in messages if isinstance(message, dict)
            for part in message.get("parts") or [] if isinstance(part, dict)
            and part.get("type") in ("tool_call", "tool_call_response") and isinstance(part.get("id"), str)
            } if isinstance(messages, list) else set()


def _identifier(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or not value.strip("*") or value.casefold() in {"[redacted]", "<redacted>"}:
        return None
    return value


class OpenClawAdapter:
    def identify(self, evidence):
        result = DelegationEvidence()
        spawns = defaultdict(list)
        runs = _Runs(evidence)
        spawned_in, inheriting = Counter(), set()
        for tool in evidence.tools:
            name = tool.get("tool_name")
            if not isinstance(name, str) or name.partition(":")[0].strip() != "sessions_spawn":
                continue
            output = tool.get("outputs")
            receipt = output.get("details") if isinstance(output, dict) else None
            if (not isinstance(receipt, dict) or receipt.get("status") != "accepted" or output.get("isError")
                    or tool.get("execution_status") != "succeeded" or tool.get("identity_conflicts")
                    or not isinstance(receipt.get("childSessionKey"), str) or not receipt["childSessionKey"].strip()):
                continue
            spawned_in[runs.of(tool)] += 1
            if receipt.get("context") != "isolated":
                inheriting.add(runs.of(tool))
            run_id = _identifier(receipt.get("runId"))
            if not run_id:
                result.issues.append(EvidenceIssue("openclaw_child_run_missing",
                    "Accepted spawn has no usable child run ID", [tool["id"]]))
                continue
            spawns[run_id].append((tool, _identifier(receipt["childSessionKey"])))

        if not spawns:
            return result

        # Nested runs that continue the spawning run's own conversation are not children.
        children = {}
        for parent_run in spawned_in:
            harness = runs.harness(parent_run) if parent_run else None
            if not harness:
                continue
            calls = [tool for tool in runs.members[parent_run] if tool["kind"] == "tool" and tool.get("tool_call_id")]
            spellings = Counter(_plain(tool["tool_call_id"]) for tool in calls)
            # Two ids with one replayed spelling identify nothing.
            made = {_plain(tool["tool_call_id"]): tool for tool in calls if spellings[_plain(tool["tool_call_id"])] == 1}
            children[parent_run] = []
            for nested_run in runs.nested.get(harness, []):
                given = set().union(*(_history_calls(r) for r in runs.members[nested_run] if r["kind"] == "model"))
                anchors = sorted(given & made.keys())
                if anchors and parent_run not in inheriting:
                    for record in runs.members[nested_run]:
                        result.same_execution[record["id"]] = made[anchors[0]]["id"]
                else:
                    children[parent_run].append(nested_run)

        # A session can be reused. Its records only identify a particular run
        # when exactly one recorded spawn uses that session.
        session_counts = Counter(session for group in spawns.values() for _, session in group if session)
        native_records = defaultdict(list)
        framework_models = [m for m in evidence.models if m.get("source") in ("framework", "agent_native", "auto_instrumented")]
        for record in evidence.tools + framework_models:
            session = record.get("native_session_id")
            if session and session_counts[session] == 1:
                native_records[session].append(record)

        record_owners = {}
        for run_id, group in spawns.items():
            if len(group) != 1:
                result.issues.append(EvidenceIssue("openclaw_ambiguous_spawn",
                    "Multiple spawn calls claimed the same child run", [tool["id"] for tool, _ in group]))
                continue
            (tool, session), = group
            parent = tool.get("native_session_id")
            if parent and parent == session:
                result.issues.append(EvidenceIssue("openclaw_self_delegation",
                    "The spawn receipt identifies the calling session as its own child", [tool["id"]]))
                continue
            refs = [*tool["evidence"], *tool.get("session_evidence", [])]
            # The run ID survives redaction of the session key in structured
            # receipts. Never recover the hidden key by parsing display text.
            key = execution_key(evidence, tool.get("invocation_id"), "openclaw", run_id,
                                native_session_id=session)
            child_scope = {**tool, "native_session_id": session}
            owned = [r["id"] for r in native_records.get(session, ()) if compatible(child_scope, r)]
            attribution = "session" if owned else None
            parent_run = runs.of(tool)
            nested = children.get(parent_run, [])
            if not owned and nested:
                if spawned_in[parent_run] == 1 and len(nested) == 1:
                    child_run, = nested
                    owned = [r["id"] for r in runs.members[child_run]
                             if not r.get("native_session_id") and not r.get("identity_conflicts")]
                    attribution = "run_structure"
                    refs = [*refs, runs.reference(child_run), runs.reference(runs.harness(child_run))]
                else:
                    result.issues.append(EvidenceIssue("openclaw_child_run_ambiguous",
                        "Several spawns or nested runs share one run; no recorded identifier pairs them", [tool["id"]]))
            args = tool.get("input_arguments")
            args = args if isinstance(args, dict) else {}
            task = args.get("task")
            task = task if isinstance(task, str) and task.strip() else None
            fact = {"parent_session_id": parent, "child_run_id": run_id, "child_session_id": session,
                    "invocation_id": tool.get("invocation_id"), "tool_call_id": tool.get("tool_call_id"),
                    "status": "accepted", "attribution": attribution, "evidence": refs}
            result.facts.append(fact)
            if not owned:
                result.issues.append(EvidenceIssue("native_child_records_missing",
                    "OpenClaw accepted the task; no internal child operation could be attributed", [tool["id"]]))
            if task is None and not owned:
                continue
            name = _identifier(args.get("agentId")) or "OpenClaw subagent"
            result.nodes.append(ExecutionNode(key, name, input=task, evidence=refs, record_ids=owned, status="accepted"))
            result.links.append(DelegationLink(None, key.id, tool["id"], refs))
            for rid in owned:
                record_owners[rid] = key.id
        for link in result.links:
            link.parent_id = record_owners.get(link.tool_id)
        return result
