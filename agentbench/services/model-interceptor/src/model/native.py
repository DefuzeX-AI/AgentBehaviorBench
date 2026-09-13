"""Pass-through JSON model protocols and their streaming responses."""
from defuzex_model_interceptor.transport.json import json_request
from defuzex_model_interceptor.transport.sse import SSEDecoder


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
