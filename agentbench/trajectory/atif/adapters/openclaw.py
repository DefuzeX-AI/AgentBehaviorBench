"""Recognize native OpenClaw sessions_spawn receipts and their recorded child sessions."""
from collections import Counter, defaultdict

from agentbench.observe.tool_links import compatible
from ..contracts import DelegationEvidence, DelegationLink, EvidenceIssue, ExecutionNode, execution_key


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
            run_id = _identifier(receipt.get("runId"))
            if not run_id:
                result.issues.append(EvidenceIssue("openclaw_child_run_missing",
                    "Accepted spawn has no usable child run ID", [tool["id"]]))
                continue
            spawns[run_id].append((tool, _identifier(receipt["childSessionKey"])))

        if not spawns:
            return result

        # A session can be reused. Its records only identify a particular run
        # when exactly one recorded spawn uses that session.
        session_counts = Counter(session for group in spawns.values() for _, session in group if session)
        native_records = defaultdict(list)
        framework_models = [m for m in evidence.models if m.get("source") == "framework"]
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
            args = tool.get("input_arguments")
            args = args if isinstance(args, dict) else {}
            task = args.get("task")
            task = task if isinstance(task, str) and task.strip() else None
            fact = {"parent_session_id": parent, "child_run_id": run_id, "child_session_id": session,
                    "invocation_id": tool.get("invocation_id"), "tool_call_id": tool.get("tool_call_id"),
                    "status": "accepted", "evidence": refs}
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
