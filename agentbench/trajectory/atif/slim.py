"""Reduce the validated ATIF derivation to the document stored beside the run.

The converter builds and validates a complete document that embeds every
record it used. The attempt directory already keeps those records, so the
stored document carries the official ATIF fields unchanged and, under
``extra.abb``, only small annotations and pointers into the recorded evidence.

A pointer is ``{"file": <path relative to the attempt directory>, "line":
<1-based line, or null for a whole JSON file>}``, the same relative-path
convention Harbor uses for media files beside a trajectory. Paths are the
artifact names the reader used; ``artifact_paths.artifact_file`` resolves them,
including the legacy layouts it supports.

Each position of the document has one table below. A rule receives the stored
key, its value and the shared context, and returns the entries to store in its
place (an empty dict drops it). Every ``extra.abb`` key must have an entry: an
unlisted key fails the export, so storing new data is a deliberate decision.
"""
from copy import deepcopy


def pointers(refs):
    """Recorded evidence references as pointers, without repeats."""
    seen, result = set(), []
    for ref in refs or []:
        pointer = (ref["file"], ref.get("line"))
        if pointer not in seen:
            seen.add(pointer)
            result.append({"file": pointer[0], "line": pointer[1]})
    return result


def keep(key, value, context):
    return {key: value}


def drop(key, value, context):
    return {}


def as_pointers(key, value, context):
    return {key: pointers(value)}


def _present(**values):
    return {key: value for key, value in values.items() if value is not None}


def execution(key, value, context):
    # The key identifies the execution and leads back to its run; the name and
    # parent are already the trajectory's agent name and nesting.
    return {key: {"key": value["key"], "status": value["status"]}}


def provenance(key, value, context):
    return {key: {"builder_version": value["builder_version"], "harbor": value["harbor"]}}


def issues(key, value, context):
    stored = []
    for issue in value:
        ids = issue.get("record_ids") or []
        found = [pointer for rid in ids for pointer in context["records"].get(rid, [])]
        unresolved = [rid for rid in ids if rid not in context["records"]]
        stored.append({"code": issue["code"], "message": issue["message"],
                       **({"evidence": pointers(found)} if found else {}),
                       **({"subjects": unresolved} if unresolved else {})})
    return {key: stored}


def unassigned_records(key, value, context):
    return {key: [{**_present(kind=record.get("kind"), source=record.get("source"),
                              tool_name=record.get("tool_name"), tool_call_id=record.get("tool_call_id"),
                              timestamp=record.get("timestamp")),
                   "evidence": context["records"][record["id"]]} for record in value]}


def delegation_facts(key, value, context):
    return {key: [{**fact, "evidence": pointers(fact.get("evidence"))} for fact in value]}


def model_record(key, value, context):
    return {"evidence": context["records"][value["id"]]}


def tool_execution(key, value, context):
    return {"evidence": context["records"][value["id"]],
            **_present(execution_status=value.get("execution_status"),
                       started_at=value.get("started_at") or value.get("timestamp"),
                       ended_at=value.get("ended_at"))}


def invocation(key, value, context):
    from agentbench.observe.input_artifacts import request_paths
    folder = value["folder"]
    record = value.get("record") or {}
    # The same order the reader follows: the Input record, else the request
    # it was recovered from.
    candidates = [f"{folder}/input.json", *request_paths(folder)]
    found = next((name for name in candidates if context["exists"](name)), candidates[0])
    return {**_present(input_id=record.get("input_id")), "evidence": [{"file": found, "line": None}]}


def execution_start(key, value, context):
    return {"execution_started_at": value.get("start_time")}


# Root and embedded child trajectories.
DOCUMENT = {
    "execution": execution,
    "source": keep,                   # the step source that read the records
    "version_missing_reason": keep,
    "provenance": provenance,
    "issues": issues,
    "unassigned_records": unassigned_records,
    "delegation_facts": delegation_facts,
    "raw_records": drop,              # the attempt directory holds every record
    "invocations": drop,              # steps/NNNN/{input,request,result}.json
    "native_events": drop,            # steps/NNNN/acp-events.jsonl
    "unassigned_agent_spans": drop,   # otel/spans.jsonl
    "auxiliary_artifacts": drop,      # otel/status.json and similar files
}

STEP = {
    "record_ids": drop,               # replaced by the evidence pointers
    "model_record": model_record,
    "invocation": invocation,
    "execution_start": execution_start,
    "evidence": as_pointers,
    "kind": keep,
    "association": keep,
    "turn_evidence": keep,
    "result_source": keep,
}

OBSERVATION_RESULT = {
    "record_ids": drop,
    "tool_execution": tool_execution,
}

