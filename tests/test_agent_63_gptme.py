"""gptme ACP launcher: shared provider mapping without leaking the key or re-pointing routes."""
import importlib.util

import pytest

from tests.registered_agents import unit

KEY = 'synthetic-selected-key'
BASE = {
    'ABB_AGENT_MODEL_API_KEY': KEY,
    'ABB_AGENT_MODEL_BASE_URL': 'https://api.deepseek.com/',
    'ABB_AGENT_MODEL': 'deepseek-flash',
}


def launcher():
    spec = importlib.util.spec_from_file_location('gptme_launch', unit('gptme') / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_provider_receives_selected_endpoint_and_baked_tiktoken_cache():
    command, env = launcher().prepare(dict(BASE, PATH='/usr/bin'))
    assert command == ['/opt/agent-venv/bin/gptme-acp']
    assert env['GPTME_MODEL'] == 'local/deepseek-flash'
    assert env['OPENAI_BASE_URL'] == 'https://api.deepseek.com'
    assert env['OPENAI_API_KEY'] == KEY
    assert env['TIKTOKEN_CACHE_DIR'] == '/opt/tiktoken-cache'
    assert KEY not in ' '.join(command)


def test_inherited_overrides_cannot_re_point_requests():
    _, env = launcher().prepare(dict(BASE, OPENAI_API_BASE='https://other.invalid/v1',
                                     LLM_PROXY_URL='https://proxy.invalid', LLM_PROXY_API_KEY='x'))
    assert not {'OPENAI_API_BASE', 'LLM_PROXY_URL', 'LLM_PROXY_API_KEY'} & set(env)


@pytest.mark.parametrize('override,message', [
    ({'ABB_AGENT_MODEL_API_KEY': ''}, 'ABB_AGENT_MODEL_API_KEY'),
    ({'ABB_AGENT_MODEL_BASE_URL': 'http://api.deepseek.com'}, 'HTTPS URL'),
    ({'ABB_AGENT_MODEL': 'model with spaces'}, 'unsupported characters'),
])
def test_invalid_selection_is_rejected(override, message):
    with pytest.raises(ValueError, match=message):
        launcher().prepare(dict(BASE, **override))
