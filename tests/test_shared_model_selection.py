"""Public selection, validation, interceptor handoff and resume behavior."""
import json
from dataclasses import replace

import pytest

from agentbench.cli.sessions.model_configuration import agent_model_configuration
from agentbench.harness.registry import AgentRegistration
from agentbench.harness.session.plan import build_plan, validate_provenance, SuiteProvenanceError
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.runtime.interception.native_model import (
    model_declaration, resolve_shared_model, bind_model_routes, KEY_ENV, MODEL_ENV,
)
from agentbench.runtime.interception.providers import ModelTargetConfig, StaticModelTargetProvider
from agentbench.runtime.interception.service_config import prepare_service_config

ENV = {'OPENROUTER_API_KEY': 'synthetic-router-key', 'OPENROUTER_MODEL': 'router-model',
       'DEEPSEEK_API_KEY': 'synthetic-ds-key', 'DEEPSEEK_MODEL': 'ds-model'}
MANIFEST = '''schema_version = "defuzex-bench.agent.v2"
agent_id = "shared"
framework = "acp"
[runtime]
type = "docker"
[build]
context = "."
dockerfile = "Dockerfile"
[launch]
argv = ["python", "worker.py"]
[llm_interception]
trust_plugin = "pem-env"
'''


REPLACEMENT_MANIFEST = MANIFEST.replace('framework = "acp"', 'framework = "langgraph"') + '\ncredentials = [{id="model", agent_env="OPENAI_API_KEY", auth_plugin="bearer-token"}]\n'


@pytest.fixture
def root(tmp_path):
    (tmp_path/'agent.toml').write_text(MANIFEST)
    (tmp_path/'Dockerfile').write_text('FROM scratch')
    return tmp_path


def provenance(root, env, model=None):
    agent = AgentRegistration('shared', root, True, 'ready', 'acp', 'fixture')
    return [agent], {'agent_models': agent_model_configuration([agent], environ=env, model=model)}


@pytest.mark.parametrize('change', [
    {'DEEPSEEK_MODEL': 'unused-change'},
    {'DEEPSEEK_BASE_URL': 'https://unused.example/v1'},
    {'OPENROUTER_API_KEY': 'rotated-key'},
])
def test_unused_settings_and_key_rotation_do_not_change_resume(root, change):
    agents, before = provenance(root, ENV)
    plan = build_plan('shared_model', agents, configuration=before)
    _, after = provenance(root, {**ENV, **change})
    validate_provenance(plan, agents, after)
    assert 'synthetic-router-key' not in json.dumps(plan)
    assert 'synthetic-ds-key' not in json.dumps(plan)


@pytest.mark.parametrize('change', [
    {'OPENROUTER_MODEL': 'changed'},
    {'OPENROUTER_BASE_URL': 'https://changed.example/v1'},
    {'ABB_MODEL_PROVIDER': 'deepseek'},
    {'OPENROUTER_API_KEY': ''},
])
def test_effective_model_url_or_provider_change_rejects_resume(root, change):
    agents, before = provenance(root, ENV)
    plan = build_plan('shared_model', agents, configuration=before)
    _, after = provenance(root, {**ENV, **change})
    with pytest.raises(SuiteProvenanceError):
        validate_provenance(plan, agents, after)


def test_cli_model_matches_container_projection_and_saved_provenance(root):
    _, config = provenance(root, ENV, model='cli-selected')
    runtime = AgentContainerConfig.from_agent_dir(root, environ={**ENV, 'ABB_MODEL': 'cli-selected'},
        secret_resolver=EnvironmentSecretResolver(ENV))
    target = config['agent_models']['shared']['target']
    assert target['model'] == runtime.environment[MODEL_ENV] == 'cli-selected'
    assert target['base_url'] == runtime.model_target.base_url
    assert target['provider_id'] == runtime.model_target.provider_id


