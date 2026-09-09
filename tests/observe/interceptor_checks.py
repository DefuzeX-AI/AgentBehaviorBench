"""Run in the actual Interceptor image with its installed mitmproxy objects."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from mitmproxy import http
from defuzex_model_interceptor.addon import ModelInterceptorAddon
from defuzex_model_interceptor.config import ServiceConfig, Credential, Route, Target


class InterceptorChecks(unittest.TestCase):
    def test_large_event_transport(self):
        from defuzex_model_interceptor.events import emit
        emit("large_transport_test", raw_body="完整输出" * 100000 + "[DONE]")

    def test_large_stream_is_fully_recorded_and_forwarded(self):
        with patch("defuzex_model_interceptor.addon.emit") as emit:
            addon, flow = self.make("openai-chat", True)
            flow.response = http.Response.make(200, b"", {"content-type": "text/event-stream"})
            addon.responseheaders(flow)
            text = "完整中文内容" * 50000
            data = ("data: " + json.dumps({"choices": [{"delta": {"content": text}}]}, ensure_ascii=False)
                    + '\n\ndata: {"choices":[],"usage":{"total_tokens":123}}\n\ndata: [DONE]\n\n').encode()
            output = b"".join(flow.response.stream(data[i:i+4093]) for i in range(0, len(data), 4093))
            output += flow.response.stream(b"")
            self.assertEqual(output, data)
            response = [c.kwargs for c in emit.call_args_list if c.args[0] == "llm_response"][0]
            self.assertFalse(response["truncated"])
            self.assertEqual(response["payload"]["events"][0]["choices"][0]["delta"]["content"], text)
            self.assertEqual(response["payload"]["events"][-1]["usage"]["total_tokens"], 123)
            self.assertEqual(response["raw_body"], data.decode())

    def test_large_json_request_and_response_are_complete(self):
        with patch("defuzex_model_interceptor.addon.emit") as emit:
            addon, flow = self.make()
            text = "完整输入输出" * 50000
            # Restore a source request and send it through the real routing code.
            flow.request = http.Request.make("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                json.dumps({"contents": [{"role": "user", "parts": [{"text": text}]}]}).encode(),
                {"x-goog-api-key": "temporary", "content-type": "application/json"})
            addon.request(flow)
            request = [c.kwargs for c in emit.call_args_list if c.args[0] == "llm_request"][-1]
            self.assertFalse(request["truncated"])
            self.assertEqual(request["payload"]["messages"][0]["content"], text)
            self.assertEqual(json.loads(request["source_raw_body"])["contents"][0]["parts"][0]["text"], text)
            body = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}).encode()
            flow.response = http.Response.make(200, body, {"content-type": "application/json"})
            addon.responseheaders(flow)
            addon.response(flow)
            response = [c.kwargs for c in emit.call_args_list if c.args[0] == "llm_response"][-1]
            self.assertFalse(response["truncated"])
            self.assertEqual(response["raw_body"], body.decode())
            self.assertEqual(json.loads(flow.response.content)["candidates"][0]["content"]["parts"][0]["text"], text)

    def make(self, protocol="gemini-content", stream=False, token="temporary"):
        google = protocol == "gemini-content"
        host = "generativelanguage.googleapis.com" if google else "api.openai.com"
        path = "/v1beta/models/gemini-2.5-flash:" + ("streamGenerateContent" if stream else "generateContent") if google else "/v1/chat/completions"
        credential = Credential("main", "google-api-key" if google else "bearer-token", "temporary", "upstream-secret")
        route = Route("main", (host,), (443,), ("POST",), (path,), protocol, "main")
        addon = ModelInterceptorAddon(ServiceConfig("test", 262144, Target("openrouter", "openrouter", "https://openrouter.ai/api/v1", "target/model", {}), (credential,), (route,)))
        payload = {"contents": [{"role": "user", "parts": [{"text": "你好"}]}]} if google else {"model": "source", "messages": [{"role": "user", "content": "你好"}], "stream": stream}
        headers = {"x-goog-api-key": token} if google else {"authorization": "Bearer " + token}
        headers.update({"content-type": "application/json", "x-abb-framework-span": "span-123"})
        request = http.Request.make("POST", f"https://{host}{path}", json.dumps(payload).encode(), headers)
        flow = SimpleNamespace(request=request, metadata={}, response=None)
        addon.request(flow)
        return addon, flow

    def test_google_roundtrip_and_auth(self):
        addon, flow = self.make()
        self.assertEqual(flow.request.host, "openrouter.ai")
        self.assertEqual(flow.request.headers["authorization"], "Bearer upstream-secret")
        self.assertNotIn("x-goog-api-key", flow.request.headers)
        self.assertNotIn("x-abb-framework-span", flow.request.headers)
        self.assertEqual(flow.metadata["framework_span_id"], "span-123")
        self.assertEqual(json.loads(flow.request.content)["model"], "target/model")
        flow.response = http.Response.make(200, json.dumps({"choices": [{"message": {"content": "响应"}, "finish_reason": "stop"}]}).encode(), {"content-type": "application/json"})
        addon.responseheaders(flow)
        addon.response(flow)
        self.assertEqual(json.loads(flow.response.content)["candidates"][0]["content"]["parts"][0]["text"], "响应")

    def test_original_openai_stream_is_unchanged(self):
        addon, flow = self.make("openai-chat", True)
        flow.response = http.Response.make(200, b"", {"content-type": "text/event-stream"})
        addon.responseheaders(flow)
        data = b'data: {"choices":[]}\n\ndata: [DONE]\n\n'
        self.assertEqual(flow.response.stream(data), data)
        self.assertEqual(flow.response.stream(b""), b"")
        addon.response(flow)

    def test_google_fragmented_stream_and_events(self):
        with patch("defuzex_model_interceptor.addon.emit") as emit:
            addon, flow = self.make(stream=True)
            flow.response = http.Response.make(200, b"", {"content-type": "text/event-stream"})
            addon.responseheaders(flow)
            data = ('data: ' + json.dumps({"choices": [{"delta": {"content": "中文"}, "finish_reason": "stop"}]}, ensure_ascii=False) + '\n\ndata: [DONE]\n\n').encode()
            output = b"".join(flow.response.stream(bytes([x])) for x in data) + flow.response.stream(b"")
            addon.response(flow)
            self.assertEqual(json.loads(output)[0]["candidates"][0]["content"]["parts"][0]["text"], "中文")
            responses = [call for call in emit.call_args_list if call.args[0] == "llm_response"]
            self.assertEqual(len(responses), 1)
            self.assertIn("events", responses[0].kwargs["payload"])

    def test_bad_token_and_upstream_error(self):
        addon, flow = self.make(token="wrong")
        self.assertEqual(flow.response.status_code, 401)
        addon, flow = self.make()
        flow.response = http.Response.make(429, b'{"error":{"message":"rate limited"}}', {"content-type": "application/json"})
        addon.response(flow)
        self.assertEqual(flow.response.status_code, 429)
        self.assertEqual(json.loads(flow.response.content)["error"]["code"], 429)


if __name__ == "__main__":
    unittest.main()
