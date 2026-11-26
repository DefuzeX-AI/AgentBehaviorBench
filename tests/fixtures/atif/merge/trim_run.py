"""Cut a recorded chat run down to the rows and fields the ATIF merge reads.

usage: python tests/fixtures/atif/merge/trim_run.py <run directory> <new fixture directory>
"""
import json
import sys
from pathlib import Path

from agentbench.trajectory.content import model_output

LIMIT = 400


def short(text):
    return text if len(text) <= LIMIT else text[:LIMIT] + " ...(trimmed)"


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values), encoding="utf-8", newline="\n")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def trim_span(row):
    span = row["span"]
    attributes = {item["key"]: item["value"] for item in span.get("attributes", [])}
    name = (attributes.get("gen_ai.tool.name") or {}).get("stringValue")
    kept = []
    for key, value in attributes.items():
        text = value.get("stringValue")
        if key in ("gen_ai.tool.definitions", "gen_ai.system_instructions"):
            continue
        if key == "gen_ai.input.messages" and isinstance(text, str):
            # The delegation adapter reads only the tool call ids replayed in the history.
            try:
                messages = json.loads(text)
            except ValueError:
                messages = []
            history = [{"role": message.get("role"),
                        "parts": [{k: part[k] for k in ("type", "id", "name") if k in part}
                                  for part in message.get("parts") or []
                                  if isinstance(part, dict) and part.get("type") in ("tool_call", "tool_call_response")]}
                       for message in messages if isinstance(message, dict)]
            value = {"stringValue": json.dumps([m for m in history if m["parts"]], ensure_ascii=False)}
        elif key == "gen_ai.tool.call.result" and isinstance(text, str) and len(text) > LIMIT and name != "sessions_spawn":
            value = {"stringValue": short(text)}
        elif isinstance(text, str) and len(text) > LIMIT and not key.startswith("gen_ai."):
            continue
        kept.append({"key": key, "value": value})
    return {"schema": row["schema"], "context": row.get("context", {}), "origin": row["origin"],
            "resource": {"attributes": [item for item in (row.get("resource") or {}).get("attributes", [])
                                        if item.get("key") == "service.name"]},
            "scope": {"name": (row.get("scope") or {}).get("name")},
            "span": {**{k: v for k, v in span.items() if k not in ("attributes", "events", "links")}, "attributes": kept}}


def plain_response(payload):
    """The assembled stream as one non-streaming response with the same output."""
    output = model_output(payload)
    message = {"content": output.get("text") or ""}
    if output.get("reasoning"):
        message["reasoning_content"] = short(output["reasoning"])
    if output.get("tool_calls"):
        message["tool_calls"] = [{"id": call["id"], "type": "function", "function": {
            "name": call["name"], "arguments": json.dumps(call["arguments"], ensure_ascii=False)}} for call in output["tool_calls"]]
    return {"model": output.get("model"), "choices": [{"message": message, "finish_reason": output.get("finish_reason")}],
            "usage": output.get("usage")}


def trim_network(values):
    answered = {row["data"].get("call_id") for row in values if row["event"] == "llm_response"}
    kept = []
    for row in values:
        data, event = row.get("data") or {}, row["event"]
        base = {key: row[key] for key in ("schema", "run_id", "source", "event", "timestamp") if key in row}
        common = {key: data[key] for key in ("agent_id", "call_id", "provider", "model", "sequence", "status", "streaming") if key in data}
        if event == "llm_request":
            kept.append({**base, "data": {**common, "payload": {"model": (data.get("payload") or {}).get("model"), "messages": []}}})
        elif event == "llm_response":
            kept.append({**base, "data": {**common, "payload": plain_response(data.get("payload")), "client_payload": None}})
        elif event == "llm_delta" and data.get("call_id") not in answered:
            kept.append({**base, "data": {**common, "payload": data.get("payload")}})
    return kept


def trim_acp(values):
    kept = []
    for row in values:
        data, event = dict(row.get("data") or {}), row["event"]
        update = data.get("update")
        if event == "session":
            data = {key: data[key] for key in ("sessionId", "input_id", "invocation_id", "agent_id") if key in data}
        elif event == "session_update":
            if not isinstance(update, dict) or update.get("sessionUpdate") not in ("tool_call", "tool_call_update", "agent_message_chunk"):
                continue
            update = dict(update)
            if isinstance(update.get("rawOutput"), str):
                update["rawOutput"] = short(update["rawOutput"])
            elif update.get("rawOutput") is not None:
                update["rawOutput"] = short(json.dumps(update["rawOutput"], ensure_ascii=False))
            if isinstance(update.get("content"), list):
                update["content"] = [{"type": "content", "content": {"type": "text", "text": short(
                    ((item.get("content") or {}).get("text") or "") if isinstance(item, dict) else "")}} for item in update["content"]]
            update.pop("_meta", None)
            data["update"] = update
        elif event not in ("prompt_started", "prompt_completed", "failure"):
            continue
        kept.append({**{key: row[key] for key in ("schema", "run_id", "source", "event", "timestamp") if key in row}, "data": data})
    return kept


def main(source, target):
    source, target = Path(source), Path(target)
    run = json.loads((source / "run.json").read_text(encoding="utf-8"))
    recorded = json.loads((source / "request/target.json").read_text(encoding="utf-8"))
    write(target / "run.json", {"run_id": run["run_id"], "agent_id": run["agent_id"], "status": run["status"]})
    write(target / "request/target.json", {
        "runtime": {"adapter": {"type": recorded["runtime"]["adapter"]["type"]},
                    "evaluation": {"single_input_model_scope": recorded["runtime"]["evaluation"]["single_input_model_scope"]},
                    "atif": recorded["runtime"].get("atif", {})},
        "architecture": {"source_revision": recorded["architecture"]["source_revision"]}})
    for folder in sorted((source / "steps").iterdir()):
        out = target / "steps" / folder.name
        write(out / "input.json", json.loads((folder / "input.json").read_text(encoding="utf-8")))
        if (folder / "result.json").is_file():
            result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
            write(out / "result.json", {key: result[key] for key in ("schema", "status", "output", "run_id", "input_id") if key in result})
        summary = json.loads((folder / "acp-summary.json").read_text(encoding="utf-8"))
        write(out / "acp-summary.json", {"session": {"sessionId": (summary.get("session") or {}).get("sessionId")}})
        write_rows(out / "acp-events.jsonl", trim_acp(rows(folder / "acp-events.jsonl")))
    write_rows(target / "otel/spans.jsonl", [trim_span(row) for row in rows(source / "otel/spans.jsonl")])
    write_rows(target / "logs/network.jsonl", trim_network(rows(source / "logs/network.jsonl")))


if __name__ == "__main__":
    main(*sys.argv[1:])