def test_observe_service_has_exact_route_no_replacement_or_secret_file(root, tmp_path):
    runtime = AgentContainerConfig.from_agent_dir(root, environ=ENV,
        secret_resolver=EnvironmentSecretResolver(ENV))
    config = bind_model_routes(InterceptionConfig.from_agent_dir(root), runtime.model_target)
    secret_dir = tmp_path/'secrets'
    secret_dir.mkdir()
    data, credentials = prepare_service_config(config, agent_id='shared', max_trace_bytes=4096,
        secret_dir=secret_dir, secret_resolver=EnvironmentSecretResolver(ENV), environ=ENV)
    assert data['mode'] == 'observe'
    assert 'target' not in data and 'targets' not in data
    assert data['routes'][0]['host_patterns'] == ('openrouter.ai',)
    assert data['routes'][0]['path_patterns'] == ('/api/v1/chat/completions',)
    assert credentials == {} and not list(secret_dir.iterdir())
    assert not any(key in json.dumps(data) for key in ('synthetic-router-key', 'synthetic-ds-key'))
    assert runtime.environment[KEY_ENV] == ENV['OPENROUTER_API_KEY']


def test_static_validation_needs_no_model_or_key_but_execution_does(root):
    config = AgentContainerConfig.from_agent_dir(root, environ={}, secret_resolver=None, resolve_model=False)
    assert config.model_target is None
    with pytest.raises(ValueError, match='OPENROUTER_MODEL'):
        AgentContainerConfig.from_agent_dir(root, environ={}, secret_resolver=EnvironmentSecretResolver({}))


def test_native_does_not_resolve_common_provider_even_when_invalid():
    manifest = {'framework': 'acp', 'model': {'provider': 'minimax', 'source': 'native'}}
    assert resolve_shared_model(manifest, {'ABB_MODEL_PROVIDER': 'unknown'}) is None
    assert resolve_shared_model({}, {'ABB_MODEL_PROVIDER': 'unknown'}) is None


@pytest.mark.parametrize('fields', [
    {'source': 'typo'}, {'source': 'native'}, {'provider': ''}, {'provider': 1},
    {'provider': 'deepseek', 'unknown': True}, {'metadata_paths': ['/*']},
])
def test_invalid_model_policy_is_rejected(fields):
    with pytest.raises(ValueError):
        model_declaration({'model': fields, 'framework': 'acp', 'llm_interception': {}})


@pytest.mark.parametrize('field,value', [
    ('environment', {'ABB_AGENT_MODEL': 'override'}),
    ('credentials', [{'agent_env': 'other'}]), ('routes', [{}]),
])
def test_shared_policy_cannot_conflict_with_static_model_settings(field, value):
    with pytest.raises(ValueError, match='remove static overrides'):
        model_declaration({'framework': 'acp',
                           'llm_interception': {field: value}})


@pytest.mark.parametrize('url', [
    'http://example.test/v1', 'https://user:password@example.test/v1',
    'https://example.test/v1?secret=value', 'https://example.test/v1#fragment',
    'https://*.example.test/v1', 'https://example.test/*',
])
def test_invalid_selected_url_fails_without_echoing_it(root, url):
    with pytest.raises(ValueError) as error:
        AgentContainerConfig.from_agent_dir(root, environ={**ENV, 'OPENROUTER_BASE_URL': url},
            secret_resolver=EnvironmentSecretResolver(ENV))
    assert url not in str(error.value)


def test_custom_catalog_endpoint_prefix_and_model_provider_override(root):
    target = ModelTargetConfig('custom', 'compatible-json', 'https://example.test/api',
                              'custom-model', 'CUSTOM_KEY', endpoint_paths={'/chat/completions': '/v2/chat/completions'})
    env = {'CUSTOM_KEY': 'custom-synthetic'}
    config = AgentContainerConfig.from_agent_dir(root, environ=env, secret_resolver=EnvironmentSecretResolver(env),
                                                 model_provider=StaticModelTargetProvider(target))
    assert config.environment[MODEL_ENV] == 'custom-model'
    assert config.model_target.base_url == 'https://example.test/api/v2'


