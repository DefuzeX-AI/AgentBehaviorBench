"""OpenCode task metadata and optional recorded native response/turn identity."""
from collections import defaultdict
from agentbench.observe.native_links import response_ids
from agentbench.observe.tool_links import compatible
from ..contracts import DelegationEvidence, EvidenceIssue, execution_key, ExecutionNode, DelegationLink


class OpenCodeAdapter:
    def identify(self, evidence):
        result = DelegationEvidence()
        relations = {}
        for event in evidence.native_events:
            data = event["data"]
            payload = data.get("payload", data)
            update = payload.get("update", payload) if isinstance(payload, dict) else {}
            if not isinstance(update, dict):
                continue
            output = update.get("rawOutput")
            for metadata in (update.get("_meta"), update.get("metadata"),
                             output.get("metadata") if isinstance(output, dict) else None):
                if not isinstance(metadata, dict):
                    continue
                parent, child = metadata.get("parentSessionId"), metadata.get("sessionId")
                if not parent or not child or parent == child:
                    continue
                identity = (data.get("invocation_id"), parent, child, update.get("toolCallId"))
                relations.setdefault(identity, {"parent_session_id": parent, "child_session_id": child,
                    "tool_call_id": update.get("toolCallId"), "invocation_id": data.get("invocation_id"),
                    "evidence": event.get("evidence", []), "status": "internal_records_missing"})
        by_session = defaultdict(list)
        for identity, fact in relations.items():
            by_session[(identity[0], identity[2])].append(fact)
        native = [e for e in evidence.native_events if e["data"].get("native_response_id")
                  and e["data"].get("native_turn_id") and e["data"].get("native_session_id")]
        for identity, fact in relations.items():
            invocation, parent, child, call_id = identity
            tool_candidates = [t for t in evidence.tools if call_id and t.get("tool_call_id") == call_id and compatible(t, fact)]
            calls = [e for e in native if e["data"]["native_session_id"] == child and compatible(e["data"], fact)]
            turns = {e["data"]["native_turn_id"] for e in calls}
            owned = []
            # Reused sessions require the particular turn's delegation identity.
            # Neither text equality nor time proximity supplies that identity.
            if len(by_session[(invocation, child)]) == len(tool_candidates) == len(turns) == 1:
                for event in calls:
                    matches = [m for m in evidence.models if event["data"]["native_response_id"] in
                               response_ids(m.get("raw_response", {}).get("payload")) and compatible(m, fact)]
                    competing = [e for e in native if e["data"]["native_response_id"] == event["data"]["native_response_id"]]
                    if len(matches) == len(competing) == 1:
                        owned.append(matches[0]["id"])
                if owned:
                    turn, = turns
                    key = execution_key(evidence, invocation, "opencode", turn, native_session_id=child)
                    args = tool_candidates[0].get("input_arguments")
                    name = args.get("subagent_type") if isinstance(args, dict) else None
                    refs = fact["evidence"] + [r for event in calls for r in event.get("evidence", [])]
                    result.nodes.append(ExecutionNode(key, name or "unknown", evidence=refs, record_ids=sorted(set(owned))))
                    result.links.append(DelegationLink(None, key.id, tool_candidates[0]["id"], refs))
                    fact.update(status="native_models_linked", native_turn_id=turn, execution_id=key.id)
                    result.issues.append(EvidenceIssue("native_child_input_unavailable", "No distinct child input event was recorded", owned))
                    continue
            result.issues.append(EvidenceIssue("native_child_records_missing",
                "Structured delegation observed; no unambiguous child turn and internal model records",
                [str(v) for v in identity if v]))
        result.facts.extend(relations.values())
        if not relations:
            result.issues.append(EvidenceIssue("native_hierarchy_not_observed",
                "No structured OpenCode parent/child session relation was recorded"))
        return result
