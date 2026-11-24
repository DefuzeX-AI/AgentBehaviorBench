"""Assemble official Harbor models from resolved ABB evidence."""
from dataclasses import asdict
import json

from harbor.models.trajectories import (Agent, Step, Trajectory, ToolCall,
    Observation, ObservationResult, SubagentTrajectoryRef, Metrics, FinalMetrics)
from . import SCHEMA_VERSION
from .contracts import EvidenceIssue
from .otel_times import SpanTimes


def text(value):
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _metrics(output):
    usage = output.get("usage")
    if not isinstance(usage, dict):
        return None
    values = {}
    for target, sources in {"prompt_tokens": ("prompt_tokens", "input_tokens"),
                            "completion_tokens": ("completion_tokens", "output_tokens")}.items():
        for source in sources:
            if type(usage.get(source)) is int and usage[source] >= 0:
                values[target] = usage[source]
                break
    details = usage.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    if type(cached) is int and cached >= 0:
        values["cached_tokens"] = cached
    cost = usage.get("cost")
    if type(cost) in (int, float) and cost >= 0:
        values["cost_usd"] = cost
    return Metrics(**values, extra={"abb": {"recorded_usage": usage}}) if values else None


def assemble_atif(bundle, graph, provenance):
    pending = {nid: [] for nid in graph.nodes}
    tools = {t["id"]: t for t in bundle.tools}
    attached, issues = set(), graph.issues
    clocks = SpanTimes(bundle, issues)

    def operation_time(record):
        native = [r for r in record.get("agent_otel", []) if r.get("start_time") and r.get("unix_nano")]
        if len(native) == 1:
            return {**native[0], "unix_nano": int(native[0]["unix_nano"])}
        span = bundle.spans.get(record.get("span")) or {}
        native = span.get("native_id")
        return clocks.start(record, native) if native else None

    def unassigned(record):
        timing = operation_time(record)
        return {**record, "timestamp": timing["start_time"] if timing else None, "ended_at": None}

    def order(record, timing):
        # Without a clock the original source line still preserves local order.
        first = min((ref["file"], ref["line"]) for ref in record["evidence"])
        return (0, timing["unix_nano"], first) if timing else (1, 0, first)

    revision = provenance.get("agent_revision") or "unknown"
    if revision == "unknown":
        issues.append(EvidenceIssue("missing_agent_revision", "No frozen revision in historical evidence"))
    delegation_by_tool = {}
    for link in graph.delegations:
        delegation_by_tool.setdefault(link.tool_id, []).append(link)

    def observed(tool, call_id=None):
        return ObservationResult(source_call_id=call_id, content=text(tool.get("outputs")),
            extra={"abb": {"record_ids": [tool["id"]], "tool_execution": tool}},
            subagent_trajectory_ref=[SubagentTrajectoryRef(trajectory_id=link.child_id)
                for link in delegation_by_tool.get(tool["id"], [])] or None)

    for model in bundle.models:
        owner = graph.owners[model["id"]]
        if owner is None:
            continue
        output = model.get("client_output") or model["output"]
        call_output = model.get("client_output") or model.get("framework_output") or output
        calls, observations = [], []
        for call in call_output.get("tool_calls") or output.get("tool_calls") or []:
            if not call.get("id") or not call.get("name") or not isinstance(call.get("arguments"), dict):
                issues.append(EvidenceIssue("incomplete_tool_call", "Tool call cannot be represented as complete ATIF arguments", [model["id"]]))
                continue
            calls.append(ToolCall(tool_call_id=call["id"], function_name=call["name"], arguments=call["arguments"]))
            for relation in graph.tool_relations[model["id"]]:
                if relation["tool_call_id"] == call["id"] and relation["status"] == "exact":
                    for tid in relation["interaction_ids"]:
                        if graph.owners[tid] == owner and tid not in attached:
                            observations.append(observed(tools[tid], call["id"]))
                            attached.add(tid)
        reasoning = output.get("reasoning")
        timing = operation_time(model)
        step = Step(step_id=1, source="agent", timestamp=timing["start_time"] if timing else None,
            message=text(output.get("text")), reasoning_content=reasoning if isinstance(reasoning, str) else None,
            model_name=model["output"].get("model") or model["input"].get("model"),
            tool_calls=calls or None, observation=Observation(results=observations) if observations else None,
            metrics=_metrics(model["output"]), llm_call_count=1,
            extra={"abb": {"record_ids": [model["id"]], "model_record": model}})
        pending[owner].append((order(model, timing), model["id"], step))
    for tool in bundle.tools:
        owner = graph.owners[tool["id"]]
        if owner is None or tool["id"] in attached:
            continue
        timing = operation_time(tool)
        pending[owner].append((order(tool, timing), tool["id"],
            Step(step_id=1, source="agent", timestamp=timing["start_time"] if timing else None, message="",
                 observation=Observation(results=[observed(tool)]),
                 extra={"abb": {"kind": "independent_tool", "association": "unlinked"}})))

    from .replies import root_steps
    root_rows = root_steps(bundle, pending[graph.root_id], issues, clocks)
    pending[graph.root_id] = [((0, i, ()), "", step) for i, step in enumerate(root_rows)]
    for nid, node in graph.nodes.items():
        if nid != graph.root_id and node.input is not None:
            pending[nid].append(((-1,), "!input", Step(step_id=1, source="user", message=text(node.input),
                extra={"abb": {"kind": "child_input", "evidence": node.evidence}})))
        owned_models = sorted((m for m in bundle.models if graph.owners[m["id"]] == nid),
                              key=lambda m: order(m, operation_time(m)))
        if owned_models:
            first = owned_models[0]["input"]
            systems = [m.get("content") for m in first.get("messages") or []
                       if isinstance(m, dict) and m.get("role") in ("system", "developer")]
            if first.get("system") is not None:
                systems.insert(0, first["system"])
            if first.get("instructions") is not None:
                systems.insert(0, first["instructions"])
            for i, message in enumerate(systems):
                pending[nid].append(((-2,), str(i), Step(step_id=1, source="system", message=text(message))))

    # Children without any real step remain a gap, never a dangling reference.
    valid_nodes = {nid for nid, steps in pending.items() if steps}
    for nid in graph.nodes:
        if nid not in valid_nodes:
            issues.append(EvidenceIssue("empty_execution", "Execution has no representable recorded steps", [nid]))
    for rows in pending.values():
        for _, _, step in rows:
            if step.observation:
                for result in step.observation.results:
                    result.subagent_trajectory_ref = [r for r in result.subagent_trajectory_ref or []
                                                      if r.trajectory_id in valid_nodes] or None
    if graph.root_id not in valid_nodes:
        raise ValueError("No observed steps for a valid root ATIF trajectory")

    def build(nid, ancestors):
        if nid in ancestors:
            raise ValueError("Cyclic execution graph")
        node = graph.nodes[nid]
        steps = [s for _, _, s in sorted(pending[nid], key=lambda x: (x[0], x[1]))]
        for i, step in enumerate(steps, 1):
            step.step_id = i
        children = [build(cid, {*ancestors, nid}) for cid, child in sorted(graph.nodes.items())
                    if child.parent_id == nid and cid in valid_nodes]
        extra = {"execution": asdict(node)}
        if nid != graph.root_id:
            extra["version_missing_reason"] = "No independent child Agent revision was recorded"
        if nid == graph.root_id:
            extra.update(source=bundle.source, provenance=provenance, invocations=bundle.inputs,
                unassigned_records=[unassigned(r) for r in bundle.models + bundle.tools if graph.owners[r["id"]] is None],
                native_events=bundle.native_events, issues=[asdict(i) for i in issues])
            if bundle.unassigned_agent_spans:
                extra["unassigned_agent_spans"] = bundle.unassigned_agent_spans
            extra["raw_records"] = bundle.raw_records
            extra["auxiliary_artifacts"] = bundle.auxiliary_artifacts
            extra["delegation_facts"] = graph.delegation_facts
        doc = Trajectory(schema_version=SCHEMA_VERSION, trajectory_id=nid, session_id=bundle.run["run_id"],
            agent=Agent(name=node.name, version=revision if nid == graph.root_id else "unknown"),
            steps=steps, subagent_trajectories=children or None, extra={"abb": extra})
        metrics = [step.metrics for step in steps if step.llm_call_count == 1]
        values = {}
        # Partial known sums are not mislabelled as complete totals.
        for field, total in (("prompt_tokens", "total_prompt_tokens"), ("completion_tokens", "total_completion_tokens"),
                             ("cached_tokens", "total_cached_tokens"), ("cost_usd", "total_cost_usd")):
            local = [getattr(m, field) if m else None for m in metrics]
            descendants = [getattr(c.final_metrics, total) if c.final_metrics else None for c in children]
            if local + descendants and all(v is not None for v in local + descendants) and not (
                nid == graph.root_id and any(graph.owners[m["id"]] is None for m in bundle.models)):
                values[total] = sum(local + descendants)
        doc.final_metrics = FinalMetrics(**values, total_steps=len(steps),
            extra={"abb": {"metrics_scope": "execution_and_descendants", "unknown_model_usage": sum(m is None for m in metrics)}})
        return doc

    return build(graph.root_id, set())
