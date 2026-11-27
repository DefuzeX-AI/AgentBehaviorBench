"""Project Langfuse SDK observations from the local OTLP export into ATIF."""
import json

from agentbench.trajectory.content import framework_input, framework_output
from ..contracts import EvidenceIssue, stable_id
from .base import Recorded, _exported, references


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def generation_usage(details):
    if not isinstance(details, dict):
        return None
    # The callback may retain OpenAI totals or split them into exclusive
    # Langfuse buckets. Priority-tier counts overlap with the regular buckets.
    usage = dict(details)
    for side, target in (("input", "prompt_tokens"), ("output", "completion_tokens")):
        if target not in usage and type(details.get(side)) is int:
            usage[target] = details[side] + sum(
                value for key, value in details.items() if type(value) is int and (
                    key.startswith(side + "_") and not key.startswith(side + "_priority")
                    or side == "input" and key.startswith("cached_modality_")))
    cached = details.get("input_cache_read", details.get("input_cached_tokens"))
    if type(cached) is int:
        usage.setdefault("prompt_tokens_details", {"cached_tokens": cached})
    return usage


class LangfuseSource:
    name = "langfuse"
    reply_steps = True
    exported_steps = False
    reads_network = False

    def recorded(self, index, *, include_network, issues):
        self.spans = {}
        return Recorded([], [], self.spans, [])

    def adopt(self, item, issues):
        attrs = item["attributes"]
        if item["scope"].get("name") != "langfuse-sdk":
            return None
        prefix = "langfuse.observation."
        kind = attrs.get(prefix + "type")
        inputs = decode(attrs.get(prefix + "input"))
        output = decode(attrs.get(prefix + "output"))
        metadata_prefix = prefix + "metadata."
        metadata = {key[len(metadata_prefix):]: decode(value) for key, value in attrs.items()
                    if key.startswith(metadata_prefix)}
        trace_id, span_id = item["trace_id"], item["span_id"]
        sid = stable_id("agent_otel", trace_id, span_id)
        parent = item["parent_span_id"]
        failed = (item.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")
                  or attrs.get(prefix + "level") == "ERROR")
        status = "error" if failed else "complete" if item.get("end_time") else "incomplete"
        record = _exported(item, kind)
        record.update(span=sid, status=status)
        for key in ("input_id", "invocation_id", "case_id"):
            if metadata.get("abb_" + key):
                record[key] = metadata["abb_" + key]
        tool_id = output.get("tool_call_id") if isinstance(output, dict) else None
        self.spans[sid] = {**record, "id": sid, "row_id": sid, "native_id": span_id,
                           "source_file": item["ref"]["file"], "metadata": metadata,
                           "parent": stable_id("agent_otel", trace_id, parent) if parent else None,
                           "kind": {"tool": "tool", "generation": "llm"}.get(kind, "chain"),
                           "name": item["name"], "tool_call_id": tool_id, "input": inputs,
                           "evidence": references([item["ref"]])}
        if kind == "tool":
            record.update(kind="tool", tool_call_id=tool_id, tool_name=item["name"],
                          input_arguments=inputs, outputs=output.get("content", output) if isinstance(output, dict) else output,
                          started_at=item.get("start_time"),
                          execution_status={"complete": "succeeded", "error": "error", "incomplete": "not_observed"}[status])
        elif kind == "generation":
            if isinstance(output, str):
                output = {"content": output}
            if not isinstance(output, dict) or not ("content" in output or "tool_calls" in output):
                issues.append(EvidenceIssue("missing_generation_output", "Generation span lacks a recorded reply", [sid]))
                return None
            value = framework_output({"generations": [[{"message": output}]]})
            value["usage"] = generation_usage(decode(attrs.get(prefix + "usage_details")))
            value["model"] = attrs.get(prefix + "model.name")
            record.update(kind="model", input=framework_input(inputs), output=value, call_id=None,
                          client_output=None, framework_output=None, raw_request={}, raw_response={}, stream=None,
                          error=attrs.get(prefix + "status_message"))
            if status != "complete":
                issues.append(EvidenceIssue("unfinished_or_failed_model", status, [sid]))
        else:
            return None
        return record

    def complete(self, models, tools, native, issues, other_spans):
        if not models:
            issues.append(EvidenceIssue("missing_langfuse_generation", "No Langfuse generation with a recorded reply"))
