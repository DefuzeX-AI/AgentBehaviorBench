"""Read existing ABB evidence, retaining chain nodes and original payloads.

Which records become model and tool steps is the step source's decision
(``sources/``); this module reads what every source shares.
"""
from copy import deepcopy
from pathlib import Path
import json

from agentbench.observe.artifact_paths import SESSION_OUTPUT, canonical_relative
from agentbench.observe.interactions import InteractionIndex, _files
from agentbench.observe.input_artifacts import read_input_artifacts
from agentbench.observe.tool_links import compatible
from agentbench.observe.view_api import RunViewAPI
from agentbench.trajectory.agent_otel import content, correlate, operations
from .contracts import EvidenceBundle, EvidenceIssue, stable_id
from .provenance import snapshot, ensure_unchanged
from .sources import declared, select
from .sources.base import _scope, references


def read_evidence(directory, *, allow_incomplete=False, include_network=True, run=None, source=None):
    root = Path(directory).resolve(strict=True)
    api = RunViewAPI(root)
    before = snapshot(root)
    # The run flow derives ATIF before run.json receives its final status, so
    # it supplies that status in memory.
    run = dict(run) if run is not None else api.read("run.json") or {}
    terminal = {"succeeded", "failed", "cancelled", "interrupted", "stopped", "completed", "degraded"}
    if run.get("status") not in terminal and not allow_incomplete:
        raise ValueError("Run is not known to be finished; use --allow-incomplete")
    target = api.read("request/target.json") or {}
    artifacts = [(folder, *read_input_artifacts(folder, api.read)) for folder in api.outputs()]
    if source is None:
        source = declared(target, [{"request": request} for _, _, request in artifacts])
        capture = api.read("otel/status.json") or {}
        frozen = (target.get("runtime") or {}).get("atif") or {}
        if not frozen.get("source") and source == "langgraph" and capture.get("profile") == "langfuse-auto":
            source = "langfuse"
    source = select(source)

    def wire(name):
        return canonical_relative(name) == canonical_relative("network.jsonl")

    # Exclude the interceptor at the input boundary, before any wire/callback
    # join. A framework span then contributes its own payload even on retries.
    # A source that merges the wire record reads it apart from that join.
    def selected(name):
        return include_network or source.reads_network or not wire(name)

    def indexed(keep):
        found = InteractionIndex(root, [file for file in _files(root) if keep(file[0])])
        for records in found.groups.values():
            for record in records:
                record["file"] = api.file(record["file"]).relative_to(root).as_posix()
        return found

    index = indexed(lambda name: not wire(name) or include_network and not source.reads_network)
    issues = [EvidenceIssue("invalid_record", text) for text in index.warnings]
    if run.get("status") not in terminal:
        issues.append(EvidenceIssue("incomplete_run", "Snapshot of an unfinished or unknown run"))
    elif run.get("status") not in {"succeeded", "completed"}:
        issues.append(EvidenceIssue("run_not_succeeded", "Recorded run status: " + str(run.get("status"))))
    if not run.get("run_id"):
        run = {**run, "run_id": stable_id("anonymous-evidence", before)}
        issues.append(EvidenceIssue("missing_run_id", "Export identity derived from evidence digests"))
    raw_records = {}
    for row in index.rows:
        for record in index.groups[row["id"]]:
            raw_records[(record["file"], record["line"])] = deepcopy(record)
    inputs = []
    for folder, record, request in artifacts:
        inputs.append({"folder": folder, "record": record, "request": request,
                       "result": api.read(f"{folder}/result.json"),
                       "acp_summary": api.read(f"{folder}/acp-summary.json"),
                       "context": {k: v for k, v in index.contexts.get(folder, {}).items()
                                   if k in _scope({})}})
    models, tools, spans, native = source.recorded(index, include_network=include_network, issues=issues)
    if source.reads_network:
        # Unparsed lines are reported below with the other raw records.
        source.read_network(indexed(wire))
    for folder in api.evidence_outputs():
        try:
            path = api.file(f"{folder}/acp-events.jsonl")
        except FileNotFoundError:
            path = None
        if path is not None and path.is_file():
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                try:
                    row = json.loads(line)
                    raw_records[(path.relative_to(root).as_posix(), n)] = {"file": path.relative_to(root).as_posix(), "line": n, "raw": row}
                    native.append({"data": row.get("data", {}), "event": row.get("event"), "timestamp": row.get("timestamp"),
                                   "evidence": references([{"file": path.relative_to(root).as_posix(), "line": n, "raw": row}])})
                except (ValueError, AttributeError):
                    issues.append(EvidenceIssue("invalid_acp_event", f"{folder}/acp-events.jsonl:{n}"))
    bind_sessions(tools, native)
    auxiliary = {}
    shared_summary = SESSION_OUTPUT + "/acp-summary.json"
    if shared_summary in before:
        auxiliary[shared_summary] = api.read(shared_summary)
    # Preserve OTel envelopes/payloads and recorded runtime/configuration facts.
    # They are evidence-only until a validated adapter can interpret them.
    for name in before:
        if not selected(name):
            continue
        if name.startswith("otel/") or name.endswith(".jsonl") or "/otel" in name or name.endswith("execution-environment.json") or name.startswith("request/native-config-") or name == "request/experiment.json":
            value = api.file(name).read_text(encoding="utf-8")
            if name.endswith(".jsonl"):
                for n, line in enumerate(value.splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                    except ValueError:
                        raw = {"unparsed_line": line}
                        issues.append(EvidenceIssue("invalid_raw_record", f"{name}:{n}"))
                    raw_records[(name, n)] = {"file": name, "line": n, "raw": raw}
            else:
                auxiliary[name] = json.loads(value) if name.endswith(".json") else value
    agent_spans, adopted = [], []
    for item, record in correlate(models + tools, operations(raw_records.values())):
        ref = references([item["ref"]])[0]
        if record is None:
            record = source.adopt(item, issues)
            if record is None:
                agent_spans.append({**ref, "trace_id": item["trace_id"], "span_id": item["span_id"],
                    "parent_span_id": item["parent_span_id"], "origin": item["origin"], "operation": item["kind"],
                    "name": item["name"], **content(item)})
                continue
            (tools if record["kind"] == "tool" else models).append(record)
            adopted.append(record)
        record["evidence"].append(ref)
        record.setdefault("agent_otel", []).append({**ref, "trace_id": item["trace_id"],
            "span_id": item["span_id"], "parent_span_id": item["parent_span_id"], "origin": item["origin"], "start_time": item.get("start_time"),
            "unix_nano": item.get("start_time_unix_nano")})
    bind_sessions([record for record in adopted if record["kind"] == "tool"], native)
    source.complete(models, tools, native, issues, agent_spans)
    bundle = EvidenceBundle(root, run, before, inputs, models, tools, spans, native, issues,
                            target, list(raw_records.values()), auxiliary)
    bundle.unassigned_agent_spans = agent_spans
    bundle.source, bundle.reply_steps, bundle.exported_steps = source.name, source.reply_steps, source.exported_steps
    ensure_unchanged(bundle)
    return bundle


def bind_sessions(tools, native):
    """Give a tool the ACP session that reported its call.

    A tool record carries no session of its own. The Agent's ACP messages name
    the session beside the same tool call id; only a unique session in a
    compatible invocation is taken, with those messages as evidence.
    """
    for tool in tools:
        matches = []
        for event in native:
            data = event["data"]
            update = data.get("update") or {}
            if (isinstance(update, dict) and tool.get("tool_call_id")
                    and update.get("toolCallId") == tool["tool_call_id"]
                    and data.get("session_id") and compatible(tool, data)):
                matches.append(event)
        sessions = {event["data"]["session_id"] for event in matches}
        if len(sessions) == 1:
            session, = sessions
            if tool.get("native_session_id") not in (None, session):
                tool["identity_conflicts"] = [*(tool.get("identity_conflicts") or []), "native_session_id"]
            else:
                tool["native_session_id"] = session
                tool["session_evidence"] = [ref for event in matches for ref in event.get("evidence", [])]
        elif len(sessions) > 1:
            tool["identity_conflicts"] = [*(tool.get("identity_conflicts") or []), "native_session_id"]
