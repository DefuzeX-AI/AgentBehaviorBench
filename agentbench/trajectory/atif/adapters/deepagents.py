"""Recognize the recorded Deep Agents tool -> named agent graph boundary."""
from agentbench.observe.tool_links import compatible
from ..contracts import DelegationEvidence, DelegationLink, execution_key, ExecutionNode


class DeepAgentsAdapter:
    def identify(self, evidence):
        result = DelegationEvidence()
        for span in evidence.spans.values():
            parent = evidence.spans.get(span["parent"])
            if not parent or parent["kind"] != "tool" or span["kind"] != "chain":
                continue
            args = parent.get("input")
            name = span["metadata"].get("lc_agent_name")
            if (not isinstance(args, dict) or not name or span["name"] != name
                    or args.get("subagent_type") != name or not parent.get("tool_call_id")
                    or not compatible(parent, span)):
                continue
            key = execution_key(evidence, span.get("invocation_id"), "framework", span["native_id"], source_file=span["source_file"])
            result.nodes.append(ExecutionNode(key, name, boundary_id=span["id"],
                                               input=span["input"], evidence=span["evidence"], status=span["status"]))
            result.links.append(DelegationLink(None, key.id, parent["row_id"], parent["evidence"] + span["evidence"]))
        return result
