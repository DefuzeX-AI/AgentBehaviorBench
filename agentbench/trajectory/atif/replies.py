"""Project an invocation's recorded outward reply independently of model ownership."""
from pathlib import PurePosixPath
from collections import defaultdict
import json

from harbor.models.trajectories import Step

from agentbench.observe.artifact_paths import SESSION_OUTPUT
from agentbench.observe.tool_links import compatible
from .contracts import EvidenceIssue


def turn_scope(item):
    request = item["request"] or {}
    sources = (request.get("observation_context") or {}, item["context"], item["record"] or {},
               {"invocation_id": request.get("run_id"), "agent_id": request.get("agent_id")})
    scope = {}
    for source in sources:
        for key in ("input_id", "case_id", "attempt_id", "invocation_id", "agent_id"):
            value = source.get(key)
            if value is not None:
                if key in scope and scope[key] != value:
                    scope["identity_conflicts"] = True
                scope[key] = value
        if source.get("identity_conflicts"):
            scope["identity_conflicts"] = True
    return scope


def reply_text(item):
    result = item["result"]
    if not isinstance(result, dict) or result.get("status") != "succeeded":
        return None
    message = result.get("output")
    return message if isinstance(message, str) and message.strip() else None


def result_matches(item):
    result = item["result"]
    scope = turn_scope(item)
    if not compatible(scope, result, scope_keys=("input_id", "case_id", "attempt_id", "invocation_id", "agent_id")):
        return False
    # The worker's result.run_id identifies its invocation, unlike the host attempt ID.
    if result.get("schema") == "abb.result.v1" and result.get("run_id"):
        return all(result["run_id"] == value for value in
                   (scope.get("invocation_id"), result.get("invocation_id")) if value)
    return True


def record_turn(record, inputs, scopes):
    matches = []
    # An exported span lives in the Case-level otel/ file; the ACP messages that
    # reported its tool call id were recorded in the Input's own folder.
    files = {PurePosixPath(ref["file"]).parent.as_posix()
             for ref in [*record.get("evidence", []), *record.get("session_evidence", [])]}
    for index, (item, scope) in enumerate(zip(inputs, scopes)):
        if not compatible(record, scope):
            continue
        if item["folder"] in files or any(record.get(k) and record[k] == scope.get(k)
                                         for k in ("invocation_id", "input_id")):
            matches.append(index)
    return matches[0] if len(matches) == 1 else None


def recorded_acp_replies(bundle):
    """Recover delivered text from the bound ACP session when no final result exists."""
    inputs = bundle.inputs
    scopes = [turn_scope(item) for item in inputs]
    shared = bundle.auxiliary_artifacts.get(SESSION_OUTPUT + "/acp-summary.json") or {}
    groups = defaultdict(list)
    current = {}
    for event in bundle.native_events:
        if event.get("event") != "session_update":
            continue
        ref = event["evidence"][0]
        data = event["data"]
        turn = record_turn({**data, "evidence": [ref]}, inputs, scopes)
        if turn is None or reply_text(inputs[turn]) is not None:
            continue
        folder = PurePosixPath(ref["file"]).parent.as_posix()
        summary = shared if folder == SESSION_OUTPUT else inputs[turn].get("acp_summary") or {}
        session = (summary.get("session") or {}).get("sessionId")
        if not session or data.get("session_id") != session:
            continue
        update = data.get("update") or {}
        kind = update.get("sessionUpdate")
        if kind in ("tool_call", "tool_call_update"):
            current.pop(turn, None)
            continue
        content = update.get("content") or {}
        if kind != "agent_message_chunk" or content.get("type") != "text" or not isinstance(content.get("text"), str):
            continue
        if turn not in current:
            current[turn] = ([], [])
            groups[turn].append(current[turn])
        current[turn][0].append(content["text"])
        current[turn][1].append(ref)
    return groups


