"""Qwen deployment uses DashScope credentials and matching interception routes."""
import importlib.util
from pathlib import Path
import pytest
from agentbench.runtime.agentcontainer.config import tomllib

ROOT = Path(__file__).resolve().parents[1] / 'resources/agents/18-qwen-code'
spec = importlib.util.spec_from_file_location('qwen_launcher', ROOT / 'bootstrap/launch.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_dashscope_defaults_override_unrelated_native_provider_settings():
    command, env = launcher.prepare({'DASHSCOPE_API_KEY': 'synthetic-qwen-key',
        'GLM_API_KEY': 'synthetic-glm-key', 'OPENAI_API_KEY': 'unrelated',
        'OPENAI_BASE_URL': 'https://example.invalid', 'OPENAI_MODEL': 'other'})
    assert env['OPENAI_API_KEY'] == 'synthetic-qwen-key'
    assert env['OPENAI_BASE_URL'] == 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    assert env['OPENAI_MODEL'] == 'qwen3-coder-plus'
    assert command[-4:] == ['--auth-type', 'openai', '--model', 'qwen3-coder-plus']
    assert 'synthetic-qwen-key' not in ' '.join(command)
    manifest = tomllib.loads((ROOT / 'agent.toml').read_text(encoding='utf-8'))
    assert manifest['runtime']['secret_env_keys'] == ['DASHSCOPE_API_KEY']
    interception = manifest['llm_interception']
    assert interception['credentials'][0]['agent_env'] == 'DASHSCOPE_API_KEY'
    route = interception['routes'][0]
    assert route['host_patterns'] == ['dashscope.aliyuncs.com']
    assert route['path_patterns'] == ['/compatible-mode/v1/chat/completions']


def test_glm_key_does_not_satisfy_qwen_credential_requirement():
    with pytest.raises(ValueError, match='DASHSCOPE_API_KEY is required'):
        launcher.prepare({'GLM_API_KEY': 'synthetic-glm-key'})


def test_model_override_and_blank_defaults():
    _, env = launcher.prepare({'DASHSCOPE_API_KEY': 'synthetic',
        'QWEN_API_BASE_URL': ' ', 'QWEN_MODEL': 'qwen-custom'})
    assert env['OPENAI_MODEL'] == 'qwen-custom'
    assert env['OPENAI_BASE_URL'] == 'https://dashscope.aliyuncs.com/compatible-mode/v1'


@pytest.mark.parametrize('url', ['http://dashscope.aliyuncs.com', 'https://dashscope.aliyuncs.com?key=x'])
def test_rejects_invalid_endpoint(url):
    with pytest.raises(ValueError, match='HTTPS URL without query or fragment'):
        launcher.prepare({'DASHSCOPE_API_KEY': 'synthetic', 'QWEN_API_BASE_URL': url})
