"""Model protocol recognition does not require per-Agent endpoint declarations."""
import pytest

from agentbench.runtime.interception.config import InterceptionConfig, InterceptionConfigurationError


MANIFEST = '''schema_version = "defuzex-bench.agent.v2"
[llm_interception]
required = true
trust_plugin = "pem-env"
{routes}
[[llm_interception.credentials]]
id = "google"
agent_env = "GEMINI_API_KEY"
auth_plugin = "google-api-key"
'''


@pytest.mark.parametrize("routes", ["", "routes = []"])
def test_manifest_can_omit_model_routes_without_losing_credentials(tmp_path, routes):
    (tmp_path / "agent.toml").write_text(MANIFEST.format(routes=routes))
    config = InterceptionConfig.from_agent_dir(tmp_path)
    assert config.routes == ()
    assert config.credentials[0].agent_env == "GEMINI_API_KEY"


def test_routes_still_reject_wrong_type(tmp_path):
    (tmp_path / "agent.toml").write_text(MANIFEST.format(routes='routes = "wrong"'))
    with pytest.raises(InterceptionConfigurationError, match="routes must be a table array"):
        InterceptionConfig.from_agent_dir(tmp_path)


def test_explicit_route_still_checks_credential_reference(tmp_path):
    manifest = MANIFEST.format(routes="") + '''
[[llm_interception.routes]]
id = "custom"
host_patterns = ["custom.example"]
ports = [443]
methods = ["POST"]
path_patterns = ["/custom/model"]
protocol_plugin = "gemini-grpc"
credential = "missing"
'''
    (tmp_path / "agent.toml").write_text(manifest)
    with pytest.raises(InterceptionConfigurationError, match="unknown credential"):
        InterceptionConfig.from_agent_dir(tmp_path)
