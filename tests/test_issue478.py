"""Whale must preserve the selected model rather than silently selecting an alias."""
import importlib.util
from pathlib import Path
import tomllib
import pytest

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'resources/agents/135-whale'


def launcher():
    spec = importlib.util.spec_from_file_location('whale_launch', UNIT / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected(**changes):
    return {'ABB_AGENT_MODEL_PROVIDER': 'deepseek', 'ABB_AGENT_MODEL': 'deepseek-v4-pro',
            'ABB_AGENT_MODEL_API_KEY': 'test-key',
            'ABB_AGENT_MODEL_BASE_URL': 'https://api.example.test/v1', **changes}


def test_selected_model_endpoint_and_key_reach_native_server():
    env = launcher().environment(selected(DEEPSEEK_MODEL='deepseek-flash'))
    assert env['WHALE_MODEL'] == 'deepseek-v4-pro'
    assert env['DEEPSEEK_BASE_URL'] == 'https://api.example.test/v1'
    assert env['DEEPSEEK_API_KEY'] == 'test-key'
    assert env['WHALE_API'] == 'auto'


@pytest.mark.parametrize('changes', [
    {'ABB_AGENT_MODEL': 'deepseek-flash'},
    {'ABB_AGENT_MODEL': 'deepseek-v4-flash'},
    {'ABB_AGENT_MODEL_PROVIDER': 'openrouter'},
    {'ABB_AGENT_MODEL_API_KEY': ''},
    {'ABB_AGENT_MODEL_BASE_URL': ''},
])
def test_incompatible_or_incomplete_selection_fails(changes):
    with pytest.raises(ValueError):
        launcher().environment(selected(**changes))


def test_shared_selection_has_no_static_routes_or_secrets():
    data = tomllib.loads((UNIT / 'agent.toml').read_text())
    assert data['model']['provider'] == 'deepseek'
    assert data['model']['source'] == 'native'
    assert data['model']['runtime_configurable'] is True
    assert not data['llm_interception'].get('routes')
    assert not data['llm_interception'].get('credentials')
    assert not data['runtime']['secret_env_keys']
    assert data['source']['method'] == 'git'
    assert len(data['source']['revision']) == 40
    assert data['adapter']['type'] == 'acp'
