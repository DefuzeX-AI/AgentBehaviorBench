"""Service-backed Agents must retain their native environment in SDK overlays."""

from types import SimpleNamespace
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import pytest

from agentbench.sdk.plugin.kuma.image import evaluation_agent
from agentbench.sdk.plugin.kuma.manifest import extend_runtime_environment


@pytest.mark.parametrize('runtime', [
    '[runtime]\ntype = "docker"\n',
    '[runtime]\ntype = "docker"\nenv_keys = ["DATABASE_HOST"]\n',
    '["runtime"] # service configuration\ntype = "docker"\n"env_keys" = [\n'
    '  "DATABASE_HOST", # native DB\n  "KUMA_API_KEY",\n]\n',
])
def test_overlay_preserves_native_environment_and_other_tables(tmp_path, runtime):
    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'Dockerfile').write_text('FROM python:3.13-slim\nUSER agent\n')
    source = ('agent_id = "service-agent"\n' + runtime +
              'secret_env_keys = ["DATABASE_PASSWORD"]\n'
              '[launch]\nargv = ["python", "native.py"]\n'
              '[other]\nenv_keys = ["KEEP_ME"]\n')
    manifest = root / 'agent.toml'
    manifest.write_text(source)
    with evaluation_agent(SimpleNamespace(path=root, agent_id='service-agent', framework='langgraph')) as staged:
        parsed = tomllib.loads((staged.path / 'agent.toml').read_text())
        keys = parsed['runtime'].get('env_keys', [])
        assert keys == tomllib.loads(source)['runtime'].get('env_keys', [])
        worker_keys = parsed['runtime']['worker_env_keys']
        assert worker_keys.count('KUMA_API_KEY') == worker_keys.count('DEFUZEX_API_KEY') == 1
        if 'DATABASE_HOST' in source:
            assert 'DATABASE_HOST' in keys
        assert parsed['runtime']['secret_env_keys'] == ['DATABASE_PASSWORD']
        assert parsed['other']['env_keys'] == ['KEEP_ME']
        assert parsed['launch']['argv'][-1] == 'agentbench.sdk.plugin.kuma.worker'
    assert manifest.read_text() == source


def test_merge_is_idempotent_and_preserves_environment_string_values():
    source = '[runtime]\nenv_keys = ["value]#not-a-comment", "KUMA_API_KEY"]\n'
    once = extend_runtime_environment(source, ('KUMA_API_KEY', 'DEFUZEX_API_KEY'))
    assert extend_runtime_environment(once, ('KUMA_API_KEY', 'DEFUZEX_API_KEY')) == once
    assert tomllib.loads(once)['runtime']['env_keys'][0] == 'value]#not-a-comment'


@pytest.mark.parametrize('value', ['"DATABASE_HOST"', '[12]', '[""]'])
def test_invalid_environment_list_is_rejected(value):
    with pytest.raises(ValueError, match='runtime.env_keys'):
        extend_runtime_environment('[runtime]\nenv_keys = ' + value, ('KUMA_API_KEY',))


def test_sdk_worker_keys_are_not_declared_agent_subprocess_keys(tmp_path, monkeypatch):
    from agentbench.adapter.acp.config import ACPConfig
    from agentbench.adapter.acp.process import child_environment
    from agentbench.runtime.agentcontainer.config import AgentContainerConfig
    root = tmp_path / 'unit'; (root / 'agent').mkdir(parents=True)
    (root / 'Dockerfile').write_text('FROM python:3.13-slim\nUSER agent\n')
    (root / 'agent.toml').write_text('''agent_id="example"
framework="acp"
[runtime]
type="docker"
env_keys=["NATIVE_SETTING"]
[build]
context="."
dockerfile="Dockerfile"
[launch]
argv = ["python", "worker.py"]
[adapter]
type="acp"
command=["native-acp"]
cwd="/workspace"
''')
    monkeypatch.setenv('KUMA_API_KEY', 'synthetic-sdk-secret')
    monkeypatch.setenv('NATIVE_SETTING', 'value')
    with evaluation_agent(SimpleNamespace(path=root, agent_id='example', framework='acp')) as staged:
        env = child_environment(ACPConfig.from_agent_dir(staged.path))
        assert env['NATIVE_SETTING'] == 'value'
        assert 'KUMA_API_KEY' not in env and 'DEFUZEX_API_KEY' not in env
        worker = AgentContainerConfig.from_agent_dir(staged.path, secret_resolver=None,
            environ={'KUMA_API_KEY': 'synthetic-sdk-secret', 'NATIVE_SETTING': 'value'})
        assert worker.environment['KUMA_API_KEY'] == 'synthetic-sdk-secret'
