"""mitmproxy lifecycle and fail-closed tests, run in the interceptor lab image."""
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest

http = pytest.importorskip("mitmproxy.http")
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon
from defuzex_model_interceptor.config import ServiceConfig, Credential, Route, Target


@pytest.mark.parametrize('purpose', ['tool', 'evaluation'])
def test_tool_exchange_captures_full_bodies_and_strips_correlation(build, purpose):
    from dataclasses import replace
    from defuzex_model_interceptor.config import ToolRoute
    from defuzex_model_interceptor.routing.policy import EgressPolicy
    addon, flow = build()
    addon.config = replace(addon.config, tool_routes=(ToolRoute(('service.example',), (443,), ('POST',), ('/callback',), purpose),))
    addon.policy = EgressPolicy(addon.config)
    body = json.dumps({'input_id': 'input-any', 'text': '中文' * 10000, 'api_key': 'real-secret'}).encode()
    flow.request = http.Request.make('POST', 'https://service.example/callback?token=temporary', body,
                                   {'content-type': 'application/json', 'x-abb-framework-span': 'span-any'})
    with patch('defuzex_model_interceptor.proxy.addon.emit') as emit:
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
        assert emit.call_args.kwargs['error_code'] == 'transport_error'
        assert emit.call_args.kwargs['request_kind'] == 'tool'
        assert emit.call_args.kwargs['purpose'] == purpose

@pytest.fixture
def build():
    with patch("defuzex_model_interceptor.proxy.addon.emit"):
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
    with patch("defuzex_model_interceptor.proxy.addon.emit") as emit:
        addon.request(flow)
    assert emit.call_args.kwargs["error_code"] == "request_preparation_failed"
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
    with patch("defuzex_model_interceptor.proxy.addon.emit") as emit:
        assert flow.response.stream(b'data: {"error":{"message":"failed real-secret"}}\n\n') == []
    assert emit.call_args.kwargs["error_code"] == "stream_processing_failed"
    assert emit.call_args.kwargs["upstream_status"] == 200
    assert "real-secret" not in json.dumps(emit.call_args.kwargs)
    assert "real-secret" not in flow.response.trailers["grpc-message"]
    assert flow.response.trailers["grpc-status"] == "13"
    assert flow.response.stream(b"") == b""
    assert flow.response.trailers["grpc-status"] == "13"


@pytest.mark.parametrize("url,method", [
    ("https://api.github.com/releases?token=hidden-query", "GET"),
    ("https://api.openai.com:8443/v1/chat/completions", "POST"),
    ("https://api.openai.com/v1/chat/completions", "GET"),
    ("https://api.openai.com/undeclared", "POST"),
])
def test_denied_request_has_original_address_and_remains_unclassified(build, url, method):
    addon, flow = build()
    flow.request = http.Request.make(method, url)
    with patch("defuzex_model_interceptor.proxy.addon.emit") as emit:
        addon.request(flow)
    fields = emit.call_args.kwargs
    assert flow.response.status_code == 403
    assert emit.call_args.args == ("llm_error",)
    assert fields["error"] == "Undeclared network request blocked"
    assert fields["error_code"] == "egress_denied"
    assert fields["error_stage"] == "policy"
    assert fields["request_kind"] == "unknown"
    assert fields["source_host"] == flow.request.pretty_host
    assert fields["source_port"] == flow.request.port
    assert fields["source_path"] == flow.request.path.split("?", 1)[0]
    assert fields["method"] == method
    assert fields["local_status"] == 403
    assert fields["upstream_status"] is None
    assert fields["target_host"] is None
    assert "hidden-query" not in json.dumps(fields)


def test_authentication_failure_is_local_and_retains_matched_route(build):
    addon, flow = build(headers={"authorization": "Bearer wrong"})
    with patch("defuzex_model_interceptor.proxy.addon.emit") as emit:
        addon.request(flow)
    fields = emit.call_args.kwargs
    assert flow.response.status_code == 401
    assert fields["error_code"] == "authentication_failed"
    assert fields["route_id"] == "route"
    assert fields["request_kind"] == "model"
    assert fields["upstream_status"] is None
    assert fields["target_host"] is None


@pytest.mark.parametrize("body,status,code,local_status", [
    (b'{"error":{"message":"rate limited real-secret"}}', 429, "upstream_error", 429),
    (b'not json real-secret', 200, "response_conversion_failed", 502),
])
def test_response_failure_distinguishes_original_and_forwarded_request(build, body, status, code, local_status):
    addon, flow = build()
    addon.request(flow)
    flow.response = http.Response.make(status, body, {"content-type": "application/json"})
    with patch("defuzex_model_interceptor.proxy.addon.emit") as emit:
        addon.responseheaders(flow)
        addon.response(flow)
    fields = emit.call_args.kwargs
    assert fields["error_code"] == code
    assert fields["upstream_status"] == status
    assert fields["local_status"] == local_status
    assert fields["source_host"] == "api.openai.com"
    assert fields["source_path"] == "/v1/chat/completions"
    assert fields["target_host"] == "openrouter.ai"
    assert fields["target_path"] == "/api/v1/chat/completions"
    assert "real-secret" not in json.dumps(fields)


def test_transport_failure_does_not_invent_an_http_status(build):
    addon, flow = build()
    addon.request(flow)
    flow.error = "Client disconnected. real-secret"
    with patch("defuzex_model_interceptor.proxy.addon.emit") as emit:
        addon.error(flow)
    fields = emit.call_args.kwargs
    assert fields["error_code"] == "transport_error"
    assert fields["local_status"] is None
    assert fields["upstream_status"] is None
    assert fields["error"] == "Client disconnected. [REDACTED]"