@pytest.mark.parametrize('overrides', [
    {'headers': {'X-Custom': 'value'}}, {'endpoint_paths': {'/messages': '/messages'}},
    {'endpoint_paths': {'/chat/completions': '/nonstandard'}}, {'target_plugin': 'unsupported'},
])
def test_unsupported_native_protocol_options_fail_explicitly(root, overrides):
    from agentbench.runtime.agentcontainer.config import tomllib
    manifest = tomllib.loads((root/'agent.toml').read_text())
    target = ModelTargetConfig('custom', 'compatible-json', 'https://example.test', 'model', 'CUSTOM_KEY')
    with pytest.raises(ValueError):
        resolve_shared_model(manifest, {}, StaticModelTargetProvider(replace(target, **overrides)))


def test_multi_target_routing_cannot_silently_change_shared_native_selection(root):
    with pytest.raises(ValueError, match='multi-target'):
        AgentContainerConfig.from_agent_dir(root, environ={**ENV, 'ABB_MODEL_ROUTING_CONFIG': 'routing.toml'},
            secret_resolver=EnvironmentSecretResolver(ENV))


@pytest.mark.parametrize('framework', ['acp', 'langgraph'])
def test_provider_pin_wins_and_matches_provenance_and_service(root, tmp_path, framework):
    from agentbench.runtime.interception.providers import OpenRouterProvider
    manifest = MANIFEST if framework == 'acp' else REPLACEMENT_MANIFEST
    (root/'agent.toml').write_text(manifest + '\n[model]\nprovider = "deepseek"\n')
    env = {**ENV, 'ABB_MODEL_PROVIDER': 'openrouter'}
    runtime = AgentContainerConfig.from_agent_dir(root, environ=env,
        secret_resolver=EnvironmentSecretResolver(env), model_provider=OpenRouterProvider())
    _, saved = provenance(root, env)
    observed = InterceptionConfig.from_agent_dir(root)
    secrets = tmp_path/'service-secrets'; secrets.mkdir()
    if framework == 'acp':
        target = saved['agent_models']['shared']['target']
        assert runtime.environment[KEY_ENV] == ENV['DEEPSEEK_API_KEY']
        assert runtime.model_target.provider_id == target['provider_id'] == 'deepseek'
        observed = bind_model_routes(observed, runtime.model_target)
    data, _ = prepare_service_config(observed, agent_id='shared', max_trace_bytes=4096,
        secret_dir=secrets, secret_resolver=EnvironmentSecretResolver(env), environ=env,
        model_provider=runtime.replacement_model_provider)
    if framework == 'langgraph':
        target = saved['agent_models']['shared']['routing']['targets']['default']
        assert data['target']['provider_id'] == target['provider_id'] == 'deepseek'
        assert data['target']['model'] == target['model'] == 'ds-model'
        assert (secrets/'target.secret').read_text() == ENV['DEEPSEEK_API_KEY']
        assert not runtime.environment
    else:
        assert data['routes'][0]['host_patterns'] == ('api.deepseek.com',)
    assert env['ABB_MODEL_PROVIDER'] == 'openrouter'


def test_pinned_provider_missing_key_fails_without_using_available_key(root):
    from agentbench.runtime.contracts import MissingSecretError
    (root/'agent.toml').write_text(MANIFEST + '\n[model]\nprovider = "deepseek"\n')
    env = {key: value for key, value in ENV.items() if key != 'DEEPSEEK_API_KEY'}
    with pytest.raises(MissingSecretError, match='DEEPSEEK_API_KEY'):
        AgentContainerConfig.from_agent_dir(root, environ=env, secret_resolver=EnvironmentSecretResolver(env))


def test_pin_ignores_unused_global_provider_and_detects_real_model_changes(root):
    (root/'agent.toml').write_text(MANIFEST + '\n[model]\nprovider = "deepseek"\n')
    agents, before = provenance(root, ENV)
    plan = build_plan('pinned', agents, configuration=before)
    _, after = provenance(root, {**ENV, 'ABB_MODEL_PROVIDER': 'unknown', 'OPENROUTER_MODEL': 'unused'})
    validate_provenance(plan, agents, after)
    _, changed = provenance(root, {**ENV, 'DEEPSEEK_MODEL': 'different'})
    with pytest.raises(SuiteProvenanceError):
        validate_provenance(plan, agents, changed)


