"""Per-call wire Strategies selected by a registry, independent of target routing.

A strategy translates requests and responses. JsonHttpProtocol remains a trace
decoder for compatibility with existing decoder plugins.
"""
import json
from importlib.metadata import entry_points
from typing import Protocol
from ..gemini import request_to_chat, response_from_chat
from .sse import SSEDecoder


def json_bytes(value, *, ascii_only=False):
    return json.dumps(value, ensure_ascii=ascii_only, separators=(",", ":")).encode("utf-8")


def json_request(request):
    payload = json.loads(request.content or b"{}")
    if not isinstance(payload, dict):
        raise ValueError("Model request body must be an object")
    return payload


class WireStrategy(Protocol):
    endpoint: str
    response_type: str
    def decode(self, request) -> tuple[dict, dict]: ...
    def response(self, payload, status: int) -> dict: ...
    def stream(self): ...


class NativeJsonWire:
    response_type = "application/json"
    grpc = False
    passthrough = True

    def __init__(self, endpoint, terminal="done"):
        self.endpoint, self.terminal = endpoint, terminal

    def decode(self, request):
        source = json_request(request)
        self.source_model = source.get("model")
        self.streaming = source.get("stream", False)
        return source, dict(source)

    def response(self, payload, status):
        return payload

    def stream(self):
        return NativeStream(self.terminal)


class NativeStream:
    def __init__(self, terminal):
        self.parser = SSEDecoder(terminal)
    def feed(self, chunk):
        self.parser.feed(chunk)
        return chunk


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


def load_wires():
    from .ollama import OllamaWire
    registry = {
        "openai-chat": lambda: NativeJsonWire("/chat/completions"),
        "openai-responses": lambda: NativeJsonWire("/responses", "response.completed"),
        "anthropic-messages": lambda: NativeJsonWire("/messages", "message_stop"),
        "openai-completions": lambda: NativeJsonWire("/completions"),
        "openai-embeddings": lambda: NativeJsonWire("/embeddings"),
        "gemini-content": GeminiWire,
        "gemini-grpc": lambda: GeminiWire(grpc=True),
        "ollama-chat": OllamaWire,
        "ollama-generate": lambda: OllamaWire(generate=True),
    }
    for entry in entry_points(group="defuzex.model_interceptor.wires"):
        if entry.name in registry:
            raise ValueError("Duplicate wire strategy: " + entry.name)
        registry[entry.name] = entry.load()
    return registry
