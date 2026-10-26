"""OwnPilot runtime configuration and private database lifecycle regressions."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'resources/agents/130-ownpilot'
spec = importlib.util.spec_from_file_location('ownpilot_launch', ROOT / 'bootstrap/launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


@pytest.mark.parametrize('url', ['https://host/api/v3', 'http://interceptor:8000/v1'])
def test_runtime_model_base_paths_remain_native(url):
    env = {'ABB_AGENT_MODEL_API_KEY': 'test-only', 'ABB_AGENT_MODEL': 'selected-model',
           'ABB_AGENT_MODEL_BASE_URL': url}
    assert launch.model_environment(env) == env


@pytest.mark.parametrize('url', ['file:///tmp/key', 'https://user:key@host/v1',
                                'https://host/v1?key=private', 'https://host/#private'])
def test_invalid_model_urls_do_not_echo_values(url):
    with pytest.raises(ValueError) as caught:
        launch.model_environment({'ABB_AGENT_MODEL_API_KEY': 'private',
                                  'ABB_AGENT_MODEL': 'model', 'ABB_AGENT_MODEL_BASE_URL': url})
    assert url not in str(caught.value)
    assert 'private' not in str(caught.value)


def test_missing_configuration_fails_before_startup():
    with pytest.raises(ValueError, match='Missing runtime-owned'):
        launch.model_environment({})


@pytest.mark.parametrize('child_exit', [0, 7])
def test_private_database_shutdown_and_native_child_exit(tmp_path, monkeypatch, child_exit):
    descriptor = tmp_path / 'agent/packages/core/data/providers/abb-runtime.json'
    descriptor.parent.mkdir(parents=True)
    descriptor.write_text((ROOT / 'install/packages/core/data/providers/abb-runtime.json').read_text())
    monkeypatch.setattr(launch, 'ROOT', tmp_path)
    for key, value in {'ABB_AGENT_MODEL_API_KEY': 'test-only', 'ABB_AGENT_MODEL': 'selected',
                       'ABB_AGENT_MODEL_BASE_URL': 'https://host/api/v3/'}.items():
        monkeypatch.setenv(key, value)
    commands = []
    def record(command, env):
        commands.append((command, env.copy()))
    monkeypatch.setattr(launch, 'run', record)
    monkeypatch.setattr(launch.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(launch.subprocess, 'Popen', lambda command, **kw:
                        SimpleNamespace(wait=lambda **kw: child_exit, poll=lambda: child_exit))
    monkeypatch.setattr(launch.subprocess, 'run', lambda command, **kw: record(command, kw['env']))
    assert launch.main() == child_exit
    assert [entry[0][0] for entry in commands] == ['initdb', 'pg_ctl', 'createdb', 'pg_ctl']
    assert commands[-1][0][-1] == 'stop'
    env = commands[0][1]
    assert env['POSTGRES_PASSWORD'] != 'ownpilot_secret'
    assert env['POSTGRES_PASSWORD'] in env['DATABASE_URL']
    assert env['POSTGRES_HOST'] == '127.0.0.1'
    assert json.loads(descriptor.read_text())['baseUrl'] == 'https://host/api/v3'
    assert not Path(commands[0][0][-1]).exists()


def test_native_descriptor_addition_is_reproducible():
    descriptor = json.loads((ROOT / 'install/packages/core/data/providers/abb-runtime.json').read_text())
    assert descriptor['type'] == 'openai-compatible'
    assert descriptor['models'] == []
    assert descriptor['apiKeyEnv'] == 'ABB_AGENT_MODEL_API_KEY'
    from agentbench.runtime.agentcontainer.config import AgentContainerConfig
    from agentbench.runtime.contracts import EnvironmentSecretResolver
    config = AgentContainerConfig.from_agent_dir(ROOT, secret_resolver=EnvironmentSecretResolver({}),
                                                environ={}, resolve_model=False)
    assert config.agent_id == 'ownpilot'