def test_mixed_replacement_agents_do_not_share_a_cached_pin(root, tmp_path):
    registrations = []
    for name, policy in [('default', ''), ('pinned', '\n[model]\nprovider = "deepseek"\n')]:
        folder = tmp_path/name; folder.mkdir()
        (folder/'agent.toml').write_text(REPLACEMENT_MANIFEST + policy)
        registrations.append(AgentRegistration(name, folder, True, 'ready', 'langgraph', 'fixture'))
    for order in (registrations, list(reversed(registrations))):
        result = agent_model_configuration(order, environ=ENV, model=None)
        assert result['default']['routing']['targets']['default']['provider_id'] == 'openrouter'
        assert result['pinned']['routing']['targets']['default']['provider_id'] == 'deepseek'


def test_provider_pin_rejects_multi_target_routing():
    from agentbench.runtime.interception.native_model import select_model_provider
    with pytest.raises(ValueError, match='multi-target'):
        select_model_provider({'framework': 'langgraph', 'llm_interception': {},
            'model': {'provider': 'deepseek'}}, {'ABB_MODEL_ROUTING_CONFIG': 'unused.toml'})


@pytest.mark.parametrize('framework', ['acp', 'langgraph'])
def test_pin_preserves_explicit_cli_model_for_local_sdk(root, framework):
    from agentbench.runtime.interception.providers import DeferredModelTargetProvider
    manifest = MANIFEST if framework == 'acp' else REPLACEMENT_MANIFEST
    (root/'agent.toml').write_text(manifest + '\n[model]\nprovider="deepseek"\n')
    runtime = AgentContainerConfig.from_agent_dir(root, environ=ENV,
        secret_resolver=EnvironmentSecretResolver(ENV),
        model_provider=DeferredModelTargetProvider(model='cli-model'))
    target = runtime.model_target if framework == 'acp' else runtime.replacement_model_provider.resolve(ENV)
    assert (target.provider_id, target.model) == ('deepseek', 'cli-model')
    _, saved = provenance(root, ENV, model='cli-model')
    public = saved['agent_models']['shared']
    saved_target = public['target'] if framework == 'acp' else public['routing']['targets']['default']
    assert saved_target['model'] == target.model


def test_registered_units_omit_redundant_model_defaults():
    from pathlib import Path
    from agentbench.runtime.agentcontainer.config import tomllib
    units = Path(__file__).resolve().parents[1]/'resources/agents'
    declarations = {}
    for path in units.glob('*/agent.toml'):
        content = path.read_text(encoding='utf-8')
        manifest = tomllib.loads(content)
        assert '# Model setup:' not in content
        if 'model' in manifest:
            declarations[manifest['agent_id']] = manifest['model']
    assert set(declarations) == {'minimax-code', 'claude-agent-acp', 'qwen-code', 'hermes-agent'}
    assert declarations['hermes-agent'] == {'metadata_paths': ['/models']}
    assert {name: config['provider'] for name, config in declarations.items() if 'provider' in config} == {
        'minimax-code': 'minimax', 'claude-agent-acp': 'codex', 'qwen-code': 'dashscope'}


def test_chat_thinking_changes_replacement_provenance_and_rejects_old_resume(root):
    (root/'agent.toml').write_text(REPLACEMENT_MANIFEST)
    agents, before = provenance(root, ENV)
    plan = build_plan('thinking', agents, configuration=before)
    _, after = provenance(root, {**ENV, 'ABB_CHAT_THINKING': 'disabled'})
    assert after['agent_models']['shared']['routing']['targets']['default']['chat_thinking'] == 'disabled'
    with pytest.raises(SuiteProvenanceError):
        validate_provenance(plan, agents, after)


def test_chat_thinking_cannot_be_silently_ignored_by_native_launcher(root):
    with pytest.raises(ValueError, match='only supported in replacement mode'):
        provenance(root, {**ENV, 'ABB_CHAT_THINKING': 'disabled'})
