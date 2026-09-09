"""Explicit text-only Gemini REST ↔ OpenAI Chat wire conversion.

Unsupported semantics fail closed instead of silently degrading a research run.
Google GAPIC REST streaming expects a JSON array; alt=sse clients expect SSE.
"""
import json


def _text(parts):
    if not isinstance(parts, list) or any(not isinstance(p, dict) or set(p) != {"text"}
                                          or not isinstance(p["text"], str) for p in parts):
        raise ValueError("Only text Gemini parts are supported")
    return "".join(p["text"] for p in parts)


def request_to_chat(payload, *, streaming):
    allowed = {"contents", "systemInstruction", "generationConfig", "model", "tools", "safetySettings"}
    if set(payload) - allowed or payload.get("tools") or payload.get("safetySettings"):
        raise ValueError("Unsupported Gemini tools, safety settings or request fields")
    messages = []
    system = payload.get("systemInstruction")
    if system:
        if set(system) - {"parts", "role"}:
            raise ValueError("Unsupported systemInstruction fields")
        messages.append({"role": "system", "content": _text(system["parts"])})
    for content in payload.get("contents", []):
        if set(content) - {"parts", "role"} or content.get("role", "user") not in {"user", "model"}:
            raise ValueError("Unsupported Gemini content role or fields")
        messages.append({"role": "assistant" if content.get("role") == "model" else "user",
                         "content": _text(content["parts"])})
    if not messages:
        raise ValueError("Gemini contents are required")
    result = {"messages": messages, "stream": streaming}
    if streaming:
        result["stream_options"] = {"include_usage": True}
    mapping = {"temperature": "temperature", "topP": "top_p", "maxOutputTokens": "max_tokens",
               "stopSequences": "stop", "candidateCount": "n", "presencePenalty": "presence_penalty",
               "frequencyPenalty": "frequency_penalty", "seed": "seed"}
    config = payload.get("generationConfig", {})
    if set(config) - mapping.keys():
        raise ValueError(f"Unsupported Gemini generation parameters: {sorted(set(config) - mapping.keys())}")
    if config.get("candidateCount", 1) != 1:
        raise ValueError("Only one Gemini candidate is currently supported")
    result.update({mapping[k]: v for k, v in config.items()})
    return result


def response_from_chat(payload, *, status=200):
    if not isinstance(payload, dict):
        raise ValueError("Upstream response must be a JSON object")
    if status >= 400 or "error" in payload:
        error = payload.get("error", {})
        return {"error": {"code": status if status >= 400 else 502,
                          "message": error.get("message", str(error)) if isinstance(error, dict) else str(error),
                          "status": "RESOURCE_EXHAUSTED" if status == 429 else "INTERNAL"}}
    candidates = []
    if "choices" not in payload and not payload.get("usage"):
        raise ValueError("Upstream response has no choices or usage")
    reasons = {"stop": "STOP", "length": "MAX_TOKENS", "content_filter": "SAFETY"}
    for choice in payload.get("choices", []):
        message = choice.get("message", choice.get("delta", {}))
        if message.get("tool_calls") or message.get("function_call"):
            raise ValueError("Gemini bridge does not support upstream tool calls")
        text = message.get("content") or ""
        if not isinstance(text, str):
            raise ValueError("Upstream content must be text")
        candidate = {"index": choice.get("index", 0),
                     "content": {"role": "model", "parts": [{"text": text}]}}
        reason = choice.get("finish_reason")
        if reason:
            if reason not in reasons:
                raise ValueError(f"Unsupported upstream finish reason: {reason}")
            candidate["finishReason"] = reasons[reason]
        candidates.append(candidate)
    result = {"candidates": candidates}
    usage = payload.get("usage")
    if usage:
        result["usageMetadata"] = {"promptTokenCount": usage.get("prompt_tokens", 0),
                                   "candidatesTokenCount": usage.get("completion_tokens", 0),
                                   "totalTokenCount": usage.get("total_tokens", 0)}
    return result


class GeminiStream:
    def __init__(self, *, sse=False, max_event_bytes=1048576):
        self.sse, self.maximum = sse, max_event_bytes
        self.buffer = bytearray()
        self.first, self.done = True, False

    def feed(self, chunk):
        self.buffer.extend(chunk)
        # Parsing bytes preserves split UTF-8 codepoints and arbitrary TCP boundaries.
        self.buffer[:] = self.buffer.replace(b"\r\n", b"\n")
        output = bytearray()
        while b"\n\n" in self.buffer:
            event, _, rest = self.buffer.partition(b"\n\n")
            self.buffer[:] = rest
            if len(event) > self.maximum:
                raise ValueError("Upstream SSE event exceeds limit")
            data = b"\n".join(line[5:].lstrip() for line in event.split(b"\n") if line.startswith(b"data:"))
            if not data:
                continue
            if data == b"[DONE]":
                self.done = True
                continue
            if self.done:
                raise ValueError("Upstream sent data after DONE")
            payload = json.loads(data)
            if isinstance(payload, dict) and "error" in payload:
                raise ValueError(f"Upstream stream failed: {payload['error']}")
            translated = json.dumps(response_from_chat(payload), ensure_ascii=False).encode("utf-8")
            if self.sse:
                output.extend(b"data: " + translated + b"\n\n")
            else:
                output.extend((b"[" if self.first else b",") + translated)
            self.first = False
        if len(self.buffer) > self.maximum:
            raise ValueError("Upstream SSE event exceeds limit")
        if not chunk:
            if self.buffer.strip() or not self.done:
                raise ValueError("Incomplete upstream Gemini stream")
            if not self.sse:
                output.extend(b"[]" if self.first else b"]")
        return bytes(output)
