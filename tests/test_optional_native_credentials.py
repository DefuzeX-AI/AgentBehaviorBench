from pathlib import Path
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.adapter.acp.config import ACPConfig


def test_optional_native_credential_is_absent_unless_supplied(tmp_path):
    (tmp_path/'Dockerfile').write_text('FROM scratch')
    (tmp_path/'agent.toml').write_text('''agent_id = "test"
[runtime]
type = "docker"
optional_secret_env_keys = ["MAVIS_ACCESS_TOKEN"]
[build]
context = "."
dockerfile = "Dockerfile"
[launch]
argv = ["python"]
[adapter]
type = "acp"
command = ["native"]
cwd = "/workspace/test"
''')
    for env, expected in (({}, {}), ({'MAVIS_ACCESS_TOKEN':'test-native-login'}, {'MAVIS_ACCESS_TOKEN':'test-native-login'})):
        config=AgentContainerConfig.from_agent_dir(tmp_path,environ=env,secret_resolver=EnvironmentSecretResolver(env))
        assert dict(config.environment)==expected
    assert 'MAVIS_ACCESS_TOKEN' in ACPConfig.from_agent_dir(tmp_path).env_keys
