"""Automatic routing keeps explicit endpoints, credentials and failures distinct."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from defuzex_model_interceptor.config import Credential, Route, ServiceConfig
from defuzex_model_interceptor.contracts import SourceSignature
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon
from defuzex_model_interceptor.registry import load_wires
from model.native import NativeJsonWire
from test_auto_routing import config, flow, grpc_flow


class RoutingEdgesTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        capture = patch("defuzex_model_interceptor.observation.events.emit",
                        side_effect=lambda event, **data: self.events.append({"event": event, **data}))
        capture.start()
        self.addCleanup(capture.stop)

    def test_native_protocols_select_the_correct_factory(self):
        settings = config()
        settings = replace(settings, credentials=settings.credentials + (
            Credential("anthropic", "anthropic-api-key", "anthropic-run-token", "target-test-secret"),
            Credential("local", "network-isolated", "unused", "target-test-secret")))
        addon = ModelInterceptorAddon(settings)
        for path, protocol, headers, body in (
            ("/v1/chat/completions", "openai-chat", {"authorization": "Bearer openai-run-token"}, {"messages": []}),
            ("/v1/completions", "openai-completions", {"authorization": "Bearer openai-run-token"}, {"prompt": "Hi"}),
            ("/v1/responses", "openai-responses", {"authorization": "Bearer openai-run-token"}, {"input": "Hi"}),
            ("/v1/embeddings", "openai-embeddings", {"authorization": "Bearer openai-run-token"}, {"input": "Hi"}),
            ("/v1/messages", "anthropic-messages", {"x-api-key": "anthropic-run-token"}, {"messages": []}),
            ("/api/chat", "ollama-chat", {}, {"messages": [{"role": "user", "content": "Hi"}]}),
            ("/api/generate", "ollama-generate", {}, {"prompt": "Hi"}),
        ):
            with self.subTest(protocol=protocol):
                request = flow("https://model.example" + path, json.dumps({"model": "source", **body}).encode(),
                               {"content-type": "application/json; charset=utf-8", **headers})
                addon.request(request)
                self.assertIsNone(request.response)
                self.assertEqual(request.metadata["defuzex_resolved_route"].protocol_plugin, protocol)

    def test_rest_google_query_key_is_consumed_not_forwarded(self):
        addon = ModelInterceptorAddon(config())
        request = flow("https://generativelanguage.googleapis.com/v1beta/models/demo:generateContent?key=google-run-token",
                       b'{"contents":[{"role":"user","parts":[{"text":"Hi"}]}]}',
                       {"content-type": "application/json"})
        addon.request(request)
        self.assertIsNone(request.response)
        self.assertNotIn("key=", request.request.url)
        self.assertNotIn("google-run-token", json.dumps(self.events))

    def test_selects_actual_credential_when_two_use_same_auth_plugin(self):
        settings = config()
        settings = replace(settings, credentials=settings.credentials + (
            Credential("google-alternate", "google-api-key", "alternate-token", "alternate-target-secret"),))
        addon, request = ModelInterceptorAddon(settings), grpc_flow()
        request.request.headers["x-goog-api-key"] = "alternate-token"
        addon.request(request)
        self.assertIsNone(request.response)
        self.assertEqual(request.metadata["defuzex_resolved_route"].credential_id, "google-alternate")
        self.assertEqual(request.request.headers["authorization"], "Bearer alternate-target-secret")
        self.assertNotIn("alternate-target-secret", json.dumps(self.events))

    def test_conversion_failure_does_not_forward_real_credentials_or_mutate_source(self):
        addon, request = ModelInterceptorAddon(config()), grpc_flow()
        request.request.content = b"invalid protobuf envelope"
        addon.request(request)
        self.assertEqual(self.events[-1]["error_code"], "request_preparation_failed")
        self.assertEqual(request.request.host, "generativelanguage.googleapis.com")
        self.assertNotIn("target-test-secret", str(request.request.headers))

    def test_explicit_custom_endpoint_still_selects_its_declared_protocol(self):
        explicit = Route("custom", ("custom.example",), (443,), ("POST",),
                         ("/our-model",), "openai-chat", "openai")
        addon = ModelInterceptorAddon(config((explicit,)))
        request = flow("https://custom.example/our-model", b'{"model":"old","messages":[]}',
                       {"content-type": "application/json", "authorization": "Bearer openai-run-token"})
        addon.request(request)
        self.assertIsNone(request.response)
        self.assertEqual(request.metadata["defuzex_route"], "custom")

    def test_installed_adapter_signature_needs_no_proxy_special_case(self):
        def custom_factory():
            wire = NativeJsonWire("/chat/completions")
            wire.signature = SourceSignature(("/custom/infer",), "bearer-token")
            return wire
        factories = {**load_wires(), "custom-wire": custom_factory}
        with patch("defuzex_model_interceptor.registry.load_wires", return_value=factories), \
             patch("defuzex_model_interceptor.replace.handler.load_wires", return_value=factories):
            addon = ModelInterceptorAddon(config())
        request = flow("https://custom.example/custom/infer", b'{"model":"old","messages":[]}',
                       {"content-type": "application/json", "authorization": "Bearer openai-run-token"})
        addon.request(request)
        self.assertIsNone(request.response)
        self.assertEqual(request.metadata["defuzex_resolved_route"].protocol_plugin, "custom-wire")

    def test_equally_specific_protocols_fail_with_ambiguity_not_arbitrary_selection(self):
        factories = {**load_wires(), "duplicate-chat": lambda: NativeJsonWire("/chat/completions")}
        with patch("defuzex_model_interceptor.replace.handler.load_wires", return_value=factories):
            addon = ModelInterceptorAddon(config())
        request = flow("https://custom.example/v1/chat/completions", b'{}',
                       {"content-type": "application/json", "authorization": "Bearer openai-run-token"})
        addon.request(request)
        self.assertEqual(request.response.status_code, 422)
        self.assertIn("Ambiguous model protocol", self.events[-1]["error"])

    def test_missing_credential_has_authentication_error(self):
        addon, request = ModelInterceptorAddon(replace(config(), credentials=())), grpc_flow()
        addon.request(request)
        self.assertEqual(self.events[-1]["error_code"], "authentication_failed")

    def test_service_json_accepts_omitted_or_empty_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "token"
            token.write_text("test-only")
            raw = {"agent_id": "test", "max_trace_bytes": 4096,
                   "target": {"provider_id": "openrouter", "target_plugin": "openrouter",
                              "base_url": "https://target.example/api/v1", "model": "test/model"},
                   "credentials": [{"id": "google", "auth_plugin": "google-api-key",
                                    "token_file": str(token), "secret_file": str(token)}]}
            path = root / "config.json"
            for routes in (None, []):
                if routes is not None:
                    raw["routes"] = routes
                path.write_text(json.dumps(raw))
                self.assertEqual(ServiceConfig.load(path).routes, ())


if __name__ == "__main__":
    unittest.main()
