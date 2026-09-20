from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import shutil

import pytest

from agentbench.adapter.acp.config import ACPConfig
from agentbench.runtime.interception.config import InterceptionConfig


ROOT = Path(__file__).parents[1]
UNIT = ROOT / "resources/agents/17-claude-agent-acp"


def launch_module():
    spec = spec_from_file_location("claude_agent_acp_launch", UNIT / "bootstrap/launch.py")
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_claude_agent_uses_generic_acp_and_observed_anthropic_route():
    adapter = ACPConfig.from_agent_dir(UNIT)
    interception = InterceptionConfig.from_agent_dir(UNIT)

    assert adapter.command == ("python", "/opt/agent/bootstrap/launch.py")
    assert adapter.cwd == "/home/agent/workspace"
    assert interception is not None and interception.mode == "observe"
    route = next(item for item in interception.routes if item.route_id == "codex-anthropic-messages")
    assert route.host_patterns == ("z.duxiaoman-int.com",)
    assert route.path_patterns == ("/coding/v1/messages",)
    assert route.protocol_plugin == "anthropic-messages"
    metadata = next(item for item in interception.tool_routes if item.purpose == "metadata")
    assert metadata.host_patterns == ("z.duxiaoman-int.com",)
    assert metadata.methods == ("HEAD",)
    assert metadata.path_patterns == ("/coding/api/hello",)
    assert metadata.required is False


def test_launcher_maps_codex_profile_without_persisting_the_key():
    command, environ = launch_module().prepare(
        UNIT,
        {
            "CODEX_API_BASE_URL": "https://z.duxiaoman-int.com/coding/v1",
            "CODEX_MODEL": "gpt-5.5",
            "CODEX_API_KEY": "test-secret",
        },
    )

    assert command == ["node", str(UNIT / "agent/dist/index.js")]
    assert environ["ANTHROPIC_BASE_URL"] == "https://z.duxiaoman-int.com/coding"
    assert environ["ANTHROPIC_MODEL"] == "gpt-5.5"
    assert environ["ANTHROPIC_AUTH_TOKEN"] == "test-secret"
    assert environ["ANTHROPIC_API_KEY"] == ""


@pytest.mark.parametrize(
    "values",
    [
        {"CODEX_API_BASE_URL": "https://z.duxiaoman-int.com/coding/v1", "CODEX_MODEL": "gpt-5.5"},
        {"CODEX_API_BASE_URL": "http://example.test/v1", "CODEX_MODEL": "gpt-5.5", "CODEX_API_KEY": "key"},
        {"CODEX_API_BASE_URL": "https://example.test/api", "CODEX_MODEL": "gpt-5.5", "CODEX_API_KEY": "key"},
    ],
)
def test_launcher_rejects_missing_or_unsafe_profile(values):
    with pytest.raises(ValueError):
        launch_module().prepare(UNIT, values)


def test_interceptor_dns_environment_is_validated_and_rendered():
    from agentbench.runtime.docker.interceptor_policy import InterceptorPolicy

    policy = InterceptorPolicy.from_environment(
        {"ABB_DOCKER_DNS": "172.30.41.252, 172.30.41.254 172.30.41.252"}
    )

    assert policy.dns_servers == ("172.30.41.252", "172.30.41.254")
    assert policy.run_arguments()[-4:] == (
        "--dns",
        "172.30.41.252",
        "--dns",
        "172.30.41.254",
    )


def test_interceptor_dns_environment_rejects_hostnames():
    from agentbench.runtime.docker.interceptor_policy import InterceptorPolicy

    with pytest.raises(ValueError, match="ABB_DOCKER_DNS"):
        InterceptorPolicy.from_environment({"ABB_DOCKER_DNS": "dns.example.com"})


def test_build_patch_waits_for_background_session_title(tmp_path):
    source = tmp_path / "session-titles.ts"
    shutil.copyfile(UNIT / "agent/src/session-titles.ts", source)
    patch = spec_from_file_location("claude_agent_acp_patch", UNIT / "bootstrap/patch_source.py")
    module = module_from_spec(patch)
    assert patch.loader is not None
    patch.loader.exec_module(module)

    module.patch(source)
    transformed = source.read_text()

    assert "await this.requestGenerateTitle(session, fallback);" in transformed
    assert "void this.requestGenerateTitle(session, fallback).catch" not in transformed
    with pytest.raises(RuntimeError, match="expected source block"):
        module.patch(source)
