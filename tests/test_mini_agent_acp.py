"""Mini-Agent ACP unit: shared-profile config mapping and launcher-side compatibility shims."""
import asyncio
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import stat
import sys
import types

import pytest

from agentbench.adapter.acp.config import ACPConfig
from agentbench.runtime.interception.config import InterceptionConfig
from tests.registered_agents import unit

UNIT = unit("mini-agent")
ENV = {
    "ABB_AGENT_MODEL_API_KEY": "synthetic-key",
    "ABB_AGENT_MODEL_BASE_URL": "https://gateway.example/api/v3/",
    "ABB_AGENT_MODEL": "chosen-model",
    "PATH": "/usr/bin",
}


def load(name):
    spec = spec_from_file_location("mini_agent_" + name, UNIT / "bootstrap" / f"{name}.py")
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_unit_uses_native_acp_command_and_shared_observed_route():
    adapter = ACPConfig.from_agent_dir(UNIT)
    interception = InterceptionConfig.from_agent_dir(UNIT)

    assert adapter.command == ("python", "/opt/agent/bootstrap/launch.py")
    assert adapter.cwd == "/home/agent/workspace"
    assert interception is not None and interception.mode == "observe"
    assert not interception.routes  # Routes are derived from the selected shared provider.


def test_launcher_selects_openai_provider_and_keeps_key_out_of_environment(tmp_path):
    command, environ, document = load("launch").prepare(dict(ENV), tmp_path)

    assert command == ["/opt/mini-agent/bin/python", str(UNIT / "bootstrap/acp_server.py")]
    assert "ABB_AGENT_MODEL_API_KEY" not in environ
    assert environ["HOME"] == str(tmp_path)
    assert environ["TIKTOKEN_CACHE_DIR"] == "/opt/mini-agent-tiktoken"  # Baked into the image.
    assert document["provider"] == "openai"
    assert document["api_base"] == "https://gateway.example/api/v3"
    assert document["model"] == "chosen-model"
    assert document["api_key"] == "synthetic-key"
    assert document["max_steps"] == 100
    assert document["tools"]["enable_mcp"] is True


@pytest.mark.parametrize("name,value,message", [
    ("ABB_AGENT_MODEL_API_KEY", "", "ABB_AGENT_MODEL_API_KEY is required"),
    ("ABB_AGENT_MODEL_BASE_URL", "http://gateway.example/v1", "HTTPS URL"),
    ("ABB_AGENT_MODEL_BASE_URL", "https://gateway.example/v1?x=1", "HTTPS URL"),
    ("ABB_AGENT_MODEL", " ", "ABB_AGENT_MODEL is required"),
])
def test_launcher_rejects_incomplete_profiles(tmp_path, name, value, message):
    with pytest.raises(ValueError, match=message):
        load("launch").prepare({**ENV, name: value}, tmp_path)


def test_config_reproduces_documented_setup_with_private_config(tmp_path):
    module = load("launch")
    source = tmp_path / "source"
    source.mkdir()
    (source / "mcp-example.json").write_text('{"mcpServers": {}}', encoding="utf-8")
    (source / "system_prompt.md").write_text("prompt", encoding="utf-8")
    module.SOURCE_CONFIG = source
    home = tmp_path / "home"
    home.mkdir()
    _, _, document = module.prepare(dict(ENV), home)

    module.write_config(home, document)

    config_dir = home / ".mini-agent/config"
    config = config_dir / "config.yaml"
    assert json.loads(config.read_text(encoding="utf-8")) == document
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert (config_dir / "mcp.json").read_text(encoding="utf-8") == '{"mcpServers": {}}'
    assert (config_dir / "system_prompt.md").read_text(encoding="utf-8") == "prompt"


def test_stream_shim_binds_only_the_acp_writer_to_the_saved_channel(monkeypatch):
    seen = []

    async def upstream():
        seen.append(sys.stdout)
        return "reader", "writer"

    module = types.SimpleNamespace(stdio_streams=upstream)
    channel, logs = io.BytesIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", logs)

    load("acp_server").bind_streams(module, channel)

    assert asyncio.run(module.stdio_streams()) == ("reader", "writer")
    assert seen == [channel]
    assert sys.stdout is logs
