"""Issue #68: an upstream transport failure reaches the SDK as a retryable network error.

The production interceptor loader runs in a real ``mitmdump`` with the container's
upstream settings (lazy upstream connection, generated certificates), and a real
KUMA SDK client in a subprocess requests a Backend host that cannot be reached.
Without an explicit decision, mitmproxy answers the client with its own HTML 502
page, which the SDK can only classify as a non-retryable ``invalid_response``.
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("kuma")
pytest.importorskip("mitmproxy")
from defuzex_model_interceptor.proxy import addon as addon_module  # noqa: E402

LOADER = Path(addon_module.__file__).with_name("loader.py")
MITMDUMP = Path(sys.executable).with_name("mitmdump")

CLIENT = r"""
import json
from kuma.transport.backend import BackendClient
client = BackendClient("dfx_" + "a" * 40, base_url="https://kuma.test/api/agentdefuze",
                       timeout=30, max_retries=0)
try:
    client.json("GET", "/sdk/v2/operations/issue68/")
    result = {"outcome": "response"}
except Exception as exc:
    result = {"outcome": type(exc).__name__, "code": getattr(exc, "code", None),
              "retryable": getattr(exc, "retryable", None)}
print(json.dumps(result))
"""


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def interceptor(tmp_path):
    if not MITMDUMP.is_file():
        pytest.skip("mitmdump is not installed next to this interpreter")
    for name in ("run.token", "target.secret"):
        (tmp_path / name).write_text("issue68-" + name)
    config = tmp_path / "interceptor_config.json"
    config.write_text(json.dumps({
        "agent_id": "issue68", "max_trace_bytes": 4096,
        "target": {"provider_id": "openrouter", "target_plugin": "openrouter",
                   "base_url": "https://target.example/api/v1", "model": "test/model", "headers": {}},
        "credentials": [{"id": "openai", "auth_plugin": "bearer-token",
                         "token_file": str(tmp_path / "run.token"),
                         "secret_file": str(tmp_path / "target.secret")}],
        "routes": [],
        "tool_routes": [{"host_patterns": ["kuma.test"], "ports": [443], "methods": ["GET", "POST"],
                         "path_patterns": ["/api/agentdefuze/*"], "purpose": "evaluation"}],
    }))
    confdir = tmp_path / "ca"
    confdir.mkdir()
    port = _free_port()
    log = tmp_path / "mitmdump.log"
    with log.open("w") as stream:
        process = subprocess.Popen(
            [str(MITMDUMP), "--quiet", "--mode", "regular", "--listen-host", "127.0.0.1",
             "--listen-port", str(port), "--set", f"confdir={confdir}",
             "--set", "connection_strategy=lazy", "--set", "upstream_cert=false",
             "--scripts", str(LOADER)],
            stdout=stream, stderr=subprocess.STDOUT,
            env={**os.environ, "DEFUZEX_INTERCEPTOR_CONFIG": str(config)})
    try:
        deadline = time.monotonic() + 30
        while '"interceptor_ready"' not in log.read_text():
            if process.poll() is not None or time.monotonic() > deadline:
                pytest.fail("interceptor did not start:\n" + log.read_text())
            time.sleep(0.1)
        yield port, confdir / "mitmproxy-ca-cert.pem", log
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _events(log, name):
    events = []
    for line in log.read_text().splitlines():
        if line.startswith("DEFUZEX_TRACE "):
            event = json.loads(line[len("DEFUZEX_TRACE "):])
            if event["event"] == name:
                events.append(event)
    return events


def test_unreachable_backend_is_a_retryable_network_error_for_the_sdk(interceptor):
    port, ca, log = interceptor
    proxy = f"http://127.0.0.1:{port}"
    environment = {**os.environ, "HTTPS_PROXY": proxy, "https_proxy": proxy,
                   "NO_PROXY": "", "no_proxy": "", "SSL_CERT_FILE": str(ca),
                   "KUMA_DISABLE_UPDATE_CHECK": "1"}
    completed = subprocess.run([sys.executable, "-c", CLIENT], capture_output=True, text=True,
                               env=environment, timeout=120)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    # Identical to what the SDK decides when it cannot reach the Backend directly.
    assert result == {"outcome": "ServiceError", "code": "network_error", "retryable": True}
    # The interceptor still records the failure as transport evidence.
    errors = _events(log, "tool_error")
    assert [error["error_code"] for error in errors] == ["transport_error"]
    assert errors[0]["source_host"] == "kuma.test"


def _config(tool_routes=()):
    from defuzex_model_interceptor.config import Credential, ServiceConfig, Target
    return ServiceConfig(
        agent_id="issue68", max_trace_bytes=4096,
        target=Target("openrouter", "openrouter", "https://target.example/api/v1", "test/model", {}),
        credentials=(Credential("openai", "bearer-token", "run-token", "target-secret"),),
        routes=(), tool_routes=tool_routes)


def test_blocked_request_envelope_is_a_non_retryable_decision_in_the_client_shape():
    from types import SimpleNamespace
    from unittest.mock import patch
    from mitmproxy import http
    from defuzex_model_interceptor.config import ToolRoute
    from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon

    config = _config((ToolRoute(("kuma.test",), (443,), ("GET",), ("/api/agentdefuze/*",)),))
    flow = SimpleNamespace(request=http.Request.make("GET", "https://elsewhere.test/collect", b"", {}),
                           response=None, metadata={})
    with patch("defuzex_model_interceptor.observation.events.emit"):
        ModelInterceptorAddon(config).request(flow)
    assert flow.response.status_code == 403
    assert json.loads(flow.response.content) == {"error": {
        "code": "egress_denied", "status": 403,
        "message": "Undeclared network request blocked", "retryable": False}}


@pytest.mark.parametrize(("status", "retryable"), [(400, False), (401, False), (404, False),
                                                   (408, True), (429, True), (500, True), (503, True)])
def test_upstream_error_is_retryable_only_when_its_status_says_the_condition_passes(status, retryable):
    from defuzex_model_interceptor.error import ErrorCode
    from defuzex_model_interceptor.proxy.addon import _error_envelope
    envelope = _error_envelope(ErrorCode.UPSTREAM_ERROR, status, "upstream said no")
    assert envelope["error"]["code"] == "upstream_error"
    assert envelope["error"]["retryable"] is retryable
    for decision in (ErrorCode.EGRESS_DENIED, ErrorCode.AUTHENTICATION_FAILED,
                     ErrorCode.REQUEST_PREPARATION_FAILED, ErrorCode.RESPONSE_CONVERSION_FAILED):
        assert _error_envelope(decision, status, "decided")["error"]["retryable"] is False


def test_transport_failure_hook_records_the_error_and_kills_the_flow():
    from unittest.mock import patch
    from mitmproxy import flow as mitm_flow
    from mitmproxy.test import tflow
    from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon

    transport = tflow.tflow()
    transport.metadata.update(defuzex_call_id="call_issue68", abb_tool=True,
                              defuzex_source_host="kuma.test")
    transport.error = mitm_flow.Error("[Errno 110] Connect call failed")
    events = []
    with patch("defuzex_model_interceptor.observation.events.emit",
               side_effect=lambda event, **data: events.append((event, data))):
        ModelInterceptorAddon(_config()).error(transport)
    assert [(event, data["error_code"]) for event, data in events] == [("tool_error", "transport_error")]
    assert events[0][1]["error"] == "[Errno 110] Connect call failed"
    assert transport.error.msg == mitm_flow.Error.KILLED_MESSAGE and transport.response is None


def test_error_in_success_body_does_not_inherit_retryability_from_synthetic_502():
    from types import SimpleNamespace
    from unittest.mock import patch
    from mitmproxy import http
    from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon

    payload = {'error': {'message': 'invalid request', 'retryable': False}}
    flow = SimpleNamespace(
        request=http.Request.make('POST', 'https://model.example/v1/chat/completions', b'{}', {}),
        response=http.Response.make(200, json.dumps(payload).encode(), {'content-type': 'application/json'}),
        metadata={'wire': SimpleNamespace(response=lambda body, status: body),
                  'defuzex_call_id': 'call_application_error', 'defuzex_route': 'chat',
                  'defuzex_resolved_route': SimpleNamespace(protocol_plugin='json-http'),
                  'defuzex_started': time.monotonic()})
    with patch('defuzex_model_interceptor.observation.events.emit'):
        ModelInterceptorAddon(_config()).response(flow)
    assert flow.response.status_code == 502
    assert json.loads(flow.response.content)['error']['code'] == 'upstream_error'
    assert json.loads(flow.response.content)['error']['retryable'] is False
