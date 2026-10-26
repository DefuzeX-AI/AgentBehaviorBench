"""DotCraft's native configuration must preserve the runtime's selected target."""
import importlib.util
import json
from pathlib import Path
import tomllib
import pytest

UNIT = Path(__file__).resolve().parents[1] / 'resources/agents/127-dotcraft'


def launcher():
    spec = importlib.util.spec_from_file_location('dotcraft_launch', UNIT / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected():
    return {'ABB_AGENT_MODEL_PROVIDER': 'selected-provider', 'ABB_AGENT_MODEL': 'selected-model',
            'ABB_AGENT_MODEL_BASE_URL': 'https://models.example.test/custom/v1',
            'ABB_AGENT_MODEL_API_KEY': 'synthetic-secret'}


def test_selected_target_is_not_replaced_and_secret_is_only_environment_reference():
    source = selected()
    config = launcher().configuration(source)
    assert config['ProviderId'] == source['ABB_AGENT_MODEL_PROVIDER']
    provider = config['Providers'][config['ProviderId']]
    assert provider['Protocol'] == 'openai-chat-completions'
    assert provider['AuthMethod'] == 'apiKey'
    assert provider['EndPoint'] == source['ABB_AGENT_MODEL_BASE_URL']
    assert provider['ApiKey'] == '$DOTCRAFT_API_KEY'
    assert config['ProviderPreferences'][config['ProviderId']]['model'] == source['ABB_AGENT_MODEL']
    assert source['ABB_AGENT_MODEL_API_KEY'] not in json.dumps(config)
    assert set(config) == {'ProviderId', 'Providers', 'ProviderPreferences'}


@pytest.mark.parametrize('missing', list(selected()))
def test_missing_selection_fails_without_secret_diagnostics(missing):
    source = selected()
    source[missing] = ''
    with pytest.raises(ValueError) as error:
        launcher().configuration(source)
    assert 'synthetic-secret' not in str(error.value)


def test_native_setup_and_acp_exec_keep_provider_secret_off_argv(tmp_path, monkeypatch):
    module = launcher()
    monkeypatch.chdir(tmp_path)
    for k, v in selected().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    calls = []
    monkeypatch.setattr(module.subprocess, 'run', lambda argv, **kwargs: calls.append((argv, kwargs)))
    monkeypatch.setattr(module.os, 'execve', lambda path, argv, env: calls.append((argv, env)))
    module.main()
    assert calls[0][0] == ['/opt/dotcraft/dotcraft', 'setup', '--provider-mode', 'skip']
    assert calls[1][0] == ['/opt/dotcraft/dotcraft', 'acp']
    assert calls[1][1]['DOTCRAFT_API_KEY'] == 'synthetic-secret'
    assert 'synthetic-secret' not in str([call[0] for call in calls])
    content = (tmp_path / 'home/.craft/config.json').read_text()
    assert 'synthetic-secret' not in content
    (tmp_path / '.craft').mkdir()
    (tmp_path / '.craft/config.json').write_text('{"unrelated":true}')
    calls.clear()
    module.main()
    assert len(calls) == 1
    assert json.loads((tmp_path / '.craft/config.json').read_text()) == {'unrelated': True}


def test_manifest_uses_native_acp_and_shared_runtime_selection():
    m = tomllib.loads((UNIT / 'agent.toml').read_text())
    assert m['source']['method'] == 'git'
    assert len(m['source']['revision']) == 40
    assert m['framework'] == m['adapter']['type'] == 'acp'
    assert 'model' not in m
    assert not m['llm_interception'].get('routes')
    assert not m['llm_interception'].get('credentials')
    assert not m['runtime']['secret_env_keys']