def root_steps(bundle, rows, issues, clocks):
    """Order recorded turns, keeping unrelated operations outside any turn."""
    inputs = bundle.inputs
    scopes = [turn_scope(item) for item in inputs]
    records = {r["id"]: r for r in [*bundle.models, *bundle.tools]}
    groups = [[] for _ in inputs]
    other = []
    # The unit declares that its Agent makes no model call outside a prompt, so
    # the sole Input of the attempt owns an inference that names no Input.
    evaluation = (bundle.target.get("runtime") or {}).get("evaluation") or {}
    sole_input = len(inputs) == 1 and evaluation.get("single_input_model_scope") is True
    for when, rid, step in sorted(rows, key=lambda row: row[:2]):
        record = records.get(rid)
        turn = record_turn(record, inputs, scopes) if record else None
        if (turn is None and sole_input and record and bundle.exported_steps and not record.get("span")
                and record.get("source") in ("agent_native", "auto_instrumented") and compatible(record, scopes[0])):
            turn = 0
            step.extra["abb"]["turn_evidence"] = "isolated_single_input_case"
        if turn is None:
            other.append((when, rid, [step]))
        else:
            groups[turn].append((when, rid, step))

    # Numbered benchmark folders encode execution order. UUID folder names do not.
    acp = recorded_acp_replies(bundle) if bundle.reply_steps else {}
    blocks = []
    for index, item in enumerate(inputs):
        group = groups[index]
        for parts, refs in acp.get(index, []):
            if not any(parts):
                continue
            step = Step(step_id=1, source="agent", message="".join(parts),
                        extra={"abb": {"kind": "acp_reply", "evidence": refs}})
            group.append(((1, 0, (refs[0]["file"], refs[0]["line"])), f"{refs[0]['file']}:{refs[0]['line']:020d}", step))
        group.sort(key=lambda row: row[:2])
        request = item["request"] or {}
        timing = clocks.start({**scopes[index], "run_id": request.get("session_id") or bundle.run["run_id"]})
        steps = []
        if item["record"] is not None:
            payload = item["record"].get("payload")
            prompt = payload if isinstance(payload, str) else "" if payload is None else json.dumps(payload, ensure_ascii=False, sort_keys=True)
            steps.append(Step(step_id=1, source="user", message=prompt,
                              extra={"abb": {"invocation": item, **({"execution_start": timing} if timing else {})}}))
        steps.extend(step for _, _, step in group)
        # Without reply steps the source's last model step of the turn is the reply.
        message = reply_text(item) if bundle.reply_steps else None
        if message is not None and not result_matches(item):
            issues.append(EvidenceIssue("result_identity_conflict", "Result identity conflicts with its input", [item["folder"]]))
        elif message is not None:
            source = item["folder"] + "/result.json"
            last_model = next((step for _, _, step in reversed(group) if step.llm_call_count), None)
            if (bundle.source in ("langgraph", "langfuse") and last_model is not None
                    and not last_model.tool_calls and last_model.message == message):
                last_model.extra["abb"]["result_source"] = source
            else:
                steps.append(Step(step_id=1, source="agent", message=message,
                                  extra={"abb": {"kind": "invocation_result", "result_source": source}}))
        if steps:
            blocks.append((timing, item["folder"], steps))
    numbered = all(PurePosixPath(folder).name.isdecimal() for _, folder, _ in blocks)
    if numbered:
        blocks.sort(key=lambda block: int(PurePosixPath(block[1]).name))
    timed = [block for block in blocks if block[0]]
    if len(blocks) > 1 and not numbered and (len(timed) != len(blocks) or
            len({block[0]["unix_nano"] for block in timed}) != len(timed)):
        issues.append(EvidenceIssue("turn_order_uncertain", "OTel boundaries cannot establish the full turn order",
                                    [folder for _, folder, _ in blocks]))
    # Undated blocks keep their stable slots. Only OTel orders the dated turns.
    ordered = iter(sorted(timed, key=lambda b: b[0]["unix_nano"]))
    blocks = [next(ordered) if block[0] else block for block in blocks]
    # Preserve turn boundaries even when other confirmed operations lack a turn.
    remaining = iter(other)
    outside = next(remaining, None)
    steps = []
    for timing, _, group in blocks:
        while outside and timing and outside[0][:2] <= (0, timing["unix_nano"]):
            steps.extend(outside[2])
            outside = next(remaining, None)
        steps.extend(group)
    if outside:
        steps.extend(outside[2])
    for _, _, group in remaining:
        steps.extend(group)
    return steps
