"""mitmproxy lifecycle and fail-closed tests, run in the interceptor lab image."""
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest

http = pytest.importorskip("mitmproxy.http")
from defuzex_model_interceptor.addon import ModelInterceptorAddon
from defuzex_model_interceptor.config import ServiceConfig, Credential, Route, Target


@pytest.mark.parametrize('purpose', ['tool', 'evaluation'])
def test_tool_exchange_captures_full_bodies_and_strips_correlation(build, purpose):
    from dataclasses import replace
    from defuzex_model_interceptor.config import ToolRoute
    from defuzex_model_interceptor.policy import EgressPolicy
    addon, flow = build()
    addon.config = replace(addon.config, tool_routes=(ToolRoute(('service.example',), (443,), ('POST',), ('/callback',), purpose),))
    addon.policy = EgressPolicy(addon.config)
    body = json.dumps({'input_id': 'input-any', 'text': '中文' * 10000, 'api_key': 'real-secret'}).encode()
    flow.request = http.Request.make('POST', 'https://service.example/callback?token=temporary', body,
                                   {'content-type': 'application/json', 'x-abb-framework-span': 'span-any'})
    with patch('defuzex_model_interceptor.addon.emit') as emit:
        addon.request(flow)
        assert flow.response is None and flow.request.content == body
        assert 'x-abb-framework-span' not in flow.request.headers
        request = emit.call_args.kwargs
        assert request['payload']['text'] == '中文' * 10000
        assert request['purpose'] == purpose and request['framework_span_id'] == 'span-any'
        assert request['path'] == '/callback' and request['truncated'] is False
        assert 'real-secret' not in json.dumps(request) and 'temporary' not in json.dumps(request)
        response_body = b'{"accepted":true,"output":{"n":2}}'
        flow.response = http.Response.make(200, response_body, {'content-type': 'application/json'})
        addon.response(flow)
        response = emit.call_args.kwargs
        assert emit.call_args.args[0] == 'tool_response'
        assert response['call_id'] == request['call_id']
        assert response['payload']['output'] == {'n': 2}
        assert response['latency_ms'] >= 0 and flow.response.content == response_body
        flow.error = 'connection ended'
        addon.error(flow)
        assert emit.call_args.args[0] == 'tool_error'
        assert emit.call_args.kwargs['call_id'] == request['call_id']

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


def test_blocked_request_event_names_the_undeclared_host(build):
    addon, flow = build()
    flow.request = http.Request.make("GET", "https://api.github.com/repos/owner/name/releases/latest?page=1")
    with patch("defuzex_model_interceptor.addon.emit") as emit:
        addon.request(flow)
        assert flow.response.status_code == 403
        assert emit.call_args.args[0] == "llm_error"
        event = emit.call_args.kwargs
        assert event["error"] == "Undeclared network request blocked"
        assert event["source_host"] == "api.github.com"
        # The query string may carry credentials and is never part of the event.
        assert event["source_path"] == "/repos/owner/name/releases/latest"
        assert event["method"] == "GET"
