"""Undeclared, non-model traffic is handed to the egress observer instead of denied here."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mitmproxy import http

from test_auto_routing import config
from test_observe_mode import native_config
from defuzex_model_interceptor.config import ServiceConfig, ServiceConfigurationError, ToolRoute
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon

OBSERVER = ("defuzex-run-egress-observer", 3128)


def flow(url, content=b"{}", headers=None, method="POST"):
    return SimpleNamespace(request=http.Request.make(method, url, content, headers or {"content-type": "application/json"}),
                           response=None, metadata={}, server_conn=SimpleNamespace(via=None), killable=True,
                           error=None, kill=lambda: None)


class EgressHandoffTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        p = patch("defuzex_model_interceptor.observation.events.emit",
                  side_effect=lambda name, **data: self.events.append({"event": name, **data}))
        p.start()
        self.addCleanup(p.stop)

    def assert_handed_off(self, addon, url):
        request = flow(url)
        request.request.host = "203.0.113.7"  # transparent destination IP
        request.request.headers["host"] = "pypi.org"
        addon.request(request)
        self.assertIsNone(request.response)
        self.assertEqual(request.server_conn.via, ("http", OBSERVER))
        self.assertEqual(request.request.host, "pypi.org")
        self.assertTrue(request.metadata["abb_egress"])
        self.assertNotIn("defuzex_call_id", request.metadata)
        self.assertEqual(self.events, [])
        return request

    def test_observe_mode_hands_undeclared_traffic_to_the_observer(self):
        addon = ModelInterceptorAddon(native_config(egress_proxy=OBSERVER))
        request = self.assert_handed_off(addon, "https://pypi.org/simple/pytest/")
        request.response = http.Response.make(200, b"<html/>", {"content-type": "text/html"})
        addon.responseheaders(request)
        addon.response(request)
        self.assertEqual(self.events, [])

    def test_replace_mode_hands_undeclared_traffic_to_the_observer(self):
        self.assert_handed_off(ModelInterceptorAddon(replace(config(), egress_proxy=OBSERVER)),
                               "https://pypi.org/simple/pytest/")

    def test_observer_refusal_emits_no_model_error_and_is_not_killed(self):
        addon = ModelInterceptorAddon(native_config(egress_proxy=OBSERVER))
        request = self.assert_handed_off(addon, "https://pypi.org/simple/pytest/")
        killed = []
        request.kill = lambda: killed.append(True)
        request.error = SimpleNamespace(msg="upstream proxy refused: 403 Forbidden")
        addon.error(request)
        self.assertEqual(self.events, [])
        self.assertEqual(killed, [])

    def test_model_and_tool_routes_are_never_handed_off(self):
        rule = ToolRoute(("native.example",), (443,), ("POST",), ("/review",), "content_safety")
        addon = ModelInterceptorAddon(native_config(egress_proxy=OBSERVER, tool_routes=(rule,)))
        for url, name in (("https://native.example/v1/messages", "llm_request"),
                          ("https://native.example/review", "tool_request")):
            with self.subTest(url=url):
                request = flow(url, b'{"model":"m","messages":[]}')
                addon.request(request)
                self.assertIsNone(request.server_conn.via)
                self.assertNotIn("abb_egress", request.metadata)
                self.assertEqual(self.events[-1]["event"], name)

    def test_without_an_observer_undeclared_traffic_is_still_denied_here(self):
        addon = ModelInterceptorAddon(native_config())
        request = flow("https://pypi.org/simple/pytest/")
        addon.request(request)
        self.assertEqual(request.response.status_code, 403)
        self.assertEqual(self.events[-1]["error_code"], "egress_denied")
        self.assertIsNone(request.server_conn.via)


class EgressProxyConfigTest(unittest.TestCase):
    def load(self, **extra):
        data = {"agent_id": "a", "max_trace_bytes": 4096, "mode": "observe", "routes": [], **extra}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return ServiceConfig.load(path)

    def test_egress_proxy_is_optional_and_validated(self):
        self.assertIsNone(self.load().egress_proxy)
        self.assertEqual(self.load(egress_proxy={"host": "observer", "port": 3128}).egress_proxy,
                         ("observer", 3128))
        for value in ({"host": "observer"}, {"host": "", "port": 3128}, {"host": "o", "port": 0}, "o:3128"):
            with self.subTest(value=value), self.assertRaises(ServiceConfigurationError):
                self.load(egress_proxy=value)


if __name__ == "__main__":
    unittest.main()
