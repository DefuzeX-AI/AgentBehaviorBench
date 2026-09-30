"""Pass-through JSON model protocols and their streaming responses."""
from defuzex_model_interceptor.transport.json import json_request
from defuzex_model_interceptor.transport.sse import SSEDecoder
from defuzex_model_interceptor.contracts import SourceSignature


class NativeJsonWire:
    response_type = "application/json"
    grpc = False
    passthrough = True

    def __init__(self, endpoint, terminal="done"):
        self.endpoint, self.terminal = endpoint, terminal
        auth = "anthropic-api-key" if endpoint == "/messages" else "bearer-token"
        self.signature = SourceSignature(("*" + endpoint,), auth)

    def decode(self, request):
        source = json_request(request)
        self.source_model = source.get("model")
        self.streaming = source.get("stream", False)
        return source, dict(source)

    def requirements(self, request):
        from .inputs import conversation_input
        source = json_request(request)
        if self.endpoint == '/embeddings':
            value = source.get('input')
            if isinstance(value, dict) or (isinstance(value, list) and any(isinstance(item, dict) for item in value)):
                raise ValueError('Multimodal embeddings require a wire that declares their input modality')
            return 'embedding', 'text'
        if self.endpoint == '/completions':
            return 'generation', 'text'
        return ('token_count' if getattr(self, 'auxiliary', False) else 'generation',
                conversation_input(source))

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
