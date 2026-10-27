"""Deployment contracts for Bitterbot's unchanged native Gateway/ACP entrypoints."""
import importlib.util
from pathlib import Path
import secrets

import pytest

UNIT = Path(__file__).resolve().parents[1] / "resources/agents/141-bitterbot"
spec = importlib.util.spec_from_file_location("bitterbot_abb_launcher", UNIT / "bootstrap/launch.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.parametrize("url", ["http://example.invalid/v1", "https:///v1", "https://example.invalid/v1?key=x", "https://example.invalid/v1#fragment"])
def test_rejects_unsafe_model_endpoint_without_exposing_key(url):
    key = secrets.token_urlsafe(24)
    with pytest.raises(ValueError) as error:
        launcher.model_config({"ABB_AGENT_MODEL_API_KEY": key,
            "ABB_AGENT_MODEL_BASE_URL": url, "ABB_AGENT_MODEL": "test-model"})
    assert key not in str(error.value)


@pytest.mark.parametrize("missing", ["ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"])
def test_missing_model_selection_fails_without_fallback(missing):
    env = {"ABB_AGENT_MODEL_API_KEY": secrets.token_urlsafe(24),
           "ABB_AGENT_MODEL_BASE_URL": "https://example.invalid/v1", "ABB_AGENT_MODEL": "test-model"}
    del env[missing]
    with pytest.raises(ValueError, match=missing):
        launcher.model_config(env)


def test_config_forwards_selection_without_embedding_secrets_or_changing_tools():
    key = secrets.token_urlsafe(24)
    _, url, model = launcher.model_config({"ABB_AGENT_MODEL_API_KEY": key,
        "ABB_AGENT_MODEL_BASE_URL": "https://example.invalid/v1/", "ABB_AGENT_MODEL": "selected-model"})
    config = launcher.gateway_config(url, model, "/case-workspace")
    assert config["agents"]["defaults"]["model"]["primary"] == "abb/selected-model"
    assert config["agents"]["defaults"]["workspace"] == "/case-workspace"
    provider = config["models"]["providers"]["abb"]
    assert provider["baseUrl"] == "https://example.invalid/v1"
    assert provider["apiKey"] == "${ABB_AGENT_MODEL_API_KEY}"
    assert key not in repr(config)
    assert "tools" not in config
    assert config["gateway"]["bind"] == "loopback"
    assert config["browser"]["profiles"]["bitterbot"]["color"] == "#FF4500"


def test_stop_escalates_after_grace_period():
    class Process:
        def __init__(self):
            self.actions = []
        def poll(self):
            return None
        def terminate(self):
            self.actions.append("terminate")
        def wait(self, timeout):
            self.actions.append("wait")
            if self.actions.count("wait") == 1:
                raise launcher.subprocess.TimeoutExpired("gateway", timeout)
        def kill(self):
            self.actions.append("kill")
    proc = Process()
    launcher.stop(proc)
    assert proc.actions == ["terminate", "wait", "kill", "wait"]


def test_bridge_gate_requires_native_gateway_hello_not_acp_start():
    assert not launcher.bridge_connected(b"[acp] ready\n")
    assert not launcher.bridge_connected(b"gateway connect failed\n")
    assert launcher.bridge_connected(b"[acp] gateway reconnected\n")


def test_transport_forwarder_preserves_binary_chunks_and_closes_on_eof():
    import os
    import tempfile
    import threading
    payload = bytes(range(256)) * 1024 + b"\nfinal\x00\xff\n"
    incoming, writer = os.pipe()
    try:
        with tempfile.TemporaryFile("w+b") as output:
            sink = os.fdopen(os.dup(output.fileno()), "wb")
            thread = threading.Thread(target=launcher.forward_bytes, args=(incoming, sink))
            thread.start()
            with os.fdopen(writer, "wb") as source:
                source.write(payload)
            thread.join(timeout=5)
            assert not thread.is_alive()
            assert sink.closed
            output.seek(0)
            assert output.read() == payload
    finally:
        os.close(incoming)


def test_transport_forwarder_exits_on_a_real_broken_pipe():
    import os
    import threading
    incoming, writer = os.pipe()
    peer, outgoing = os.pipe()
    os.close(peer)
    sink = os.fdopen(outgoing, "wb")
    try:
        thread = threading.Thread(target=launcher.forward_bytes, args=(incoming, sink))
        thread.start()
        with os.fdopen(writer, "wb") as source:
            source.write(b"request\n")
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert sink.closed
    finally:
        os.close(incoming)


def test_native_session_keys_are_canonical_and_case_isolated():
    keys = {launcher.native_session_key() for _ in range(32)}
    assert len(keys) == 32
    assert all(key.startswith("agent:main:abb-") for key in keys)
    assert all(len(key.removeprefix("agent:main:abb-")) == 32 for key in keys)
