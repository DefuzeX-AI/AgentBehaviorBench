"""Real proxy request/response regressions for omitted model routes.

Run with the interceptor's installed dependencies; no external model is called.
"""
import json
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from google.ai.generativelanguage_v1beta.types import GenerateContentRequest, GenerateContentResponse
from mitmproxy import http

from defuzex_model_interceptor.config import Credential, Route, ServiceConfig, Target, ToolRoute
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon


def config(routes=()):
    return ServiceConfig(
        agent_id="test-agent", max_trace_bytes=4096,
        target=Target("openrouter", "openrouter", "https://target.example/api/v1", "test/model", {}),
        credentials=(Credential("google", "google-api-key", "google-run-token", "target-test-secret"),
                     Credential("openai", "bearer-token", "openai-run-token", "target-test-secret")),
        routes=routes,
        tool_routes=(ToolRoute(("search.example",), (443,), ("POST",), ("/search",)),),
    )


def flow(url, content, headers, method="POST"):
    return SimpleNamespace(request=http.Request.make(method, url, content, headers),
                           response=None, metadata={})


def grpc_flow(method="GenerateContent"):
    message = GenerateContentRequest(model="models/source-model", contents=[
        {"role": "user", "parts": [{"text": "Say hello"}]}])
    data = GenerateContentRequest.serialize(message)
    return flow("https://generativelanguage.googleapis.com/"
                "google.ai.generativelanguage.v1beta.GenerativeService/" + method,
                struct.pack(">BI", 0, len(data)) + data,
                {"content-type": "application/grpc", "x-goog-api-key": "google-run-token"})


class AutomaticModelRoutingTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        patched = patch("defuzex_model_interceptor.observation.events.emit",
                        side_effect=lambda event, **data: self.events.append({"event": event, **data}))
        patched.start()
        self.addCleanup(patched.stop)

    def test_captured_grpc_request_with_only_rest_route_reaches_converter(self):
        rest = Route("gemini-rest", ("generativelanguage.googleapis.com",), (443,), ("POST",),
                     ("/v1beta/models/*:generateContent*",), "gemini-content", "google")
        addon, request = ModelInterceptorAddon(config((rest,))), grpc_flow()
        addon.request(request)
        self.assertIsNone(request.response, "Model request was rejected before conversion")
        self.assertEqual(request.request.host, "target.example")
        self.assertEqual(request.request.path, "/api/v1/chat/completions")
        self.assertEqual(json.loads(request.request.content)["messages"],
                         [{"role": "user", "content": "Say hello"}])
        request.response = http.Response.make(200, json.dumps({"choices": [
            {"index": 0, "message": {"content": "Hello"}, "finish_reason": "stop"}]}).encode(),
            {"content-type": "application/json"})
        addon.response(request)
        message = GenerateContentResponse.deserialize(request.response.content[5:])
        self.assertEqual(message.candidates[0].content.parts[0].text, "Hello")
        self.assertEqual(request.response.trailers["grpc-status"], "0")
        self.assertEqual([e["event"] for e in self.events], ["llm_request", "llm_response"])
        self.assertNotIn("target-test-secret", json.dumps(self.events))

    def test_grpc_stream_without_any_model_routes_retains_trace_and_framing(self):
        addon, request = ModelInterceptorAddon(config()), grpc_flow("StreamGenerateContent")
        addon.request(request)
        self.assertIsNone(request.response)
        self.assertTrue(json.loads(request.request.content)["stream"])
        request.response = http.Response.make(200, b"", {"content-type": "text/event-stream"})
        addon.responseheaders(request)
        event = {"choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}]}
        data = request.response.stream(b"data: " + json.dumps(event).encode() + b"\n\ndata: [DONE]\n\n")
        request.response.stream(b"")
        self.assertEqual(GenerateContentResponse.deserialize(data[5:]).candidates[0].content.parts[0].text, "Hello")
        self.assertEqual(request.response.trailers["grpc-status"], "0")
        self.assertEqual(self.events[-1]["event"], "llm_response")

    def test_openai_compatible_custom_host_without_model_routes(self):
        addon = ModelInterceptorAddon(config())
        request = flow("https://compatible.example/custom/v1/chat/completions",
                       json.dumps({"model": "source", "messages": [{"role": "user", "content": "Hi"}]}).encode(),
                       {"content-type": "application/json", "authorization": "Bearer openai-run-token"})
        addon.request(request)
        self.assertIsNone(request.response)
        self.assertEqual(request.request.host, "target.example")
        self.assertEqual(json.loads(request.request.content)["model"], "test/model")

    def test_known_protocol_with_wrong_token_cannot_fall_through_to_tool_route(self):
        settings = config()
        settings = ServiceConfig(settings.agent_id, settings.max_trace_bytes, settings.target,
                                 settings.credentials, (), (ToolRoute(("generativelanguage.googleapis.com",),
                                 (443,), ("POST",), ("/google.ai.generativelanguage.v1beta.GenerativeService/*",)),))
        addon, request = ModelInterceptorAddon(settings), grpc_flow()
        request.request.headers["x-goog-api-key"] = "wrong-token"
        addon.request(request)
        self.assertIsNotNone(request.response)
        self.assertEqual(self.events[-1]["error_code"], "authentication_failed")
        self.assertEqual(request.request.host, "generativelanguage.googleapis.com")
        self.assertNotIn("target-test-secret", str(request.request.headers))

    def test_non_model_tool_policy_is_preserved(self):
        addon = ModelInterceptorAddon(config())
        allowed = flow("https://search.example/search", b'{}', {"content-type": "application/json"})
        addon.request(allowed)
        self.assertIsNone(allowed.response)
        self.assertEqual(allowed.request.host, "search.example")
        denied = flow("https://unknown.example/private", b'{}', {"content-type": "application/json"})
        addon.request(denied)
        self.assertEqual(denied.response.status_code, 403)
        self.assertEqual(self.events[-1]["error_code"], "egress_denied")


if __name__ == "__main__":
    unittest.main()
