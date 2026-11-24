"""Join Agent-exported operations only through recorded, unique identifiers."""
from collections import Counter, defaultdict
import json
from agentbench.harness.otel.evidence import display_span
from agentbench.observe.tool_links import SCOPE_KEYS, compatible


def rows(api):
    try:
        path = api.file("otel/spans.jsonl")
    except FileNotFoundError:
        return
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as stream:
        for line, text in enumerate(stream, 1):
            if text.strip():
                yield {"file": "otel/spans.jsonl", "line": line, "raw": json.loads(text)}


def operations(records):
    seen = set()
    for ref in records:
        if ref["file"] != "otel/spans.jsonl":
            continue
        row = ref["raw"]
        if row.get("schema") != "abb.agent-otel.v1" or row.get("origin") not in ("agent_native", "auto_instrumented"):
            continue
        data = display_span(row)
        key = (data["trace_id"], data["span_id"])
        if key in seen:
            continue
        seen.add(key)
        attrs = data["attributes"]
        op = attrs.get("gen_ai.operation.name", "")
        typ = attrs.get("openinference.span.kind")
        kind = ("tool" if op == "execute_tool" or typ == "TOOL" else
                "model" if op in ("chat", "generate_content", "text_completion") or typ == "LLM" else "span")
        yield {**data, "kind": kind, "ref": ref,
               "tool_call_id": attrs.get("gen_ai.tool.call.id"), "call_id": attrs.get("abb.call_id"),
               "input_id": row.get("context", {}).get("input_id") or attrs.get("abb.input_id"),
               "case_id": row.get("context", {}).get("case_id"),
               "invocation_id": row.get("context", {}).get("invocation_id") or attrs.get("abb.invocation_id"),
               "native_session_id": attrs.get("openclaw.session.key") or attrs.get("gen_ai.conversation.id")}


def _decoded(value):
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def content(item):
    attrs = item["attributes"]
    if item["kind"] == "tool":
        return {"tool_name": attrs.get("gen_ai.tool.name") or attrs.get("tool.name") or item["name"],
                "input_arguments": _decoded(attrs.get("gen_ai.tool.call.arguments", attrs.get("input.value"))),
                "outputs": _decoded(attrs.get("gen_ai.tool.call.result", attrs.get("output.value")))}
    if item["kind"] == "model":
        return {"input": _decoded(attrs.get("gen_ai.input.messages", attrs.get("input.value"))),
                "output": _decoded(attrs.get("gen_ai.output.messages", attrs.get("output.value")))}
    return {}


def _count(value):
    if type(value) is int:
        return value if value >= 0 else None
    return int(value) if isinstance(value, str) and value.isdigit() else None


def inference(item):
    """Step content of a model span that recorded GenAI messages, else None.

    An aggregate usage span, or a call captured without content, records no
    assistant message and cannot be represented as a step.
    """
    attrs = item["attributes"]
    messages = _decoded(attrs.get("gen_ai.output.messages"))
    if not isinstance(messages, list):
        return None
    replies = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
    if not replies:
        return None
    text, reasoning, calls = [], [], []
    for part in (p for m in replies for p in (m.get("parts") or []) if isinstance(p, dict)):
        if part.get("type") == "tool_call":
            calls.append({"id": part.get("id"), "name": part.get("name"), "arguments": _decoded(part.get("arguments"))})
        elif part.get("type") in ("text", "reasoning") and isinstance(part.get("content"), str):
            (text if part["type"] == "text" else reasoning).append(part["content"])
    usage = {target: count for target, source in (("prompt_tokens", "gen_ai.usage.input_tokens"),
                                                  ("completion_tokens", "gen_ai.usage.output_tokens"))
             if (count := _count(attrs.get(source))) is not None}
    cached = _count(attrs.get("gen_ai.usage.cache_read.input_tokens"))
    if cached is not None:
        usage["prompt_tokens_details"] = {"cached_tokens": cached}
    request = {"messages": _decoded(attrs.get("gen_ai.input.messages")), "model": attrs.get("gen_ai.request.model")}
    if attrs.get("gen_ai.tool.definitions") is not None:
        request["tools"] = _decoded(attrs["gen_ai.tool.definitions"])
    return {"input": request,
            "output": {"text": "".join(text), "reasoning": "".join(reasoning) or None, "tool_calls": calls,
                       "finish_reason": replies[-1].get("finish_reason"), "usage": usage or None,
                       "model": attrs.get("gen_ai.response.model") or attrs.get("gen_ai.request.model")}}


def emitted_ids(item):
    messages = content(item).get("output")
    if not isinstance(messages, list):
        return ()
    return tuple(sorted({part["id"] for msg in messages if isinstance(msg, dict) and msg.get("role") == "assistant"
                         for part in (msg.get("parts") or []) if isinstance(part, dict)
                         and part.get("type") == "tool_call" and isinstance(part.get("id"), str)}))


def correlate(records, operations):
    """Return matched records; conflicting/missing IDs stay in the raw inventory."""
    by_key = defaultdict(list)
    for record in records:
        field = "tool_call_id" if record["kind"] == "tool" else "call_id"
        if record.get(field):
            by_key[(field, record[field])].append(record)
        if record["kind"] == "model":
            output = record.get("client_output") or record.get("output") or {}
            calls = output.get("tool_calls") if isinstance(output, dict) else None
            ids = tuple(sorted({c["id"] for c in calls or [] if isinstance(c, dict) and isinstance(c.get("id"), str)}))
            if ids:
                by_key[("emitted", ids)].append(record)
    selected = []
    counts = Counter()
    for item in operations:
        field = "tool_call_id" if item["kind"] == "tool" else "call_id"
        candidates = by_key.get((field, item[field]), ()) if item["kind"] in ("model", "tool") else ()
        if not candidates and item["kind"] == "model":
            candidates = by_key.get(("emitted", emitted_ids(item)), ())
        matches = [record for record in candidates if compatible(record, item)]
        match = matches[0] if len(matches) == 1 else None
        if match:
            counts[id(match)] += 1
        selected.append((item, match))
    for item, match in selected:
        yield item, match if match is not None and counts[id(match)] == 1 else None
