"""Small native ABB records; no local services, paths, images or credentials."""
import json
from pathlib import Path
import pytest

pytest.importorskip("harbor.models.trajectories")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def event(event_name, **data):
    return {"event": event_name, "timestamp": "2026-01-01T00:00:00+00:00", "data": data}


def span(sid, parent=None, kind="chain", name="graph", **kw):
    return event("span_start", span_id=sid, parent_span_id=parent, kind=kind, name=name, **kw)


def response(content="你好 ¡España!", calls=None):
    return {"model": "observed-model", "choices": [{"message": {"content": content, "tool_calls": calls or []}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3}}


def call(cid="tool-1", args='{"a":19,"b":23}'):
    return {"id": cid, "type": "function", "function": {"name": "calculate_sum", "arguments": args}}


def fixture(root, layout="standalone", *, tool=True, finished=True):
    folder = root / {"standalone": "invocation-one/output", "steps": "steps/0001", "legacy": "evaluation/inputs/0001"}[layout]
    save(root / "run.json", {"run_id": "run-a", "agent_id": "fixture", "status": "succeeded" if finished else "running"})
    save(root / "request/target.json", {"architecture": {"source_revision": "frozen-revision"}})
    if layout == "standalone":
        save(folder.parent / "input/request.json", {"schema": "abb.invocation.v1", "run_id": "inv-one", "input": "你好 ¡España!"})
    else:
        save(folder / "input.json", {"payload": "你好 ¡España!", "input_id": "input-one"})
    rows = [span("root"), span("model", "root", "llm", "model", input={})]
    rows.append(event("span_end", span_id="model", output={"generations": [[{"message": {"content": "你好 ¡España!", "type": "ai"}}]]}))
    if tool:
        rows += [span("tool", "root", "tool", "calculate_sum", input={"a": 19, "b": 23}, tool_call_id="tool-1"),
                 event("span_end", span_id="tool", output="42")]
    lines(folder / "framework.jsonl", rows)
    lines(root / "network.jsonl", [event("llm_request", call_id="wire-1", framework_span_id="model",
        payload={"model": "configured-model", "messages": [{"role": "system", "content": "Be exact"}, {"role": "user", "content": "你好 ¡España!"}], "tools": []}),
        event("llm_response", call_id="wire-1", payload=response(calls=[call()] if tool else []))])
    save(folder / "result.json", {"output": "你好 ¡España!"})
    return folder


def child_bundle(root):
    from agentbench.trajectory.atif.reader import read_evidence
    folder = fixture(root)
    rows = [span("root")]
    network = []
    for label in ("one", "two"):
        rows += [span("delegate-"+label, "root", "tool", "any-tool-name",
                      input={"subagent_type": "same-name", "description": label}, tool_call_id="delegate-call-"+label),
                 span("child-"+label, "delegate-"+label, "chain", "same-name", metadata={"lc_agent_name": "same-name"}, input={"messages": [label]}),
                 span("model-"+label, "child-"+label, "llm", "model", input={}),
                 event("span_end", span_id="model-"+label, output={}),
                 span("tool-"+label, "child-"+label, "tool", "calculate_sum", input={"a": 19, "b": 23}, tool_call_id="reused-id"),
                 event("span_end", span_id="tool-"+label, output="42")]
        network += [event("llm_request", call_id="wire-"+label, framework_span_id="model-"+label, payload={"messages": []}),
                    event("llm_response", call_id="wire-"+label, payload=response("identical text", [call("reused-id")]))]
    lines(folder / "framework.jsonl", rows)
    lines(root / "network.jsonl", network)
    return read_evidence(root)
