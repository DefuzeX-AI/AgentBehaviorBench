"""Official schema checks plus evidence conservation and reference integrity."""
from collections import Counter
from dataclasses import asdict
from harbor.models.trajectories import Trajectory


def walk(document):
    yield document
    for child in document.subagent_trajectories or []:
        yield from walk(child)


def validate_export(bundle, graph, document, *, evidence_resolver=None):
    if evidence_resolver is not None:
        from .bundle import restore_document
        document = Trajectory.model_validate(restore_document(document.to_json_dict(), evidence_resolver))
    Trajectory.model_validate(document.to_json_dict())
    counts, locations = Counter(), {}
    for doc in walk(document):
        children = {c.trajectory_id for c in doc.subagent_trajectories or []}
        for step in doc.steps:
            for rid in (step.extra or {}).get("abb", {}).get("record_ids", []):
                counts[rid] += 1
                locations[rid] = doc.trajectory_id
            for result in step.observation.results if step.observation else []:
                for rid in (result.extra or {}).get("abb", {}).get("record_ids", []):
                    counts[rid] += 1
                    locations[rid] = doc.trajectory_id
                for ref in result.subagent_trajectory_ref or []:
                    if ref.trajectory_id not in children:
                        raise ValueError("Child reference does not resolve in its parent")
    for record in document.extra["abb"]["unassigned_records"]:
        counts[record["id"]] += 1
        locations[record["id"]] = None
    expected = Counter(r["id"] for r in bundle.models + bundle.tools)
    if counts != expected:
        raise ValueError("Observed records were lost or counted more than once")
    if locations != graph.owners:
        raise ValueError("Export ownership differs from resolved evidence")
    # Existing bundles were built before invocation results were projected.
    if document.extra["abb"].get("provenance", {}).get("builder_version", 0) >= 3:
        validate_replies(bundle, document)
    recorded = document.extra["abb"]["raw_records"]
    if evidence_resolver is None:
        raw_equal = recorded == bundle.raw_records
    else:
        # Recreated files have new mtimes. They may change the reader's list
        # ordering, never the recorded position or the timestamp inside an event.
        from .evidence_store import json_bytes
        by_position = lambda rows: {(r["file"], r["line"]): json_bytes(r) for r in rows}
        raw_equal = len(recorded) == len(bundle.raw_records) and by_position(recorded) == by_position(bundle.raw_records)
    if not raw_equal:
        raise ValueError("Raw evidence was altered or lost")
    if document.extra["abb"]["auxiliary_artifacts"] != bundle.auxiliary_artifacts:
        raise ValueError("Auxiliary evidence was altered or lost")
    raw_keys = {(r["file"], r["line"]) for r in bundle.raw_records}
    if len(raw_keys) != len(bundle.raw_records):
        raise ValueError("Raw evidence contains duplicate source positions")
    return evidence_report(bundle, graph, document)


def evidence_report(bundle, graph, document):
    raw_keys = {(r["file"], r["line"]) for r in bundle.raw_records}
    candidates = {}
    for record in bundle.models + bundle.tools:
        for ref in record["evidence"]:
            candidates.setdefault((ref["file"], ref["line"]), set()).add(graph.owners[record["id"]])
    for sid, span in bundle.spans.items():
        for ref in span["evidence"]:
            candidates.setdefault((ref["file"], ref["line"]), set()).add(graph.span_owners[sid])
    raw_owners = {}
    for file, line in sorted(raw_keys):
        choices = candidates.get((file, line), set())
        raw_owners[f"{file}:{line}"] = next(iter(choices)) if len(choices) == 1 else None
    raw_assigned = sum(owner is not None for owner in raw_owners.values())
    relation_report = {"executions": [asdict(n) for n in graph.nodes.values()],
        "delegations": [asdict(d) for d in graph.delegations], "owners": graph.owners,
        "tool_relations": graph.tool_relations, "delegation_facts": graph.delegation_facts,
        "raw_record_owners": raw_owners,
        "issues": [asdict(i) for i in graph.issues]}
    missing = sum(owner is None for owner in graph.owners.values())
    report = {"official_schema_valid": True, "evidence_conserved": True,
        "status": "partial" if graph.issues else "complete", "observed_models": len(bundle.models),
        "observed_tools": len(bundle.tools), "assigned_records": len(graph.owners) - missing,
        "unassigned_records": missing, "embedded_children": sum(1 for _ in walk(document)) - 1,
        "raw_records_preserved": len(raw_keys),
        "raw_assigned_records": raw_assigned, "raw_unassigned_records": len(raw_keys) - raw_assigned,
        "coverage_scope": "Recorded model/tool operations; auxiliary records are preserved without inventing execution identity",
        "issues": [asdict(i) for i in graph.issues]}
    return relation_report, report


def content_checks(bundle, document):
    """Independent source-payload checks, also covering unassigned evidence."""
    from agentbench.trajectory.atif.validation import walk
    models, tools = [], []
    for doc in walk(document):
        for step in doc.steps:
            abb = (step.extra or {}).get("abb", {})
            if "model_record" in abb:
                models.append(abb["model_record"])
            for observation in step.observation.results if step.observation else []:
                tools.append(observation.extra["abb"]["tool_execution"])
    for record in document.extra["abb"]["unassigned_records"]:
        (models if record["kind"] == "model" else tools).append(record)
    checks = []
    for source in bundle.tools:
        found = [t for t in tools if t["id"] == source["id"]]
        checks.append({"kind": "tool_once", "id": source["id"], "passed": len(found) == 1})
        for kind, field in (("tool_input", "input_arguments"), ("tool_output", "outputs")):
            checks.append({"kind": kind, "id": source["id"], "passed": len(found) == 1 and found[0][field] == source[field]})
    for source in bundle.models:
        found = [m for m in models if m["id"] == source["id"]]
        for kind, field in (("model_input", "raw_request"), ("model_output", "raw_response")):
            checks.append({"kind": kind, "id": source["id"], "passed": len(found) == 1 and found[0][field] == source[field]})
    checks.append({"kind": "model_request_coverage", "passed": sorted(m["id"] for m in models) == sorted(m["id"] for m in bundle.models)})
    return checks


def validate_replies(bundle, document):
    from .replies import reply_text, result_matches

    if not bundle.reply_steps:
        return
    expected = {item["folder"] + "/result.json": reply_text(item) for item in bundle.inputs
                if reply_text(item) is not None and result_matches(item)}
    seen = set()
    for trajectory in walk(document):
        for step in trajectory.steps:
            abb = (step.extra or {}).get("abb", {})
            source = abb.get("result_source")
            if source is None:
                continue
            if (trajectory is not document or source not in expected or source in seen
                    or step.source != "agent" or step.message != expected[source]):
                raise ValueError("Invocation reply differs from its recorded result")
            if abb.get("kind") == "invocation_result" and (
                    step.llm_call_count is not None or step.metrics or abb.get("record_ids")):
                raise ValueError("Delivery step cannot claim a model operation")
            seen.add(source)
    if seen != expected.keys():
        raise ValueError("Missing recorded invocation reply")
