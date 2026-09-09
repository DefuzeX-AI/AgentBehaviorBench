"""Offline terminal review; framework and wire traces are kept distinct."""
import json
from pathlib import Path


def read_events(directory: Path):
    for path in sorted(directory.rglob("*.jsonl")):
        if path.is_symlink():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield {"source": "storage", "event": "incomplete_line", "data": {"file": str(path), "line": number}}


def render_review(directory: Path):
    result = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    lines = [f"Run: {result['run_id']}", f"Agent: {result['agent_id']}  Status: {result['status']}"]
    if result.get("error"):
        lines.append("Error: " + result["error"])
    spans, endings, calls = {}, {}, {}
    for event in read_events(directory):
        data = event["data"]
        if event["event"] == "span_start":
            spans[data["span_id"]] = data
        elif event["event"] in {"span_end", "span_error"}:
            endings[data["span_id"]] = event["event"]
        elif event["event"] == "llm_request":
            calls[data["call_id"]] = data
        elif event["event"] == "incomplete_line":
            lines.append(f"Warning: incomplete trace line in {data['file']}")
    lines.append("Framework spans:")
    for span_id, span in spans.items():
        depth, parent, visited = 0, span.get("parent_span_id"), {span_id}
        while parent in spans and parent not in visited:
            visited.add(parent)
            depth += 1
            parent = spans[parent].get("parent_span_id")
        status = {"span_end": "ok", "span_error": "error"}.get(endings.get(span_id), "incomplete")
        lines.append("  " * min(depth + 1, 16) + f"{span.get('name', '?')} [{status}] {span_id}")
    lines.append("Model wire calls (not additional framework spans):")
    for call_id, call in calls.items():
        span = call.get("framework_span_id")
        lines.append(f"  {call_id} {call.get('source_model')} → {call.get('model')} "
                     f"span={span if span in spans else 'uncorrelated'}")
    lines.append(f"Artifacts: {directory.resolve()}")
    return "\n".join(lines)