METRICS = {
    "recorded_usage": drop,           # the official metrics carry the counts
}

FINAL_METRICS = {
    "metrics_scope": keep,
    "unknown_model_usage": keep,
}


def _trajectories(document):
    yield document
    for child in document.get("subagent_trajectories") or []:
        yield from _trajectories(child)


def _positions(document):
    """Every object that may carry ``extra``, with the table that governs it."""
    for trajectory in _trajectories(document):
        yield "trajectory", trajectory, DOCUMENT
        yield "agent", trajectory.get("agent") or {}, {}
        yield "final_metrics", trajectory.get("final_metrics") or {}, FINAL_METRICS
        for step in trajectory.get("steps") or []:
            yield "step", step, STEP
            yield "metrics", step.get("metrics") or {}, METRICS
            for call in step.get("tool_calls") or []:
                yield "tool_call", call, {}
            for result in (step.get("observation") or {}).get("results") or []:
                yield "observation_result", result, OBSERVATION_RESULT
                for ref in result.get("subagent_trajectory_ref") or []:
                    yield "subagent_trajectory_ref", ref, {}


def _records(document):
    """Evidence pointers of every converted record, by record id."""
    found = {}
    for trajectory in _trajectories(document):
        abb = (trajectory.get("extra") or {}).get("abb") or {}
        for record in abb.get("unassigned_records") or []:
            found[record["id"]] = record
        for step in trajectory.get("steps") or []:
            step_abb = (step.get("extra") or {}).get("abb") or {}
            if "model_record" in step_abb:
                found[step_abb["model_record"]["id"]] = step_abb["model_record"]
            for result in (step.get("observation") or {}).get("results") or []:
                tool = ((result.get("extra") or {}).get("abb") or {}).get("tool_execution")
                if tool is not None:
                    found[tool["id"]] = tool
    return {rid: pointers(record.get("evidence")) for rid, record in found.items()}


def _resolver(directory):
    from agentbench.observe.artifact_paths import artifact_file

    def resolve(relative):
        try:
            return artifact_file(directory, relative)
        except (FileNotFoundError, ValueError):
            return None
    return resolve


def slim(document, directory=None):
    """Return the stored form of a complete ATIF document (a JSON dict).

    ``directory`` is the attempt the document was built from; it only decides
    which recorded file an Input pointer names.
    """
    document = deepcopy(document)
    resolve = _resolver(directory) if directory is not None else None
    context = {"records": _records(document),
               "exists": (lambda name: resolve(name) is not None) if resolve else (lambda name: False)}
    for position, target, table in _positions(document):
        extra = target.get("extra")
        if extra is None:
            continue
        unknown = sorted(set(extra) - {"abb"})
        if unknown:
            raise ValueError(f"{position}.extra has keys outside the ABB namespace: {unknown}")
        stored = {}
        for key, value in extra["abb"].items():
            if key not in table:
                raise ValueError(f"{position}.extra.abb.{key} has no storage rule in slim.py")
            for name, entry in table[key](key, value, context).items():
                if name in stored:
                    raise ValueError(f"{position}.extra.abb.{name} is produced by two storage rules")
                stored[name] = entry
        if stored:
            target["extra"] = {"abb": stored}
        else:
            del target["extra"]
    return document


def _all_pointers(node):
    if isinstance(node, dict):
        if set(node) == {"file", "line"} and isinstance(node["file"], str):
            yield node
            return
        for value in node.values():
            yield from _all_pointers(value)
    elif isinstance(node, list):
        for value in node:
            yield from _all_pointers(value)


def check_pointers(document, directory):
    """Every pointer must open a file inside the attempt directory and, for a
    line, a line that file has."""
    resolve = _resolver(directory)
    lines = {}
    for position, target, _ in _positions(document):
        for pointer in _all_pointers(target.get("extra")):
            path = resolve(pointer["file"])
            if path is None or not path.is_file():
                raise ValueError(f"{position} points to a missing evidence file: {pointer['file']}")
            if pointer["line"] is None:
                continue
            if path not in lines:
                with path.open("rb") as stream:
                    lines[path] = sum(1 for _ in stream)
            if not 1 <= pointer["line"] <= lines[path]:
                raise ValueError(f"{position} points past the end of {pointer['file']}: line {pointer['line']}")


def stored_document(document, directory):
    """The validated stored form of a complete document built from ``directory``."""
    from harbor.models.trajectories import Trajectory
    stored = slim(document.to_json_dict() if hasattr(document, "to_json_dict") else document, directory)
    check_pointers(stored, directory)
    Trajectory.model_validate(stored)
    return stored
