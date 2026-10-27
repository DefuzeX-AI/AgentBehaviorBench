"""AgentCrew launch configuration and protocol isolation regressions."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib


LAUNCH = Path(__file__).resolve().parents[1] / "resources/agents/135-agentcrew/bindings/launch.py"


def launcher():
    spec = importlib.util.spec_from_file_location("agentcrew_launcher", LAUNCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def environment():
    return {"ABB_AGENT_MODEL": "vendor/model", "ABB_AGENT_MODEL_BASE_URL": "https://model.example/v1",
            "ABB_AGENT_MODEL_API_KEY": "test-only-secret"}


def test_native_config_preserves_model_and_prompt(tmp_path):
    module = launcher()
    prompt = 'Native prompt with "quotes", \\paths, and\nnewlines.'
    paths = module.prepare(tmp_path / "private", environment(), ("Engineer", "Native", prompt))
    config_path = Path(paths["AGENTCREW_CONFIG_PATH"])
    provider = json.loads(config_path.read_text())["custom_llm_providers"][0]
    assert config_path.stat().st_mode & 0o777 == 0o600
    assert config_path.parent.stat().st_mode & 0o777 == 0o700
    assert provider["available_models"][0]["id"] == "vendor/model"
    assert provider["default_model_id"] == "vendor/model"
    assert provider["api_key"] == environment()["ABB_AGENT_MODEL_API_KEY"]
    assert paths["AGENTCREW_PROVIDER"] == module.PROVIDER
    assert paths["AGENTCREW_DOCKER"] == "true"
    agent = tomllib.loads(Path(paths["SW_AGENTS_CONFIG"]).read_text())["agents"][0]
    assert agent["system_prompt"] == prompt
    assert agent["tools"] == ["memory", "browser", "web_search", "code_analysis"]


@pytest.mark.parametrize("base", ["http://model.example", "https://user:secret@model.example",
                                  "https://model.example?key=secret", "https://model.example/#secret"])
def test_invalid_url_fails_before_writing(tmp_path, base):
    env = environment()
    env["ABB_AGENT_MODEL_BASE_URL"] = base
    target = tmp_path / "config"
    with pytest.raises(ValueError):
        launcher().prepare(target, env, ("Engineer", "Native", "prompt"))
    assert not target.exists()


def test_protocol_uses_reserved_stream_while_diagnostics_go_to_stderr(tmp_path):
    # A subprocess exercises descriptor-level isolation without changing pytest's stdout.
    # SDK stubs here test only the launcher's stream wiring, never ACP compatibility.
    script = '''
import asyncio, importlib.util, os, sys, types
spec = importlib.util.spec_from_file_location("launcher", sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
sdk = types.ModuleType("acp"); stdio = types.ModuleType("acp.stdio")
core = types.ModuleType("acp.core"); core.DEFAULT_STDIO_BUFFER_LIMIT_BYTES = 50 * 1024 * 1024
async def streams(*, limit):
    assert limit == 50 * 1024 * 1024
    return "reader", sys.stdout
async def native(agent, writer, reader, **kwargs):
    assert reader == "reader" and kwargs["use_unstable_protocol"]
    print("diagnostic")
    os.write(1, b"descriptor diagnostic\\n")
    writer.write('{"jsonrpc":"2.0"}\\n'); writer.flush()
sdk.run_agent = native; stdio.stdio_streams = streams
sys.modules["acp"] = sdk; sys.modules["acp.stdio"] = stdio
sys.modules["acp.core"] = core
with os.fdopen(os.dup(1), "w", buffering=1) as protocol:
    os.dup2(2, 1)
    module.reserve_protocol_output(protocol)
    asyncio.run(sdk.run_agent(None, use_unstable_protocol=True))
'''
    result = subprocess.run([sys.executable, "-c", script, str(LAUNCH)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"jsonrpc": "2.0"}
    assert "diagnostic" in result.stderr
    assert "descriptor diagnostic" in result.stderr
