"""Boundary checks for the outer Blade launcher; no native Agent is started."""
import importlib.util
import asyncio
import json
from pathlib import Path
import shutil

import pytest

PATH = Path(__file__).resolve().parents[1] / "resources/agents/88-blade-code/bootstrap/launch.py"
SPEC = importlib.util.spec_from_file_location("blade_code_abb_launcher", PATH)
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)


def settings(**overrides):
    return {"ABB_AGENT_MODEL_API_KEY": "test-key-not-a-real-credential",
            "ABB_AGENT_MODEL_BASE_URL": "https://provider.example/prefix/v1/",
            "ABB_AGENT_MODEL": "organization/model", **overrides}


@pytest.mark.parametrize("base", ["http://provider.example", "https://user:secret@provider.example",
                                 "https://provider.example?key=secret", ""])
def test_invalid_endpoint_fails_without_echoing_credential(tmp_path, base):
    with pytest.raises(ValueError) as error:
        launch.prepare(settings(ABB_AGENT_MODEL_BASE_URL=base), tmp_path)
    assert "secret" not in str(error.value)


def test_native_channel_uses_runtime_selection_and_secret_reference(tmp_path):
    env = settings()
    before = env.copy()
    command, child, config = launch.prepare(env, tmp_path)
    assert env == before
    model = config["models"][0]
    provider = config["modelProviders"][model["provider"]]
    assert config["currentModelId"] == model["id"]
    assert model["model"] == "organization/model"
    assert provider["baseUrl"] == "https://provider.example/prefix/v1"
    assert provider["wireApi"] == "openai-completions"
    assert child[provider["apiKeyEnv"]] == env["ABB_AGENT_MODEL_API_KEY"]
    assert env["ABB_AGENT_MODEL_API_KEY"] not in json.dumps(config) + " ".join(command)
    assert child["HOME"] == str(tmp_path)
    assert child["BLADE_STORAGE_ROOT"] == str(tmp_path / ".blade")
    assert command == ["node", launch.BRIDGE, launch.BINARY, "--acp"]
    assert "permissionMode" not in config and "tools" not in config


def test_missing_selection_does_not_use_native_model_default(tmp_path):
    env = settings()
    del env["ABB_AGENT_MODEL"]
    with pytest.raises(ValueError, match="ABB_AGENT_MODEL is required"):
        launch.prepare(env, tmp_path)


def test_failed_verification_reaches_real_acp_host_as_explicit_refusal(tmp_path):
    """Exercise SDK framing/metadata without a model, Docker or native Agent."""
    pytest.importorskip("acp", reason="Install the ACP adapter requirements for this boundary test")
    from agentbench.adapter.acp.config import ACPConfig
    from agentbench.adapter.acp.session import ACPSession

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the real ACP relay boundary")
    fixture = Path(__file__).parent / "fixtures/issue513_verification_failure.mjs"
    bridge = PATH.with_name("acp-compat.mjs")
    config = ACPConfig(root=tmp_path, command=(node, str(bridge), node, str(fixture)),
                       cwd=str(tmp_path), timeout=15, handshake_timeout=10)

    async def invoke():
        session = ACPSession(config)
        try:
            return await session.invoke("offline protocol probe", callbacks=[])
        finally:
            await session.close()

    text, raw = asyncio.run(invoke())
    assert text.startswith("Native streamed text remains unchanged.")
    assert "[ABB adapter diagnostic: verification_failed]" in text
    assert "not a verification PASS" in text
    assert raw["stop_reason"] == "refusal"
    failure = raw["prompt_response"]["_meta"]["abb/verificationFailure"]
    assert failure["status"] == "failed"
    assert failure["nativeVerificationEnabled"] is True
    assert failure["nativeError"] == {
        "code": -32603, "message": "Agent turn failed (verification_failed)",
        "data": {"failureType": "verification_failed", "modelId": "offline-model",
                 "outputStarted": True, "toolExecutionStarted": True,
                 "toolCallsCount": 18,
                 "taskFailure": {"reason": "No fresh verification PASS"}},
    }
