"""Whale must preserve the selected model rather than silently selecting an alias."""
import importlib.util
from pathlib import Path
import tomllib
import pytest

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'resources/agents/123-whale'


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


def native_manifest():
    return tomllib.loads((UNIT / 'agent.toml').read_text())


def test_native_source_is_preserved_when_configurable():
    from agentbench.runtime.interception.native_model import model_declaration, uses_runtime_model
    assert model_declaration(native_manifest())[0] == 'native'
    assert uses_runtime_model(native_manifest())


@pytest.mark.parametrize('changes', [
    {'runtime_configurable': 'true'}, {'runtime_configurable': 1},
    {'source': None}, {'provider': None}, {'reason': None},
])
def test_capability_requires_explicit_native_contract(changes):
    from agentbench.runtime.interception.native_model import model_declaration
    m = native_manifest()
    for key, value in changes.items():
        if value is None:
            m['model'].pop(key)
        else:
            m['model'][key] = value
    with pytest.raises(ValueError):
        model_declaration(m)


@pytest.mark.parametrize('field,value', [
    ('routes', [{'id': 'static'}]), ('credentials', [{'agent_env': 'KEY'}]),
    ('environment', {'MODEL': 'static'}),
])
def test_native_capability_rejects_static_interception_overrides(field, value):
    from agentbench.runtime.interception.native_model import model_declaration
    m = native_manifest()
    m['llm_interception'][field] = value
    with pytest.raises(ValueError, match='remove static overrides'):
        model_declaration(m)


@pytest.mark.parametrize('field', ['env_keys', 'secret_env_keys', 'optional_secret_env_keys', 'worker_env_keys'])
def test_native_capability_rejects_runtime_owned_inputs(field):
    from agentbench.runtime.interception.native_model import model_declaration
    m = native_manifest()
    m['runtime'][field] = ['ABB_AGENT_MODEL']
    with pytest.raises(ValueError, match='runtime-owned'):
        model_declaration(m)


def test_native_pin_cli_model_environment_routes_and_provenance(tmp_path):
    from agentbench.runtime.contracts import EnvironmentSecretResolver
    from agentbench.runtime.agentcontainer.config import AgentContainerConfig
    from agentbench.runtime.interception.config import InterceptionConfig
    from agentbench.runtime.interception.native_model import bind_model_routes
    from agentbench.runtime.interception.providers import resolve_model_provider
    from agentbench.adapter.acp.config import ACPConfig
    from agentbench.harness.registry import AgentRegistration
    from agentbench.evaluation.model_configuration import agent_model_configuration
    (tmp_path / 'agent.toml').write_text((UNIT / 'agent.toml').read_text().replace('network_config = "network/rules.toml"', ''))
    (tmp_path / 'Dockerfile').write_text('FROM scratch\n')
    env = {'OPENROUTER_API_KEY': 'router-test-key', 'OPENROUTER_MODEL': 'router-model',
           'DEEPSEEK_API_KEY': 'ds-test-key', 'DEEPSEEK_MODEL': 'deepseek-flash',
           'DEEPSEEK_BASE_URL': 'https://api.example.test/v1',
           'ABB_MODEL_PROVIDER': 'openrouter', 'ABB_MODEL': 'deepseek-v4-pro'}
    fallback = resolve_model_provider('openrouter', model='deepseek-v4-pro', environ=env)
    runtime = AgentContainerConfig.from_agent_dir(tmp_path, environ=env,
        secret_resolver=EnvironmentSecretResolver(env), model_provider=fallback)
    native = launcher().environment(runtime.environment)
    assert native['WHALE_MODEL'] == 'deepseek-v4-pro'
    assert native['DEEPSEEK_API_KEY'] == 'ds-test-key'
    assert native['DEEPSEEK_BASE_URL'] == 'https://api.example.test/v1'
    assert {'ABB_AGENT_MODEL', 'ABB_AGENT_MODEL_API_KEY'} <= set(ACPConfig.from_agent_dir(tmp_path).env_keys)
    routes = bind_model_routes(InterceptionConfig.from_agent_dir(tmp_path), runtime.model_target)
    assert routes.mode == 'observe'
    assert routes.routes[0].host_patterns == ('api.example.test',)
    assert routes.routes[0].path_patterns == ('/v1/chat/completions',)
    registration = AgentRegistration('whale', tmp_path, True, 'adapting', 'acp', 'fixture')
    saved = agent_model_configuration([registration], environ=env, model='deepseek-v4-pro')['whale']
    assert saved['model_source'] == 'native'
    assert saved['runtime_configurable'] is True
    assert saved['provider_pin'] == saved['target']['provider_id'] == 'deepseek'
    assert saved['target']['model'] == native['WHALE_MODEL']
    assert 'ds-test-key' not in str(saved) and 'router-test-key' not in str(saved)
    without_key = {k: v for k, v in env.items() if k != 'DEEPSEEK_API_KEY'}
    from agentbench.runtime.contracts.secrets import MissingSecretError
    with pytest.raises(MissingSecretError, match='DEEPSEEK_API_KEY'):
        AgentContainerConfig.from_agent_dir(tmp_path, environ=without_key,
            secret_resolver=EnvironmentSecretResolver(without_key), model_provider=fallback)


def test_existing_native_without_capability_keeps_dedicated_selection():
    from agentbench.runtime.interception.native_model import resolve_shared_model, select_model_provider
    m = native_manifest()
    m['model'].pop('runtime_configurable')
    m['model']['provider'] = 'minimax'
    assert resolve_shared_model(m, {'ABB_MODEL_PROVIDER': 'unknown'}) is None
    fallback = object()
    assert select_model_provider(m, {}, fallback) is fallback


def test_runtime_capability_renders_without_static_credentials(tmp_path):
    from types import SimpleNamespace
    from agentbench.onboarding.build_agent_env.build_toml.rendering import render_manifest
    source = SimpleNamespace(directory=tmp_path, repository='https://github.com/example/native',
                             revision='a' * 40, source_type='github', warnings=())
    facts = {'display_name': 'Native fixture', 'framework': 'acp',
             'adapter': {'command': ['native'], 'cwd': '/workspace', 'input_key': None,
                         'permission_policy': 'deny', 'auth_method': None},
             'env_keys': [], 'secret_env_keys': [], 'models': [], 'tool_routes': [],
             'input_fields': [], 'model': native_manifest()['model']}
    rendered = tomllib.loads(render_manifest(facts, source=source, agent_id='native-fixture'))
    assert rendered['model']['source'] == 'native'
    assert rendered['model']['runtime_configurable'] is True
    assert not rendered['llm_interception']['credentials']
    assert not rendered['llm_interception']['routes']
