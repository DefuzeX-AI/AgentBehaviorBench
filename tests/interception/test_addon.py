"""mitmproxy lifecycle and fail-closed tests, run in the interceptor lab image."""
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest

http = pytest.importorskip("mitmproxy.http")
from defuzex_model_interceptor.addon import ModelInterceptorAddon
from defuzex_model_interceptor.config import ServiceConfig, Credential, Route, Target

@pytest.fixture
def build():
    with patch("defuzex_model_interceptor.addon.emit"):
        def make(protocol="openai-chat", body=None, url=None, headers=None):
            google = protocol.startswith("gemini")
            url = url or ("https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent" if google else "https://api.openai.com/v1/chat/completions")
            request = http.Request.make("POST", url, body if body is not None else b'{"model":"source","messages":[]}',
                headers or ({"x-goog-api-key": "temporary"} if google else {"authorization": "Bearer temporary"}))
            route = Route("route", (request.pretty_host,), (443,), ("POST",), (request.path.split("?")[0],), protocol, "key")
            addon = ModelInterceptorAddon(ServiceConfig("test", 1024, Target("openrouter", "openrouter",
                "https://openrouter.ai/api/v1", "target/model", {}),
                (Credential("key", "google-api-key" if google else "bearer-token", "temporary", "real-secret"),), (route,)))
            flow = SimpleNamespace(request=request, metadata={}, response=None)
            return addon, flow
        yield make

def test_auth_and_target_mutations_are_atomic(build):
    addon, flow = build(body=b"not json")
    addon.request(flow)
    assert flow.response.status_code == 422
    assert flow.request.host == "api.openai.com"
    assert "real-secret" not in str(flow.request.headers)
    assert flow.request.headers["authorization"] == "Bearer temporary"

def test_plugin_exception_never_falls_through(build):
    addon, flow = build()
    class Broken:
        def prepare_request(self, request, **kwargs):
            request.host = "wrong.example"
            raise RuntimeError("plugin crash")
    addon.targets["openrouter"] = Broken()
    addon.request(flow)
    assert flow.response.status_code == 422
    assert flow.request.host == "api.openai.com"
    assert "real-secret" not in str(flow.request.headers)

def test_google_query_auth_is_removed_before_forwarding(build):
    addon, flow = build("gemini-content", b'{"contents":[{"parts":[{"text":"x"}]}]}',
        url="https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent?key=temporary", headers={"content-type": "application/json"})
    addon.request(flow)
    assert flow.response is None
    assert flow.request.path == "/api/v1/chat/completions"
    assert flow.request.headers["authorization"] == "Bearer real-secret"
    assert "x-goog-api-key" not in flow.request.headers

def test_http1_empty_intermediate_chunks_are_suppressed(build):
    addon, flow = build("gemini-content", b'{"contents":[{"parts":[{"text":"x"}]}]}',
        url="https://generativelanguage.googleapis.com/v1beta/models/gemini:streamGenerateContent")
    addon.request(flow)
    flow.response = http.Response.make(200, b"", {"content-type": "text/event-stream", "transfer-encoding": "chunked"})
    addon.responseheaders(flow)
    assert flow.response.stream(b"data: ") == []
    assert flow.response.stream(b'{"choices":[{"delta":{"content":"x"}}]}\n\n')
    assert flow.response.stream(b"data: [DONE]\n\n") == []
    assert flow.response.stream(b"") == b"]"

def test_grpc_stream_error_keeps_nonzero_trailers_at_eof(build):
    from google.ai.generativelanguage_v1beta import GenerateContentRequest
    import struct
    body = GenerateContentRequest.serialize(GenerateContentRequest(model="models/g", contents=[{"parts":[{"text":"x"}]}]))
    addon, flow = build("gemini-grpc", struct.pack(">BI", 0, len(body)) + body,
        url="https://generativelanguage.googleapis.com/google.ai.generativelanguage.v1beta.GenerativeService/StreamGenerateContent",
        headers={"x-goog-api-key": "temporary", "content-type": "application/grpc"})
    addon.request(flow)
    flow.response = http.Response.make(200, b"", {"content-type": "text/event-stream"})
    addon.responseheaders(flow)
    assert flow.response.stream(b'data: {"error":{"message":"failed"}}\n\n') == []
    assert flow.response.trailers["grpc-status"] == "13"
    assert flow.response.stream(b"") == b""
    assert flow.response.trailers["grpc-status"] == "13"

