"""Proxy evidence retains both upstream and explicitly adapted client streams.

Run with the model-interceptor service dependencies installed; no network calls.
"""
import importlib.util
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from model.thinking import ThinkingChatWire
from defuzex_model_interceptor.observation.decoders import (
    JSON_HTTP_PROTOCOL, THINKING_CHAT_PROTOCOL,
)


@unittest.skipUnless(importlib.util.find_spec("mitmproxy"), "Requires model-interceptor service dependencies")
class ThinkingProxyTests(unittest.TestCase):
    def setUp(self):
        from mitmproxy import http
        from defuzex_model_interceptor.replace.handler import ReplaceInterceptor
        from defuzex_model_interceptor.config import Route
        self.addon = object.__new__(ReplaceInterceptor)
        self.addon.config = SimpleNamespace(agent_id="test", max_trace_bytes=1024, mode="replace")
        self.addon.protocols = {"json-http": JSON_HTTP_PROTOCOL,
                               "openai-chat-thinking": THINKING_CHAT_PROTOCOL}
        self.addon.secrets = ("synthetic-secret",)
        self.flow = SimpleNamespace(
            request=http.Request.make("POST", "https://target.example/v1/chat/completions", b"{}"),
            response=http.Response.make(200, b"", {"content-type": "text/event-stream"}),
            metadata={"wire": ThinkingChatWire(), "defuzex_started": time.monotonic(),
                      "defuzex_call_id": "call-test", "chunk_index": 0,
                      "defuzex_resolved_route": Route("test", (), (), (), (), "openai-chat-thinking", "test")},
        )
        self.recorded = []
        patcher = patch("defuzex_model_interceptor.observation.events.emit",
                        side_effect=lambda event, **data: self.recorded.append((event, data)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_original_and_converted_evidence_separate_and_redacted(self):
        events = [
            {"choices": [{"index": 0, "delta": {"reasoning_content": "actual synthetic-secret"}}]},
            {"choices": [{"index": 0, "delta": {"content": "answer"}, "finish_reason": "stop"}]},
        ]
        raw = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n"
        self.addon.responseheaders(self.flow)
        converted = self.flow.response.stream(raw)
        self.flow.response.stream(b"")
        result = [data for name, data in self.recorded if name == "llm_response"][0]
        self.assertEqual(result["response_adapter"], "reasoning-content-to-inline-v1")
        self.assertIn("reasoning_content", result["raw_body"])
        self.assertNotIn("</think>", result["raw_body"])
        self.assertIn("</think>", json.dumps(result["client_payload"]))
        self.assertNotIn("synthetic-secret", json.dumps(result))
        self.assertIn(b"</think>", converted)
        self.assertEqual(result["status"], 200)

    def test_stream_failure_does_not_emit_successful_response(self):
        self.addon.responseheaders(self.flow)
        self.flow.response.stream(b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"partial"}}]}\n\n')
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.flow.response.stream(b"")
        self.assertTrue(self.flow.metadata["defuzex_stream_failed"])
        self.assertFalse(any(name == "llm_response" for name, _ in self.recorded))


if __name__ == "__main__":
    unittest.main()
