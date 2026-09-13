"""Explicit text-only Gemini ↔ OpenAI Chat semantic conversion.

Unsupported semantics fail closed instead of silently degrading a research run.
Google GAPIC REST streaming expects a JSON array; alt=sse clients expect SSE.
"""


from defuzex_model_interceptor.transport.json import json_bytes, json_request
from defuzex_model_interceptor.transport.sse import SSEDecoder


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
    """Backward-compatible facade over the shared framing/translation engine."""
    def __init__(self, *, sse=False, max_event_bytes=1048576):
        wire = GeminiWire()
        wire.sse = sse
        self._stream = GeminiWireStream(wire)
        self._stream.parser.maximum = max_event_bytes

    def feed(self, chunk):
        return self._stream.feed(chunk)


class GeminiWire:
    endpoint = "/chat/completions"
    response_type = "application/json"
    passthrough = False

    def __init__(self, grpc=False):
        self.grpc, self.sse = grpc, False

    @property
    def stream_type(self):
        return "text/event-stream" if self.sse else "application/json"

    def decode(self, request):
        if self.grpc:
            from .grpc import unpack_request
            if not request.headers.get("content-type", "").startswith("application/grpc"):
                raise ValueError("Expected gRPC content type")
            source = unpack_request(request.content, request.headers.get("grpc-encoding", "identity"))
            method = request.path.rsplit("/", 1)[-1]
            if method not in {"GenerateContent", "StreamGenerateContent"}:
                raise ValueError("Unsupported Gemini RPC")
            self.streaming = method == "StreamGenerateContent"
            self.source_model = source.get("model")
        else:
            source = json_request(request)
            self.streaming = ":streamGenerateContent" in request.path
            self.sse = "alt=sse" in request.path
            self.source_model = request.path.split("/models/", 1)[-1].split(":", 1)[0]
        return source, request_to_chat(source, streaming=self.streaming)

    def response(self, payload, status):
        return response_from_chat(payload, status=status)

    def encode_response(self, payload):
        if self.grpc:
            from .grpc import pack_response
            return pack_response(payload)
        return json_bytes(payload)

    def stream(self):
        return GeminiWireStream(self)


class GeminiWireStream:
    def __init__(self, wire):
        self.wire = wire
        self.parser = SSEDecoder()
        self.first = True

    def feed(self, chunk):
        output = bytearray()
        for event in self.parser.feed(chunk):
            payload = response_from_chat(event)
            if self.wire.grpc:
                from .grpc import pack_response
                output.extend(pack_response(payload))
            elif self.wire.sse:
                output.extend(b"data: " + json_bytes(payload) + b"\n\n")
            else:
                output.extend((b"[" if self.first else b",") + json_bytes(payload))
            self.first = False
        if not chunk and not self.wire.grpc and not self.wire.sse:
            output.extend(b"[]" if self.first else b"]")
        return bytes(output)
