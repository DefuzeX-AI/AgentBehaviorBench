"""Provider selection follows deployment data and preserves credential isolation."""
from itertools import product
from types import MappingProxyType

import pytest

from agentbench.runtime.contracts.secrets import EnvironmentSecretResolver, MissingSecretError
from agentbench.runtime.interception.config import CredentialConfig, InterceptionConfig, InterceptionConfigurationError
from agentbench.runtime.interception.provider_catalog import DEFAULT_PROVIDER_CATALOG
from agentbench.runtime.interception.providers import resolve_model_provider
from agentbench.runtime.interception.service_config import prepare_service_config


@pytest.mark.parametrize('present', list(product((False, True), repeat=3)))
def test_credential_priority(present):
    names = ('openrouter', 'deepseek', 'glm')
    env = {f'{name.upper()}_API_KEY': 'test-secret' if exists else ' \t'
           for name, exists in zip(names, present)}
    provider = resolve_model_provider(model='chosen-model', environ=env)
    target = provider.resolve(env)
    expected = next((name for name, exists in zip(names, present) if exists), 'openrouter')
    assert target.provider_id == expected
    assert target.credential_env == f'{expected.upper()}_API_KEY'


@pytest.mark.parametrize('name,key,model_var,url_var,url', [
    ('deepseek', 'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
    ('glm', 'GLM_API_KEY', 'GLM_MODEL', 'GLM_API_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4'),
])
def test_direct_provider_config_and_service_credentials(tmp_path, name, key, model_var, url_var, url):
    env = {key: 'upstream-test-secret', model_var: 'configured-model'}
    provider = resolve_model_provider(environ=env)
    target = provider.resolve(env)
    assert (target.provider_id, target.model, target.base_url) == (name, 'configured-model', url)
    assert target.target_plugin == 'compatible-json'
    config = InterceptionConfig(True, 'pem-env', MappingProxyType({}),
        (CredentialConfig('native', 'OPENAI_API_KEY', 'bearer-token'),), ())
    data, agent_env = prepare_service_config(config, agent_id='fixture', max_trace_bytes=4096,
        secret_dir=tmp_path, secret_resolver=EnvironmentSecretResolver(env), environ=env)
    assert (tmp_path / 'target.secret').read_text() == env[key]
    assert data['target']['provider_id'] == name
    assert data['target']['endpoint_paths']['/chat/completions'] == '/chat/completions'
    assert 'upstream-test-secret' not in repr(data)
    assert agent_env['OPENAI_API_KEY'] != env[key]
    override = {**env, url_var: 'https://deployment.example/custom/'}
    assert resolve_model_provider(model='cli-model', environ=override).resolve(override).model == 'cli-model'
    assert provider.resolve(override).base_url == 'https://deployment.example/custom'


def test_explicit_selection_wins_and_does_not_fall_back_on_missing_key():
    env = {'OPENROUTER_API_KEY': 'present', 'GLM_MODEL': 'glm-test', 'ABB_MODEL_PROVIDER': 'glm'}
    target = resolve_model_provider(environ=env).resolve(env)
    assert target.provider_id == 'glm'
    with pytest.raises(MissingSecretError, match='GLM_API_KEY'):
        EnvironmentSecretResolver(env).require(target.credential_env)
    assert resolve_model_provider('deepseek', model='ds-test', environ=env).resolve(env).provider_id == 'deepseek'


def test_missing_model_is_not_a_reason_to_skip_a_configured_key():
    env = {'DEEPSEEK_API_KEY': 'present', 'GLM_API_KEY': 'present', 'GLM_MODEL': 'glm-test'}
    with pytest.raises(InterceptionConfigurationError, match='DEEPSEEK_MODEL'):
        resolve_model_provider(environ=env).resolve(env)


def test_custom_catalog_controls_order_and_new_providers(tmp_path):
    catalog = tmp_path / 'providers.toml'
    catalog.write_text(DEFAULT_PROVIDER_CATALOG.read_text().replace(
        'priority = ["openrouter", "deepseek", "glm"]', 'priority = ["private", "glm", "deepseek", "openrouter"]') + '''
[providers.private]
credential_env = "PRIVATE_KEY"
model_env = "PRIVATE_MODEL"
base_url_env = "PRIVATE_URL"
base_url = "https://private.example/v1"
target_plugin = "compatible-json"
''')
    env = {'ABB_MODEL_PROVIDERS_CONFIG': str(catalog), 'OPENROUTER_API_KEY': 'o',
           'DEEPSEEK_API_KEY': 'd', 'GLM_API_KEY': 'g'}
    assert resolve_model_provider(model='chosen', environ=env).resolve(env).provider_id == 'glm'
    env.update(PRIVATE_KEY='p', PRIVATE_MODEL='private-model')
    target = resolve_model_provider(environ=env).resolve(env)
    assert (target.provider_id, target.credential_env, target.base_url) == (
        'private', 'PRIVATE_KEY', 'https://private.example/v1')


@pytest.mark.parametrize('replacement', [
    'priority = ["missing"]', 'priority = ["glm", "glm"]', 'priority = []',
])
def test_invalid_priority_fails_before_selection(tmp_path, replacement):
    catalog = tmp_path / 'providers.toml'
    catalog.write_text(DEFAULT_PROVIDER_CATALOG.read_text().replace(
        'priority = ["openrouter", "deepseek", "glm"]', replacement))
    with pytest.raises(InterceptionConfigurationError, match='priority'):
        resolve_model_provider(environ={'ABB_MODEL_PROVIDERS_CONFIG': str(catalog)})


@pytest.mark.parametrize('url', ['http://unsafe.example', 'https://user:secret@example.com',
                                 'https://example.com?key=secret', 'https://example.com#fragment'])
def test_invalid_target_urls_do_not_expose_secrets(url):
    env = {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'm', 'DEEPSEEK_BASE_URL': url}
    with pytest.raises(InterceptionConfigurationError) as failure:
        resolve_model_provider(environ=env).resolve(env)
    assert url not in str(failure.value)


def test_suite_configuration_records_selected_provider():
    from types import SimpleNamespace
    from agentbench.cli.sessions.configuration import runner_configuration
    from agentbench.harness.scheduling import RetryPolicy
    factory = SimpleNamespace(model=None, trace_max_bytes=4096,
        environ={'DEEPSEEK_API_KEY': 'test-secret', 'DEEPSEEK_MODEL': 'ds-model'},
        plan=SimpleNamespace(options={}, selection=SimpleNamespace(
            reference=SimpleNamespace(source='directory', name='local'))))
    runner = SimpleNamespace(_runner_factory=factory, retry_policy=RetryPolicy(),
                             concurrency=SimpleNamespace(max_parallel_cases=1))
    result = runner_configuration(runner)
    assert result['model_provider'] == 'deepseek'
    assert result['model'] == 'ds-model'
    assert result['provider_base_url'] == 'https://api.deepseek.com'
    assert 'test-secret' not in repr(result)
    factory.environ = {}
    assert runner_configuration(runner)['model_provider'] is None


@pytest.mark.parametrize('sdk_name', ['kuma', 'local'])
def test_sdk_cli_model_override_applies_to_selected_provider(sdk_name):
    from agentbench.sdk.plugins import evaluation_plan, resolve_sdk
    from agentbench.sdk.runtime import build_evaluation_runner
    runner = build_evaluation_runner(
        evaluation_plan(selection=resolve_sdk(sdk_name)), model='cli-model',
        trace_sink=None, trace_max_bytes=4096,
        environ={'DEEPSEEK_API_KEY': 'test-secret', 'DEEPSEEK_MODEL': 'env-model'})
    target = resolve_model_provider(environ=runner.environ).resolve(runner.environ)
    assert (target.provider_id, target.model) == ('deepseek', 'cli-model')


@pytest.mark.parametrize('provider,protocol,expected_path', [
    ('deepseek', 'openai-chat', '/chat/completions'),
    ('deepseek', 'openai-responses', '/responses'),
    ('deepseek', 'anthropic-messages', '/anthropic/v1/messages'),
    ('glm', 'openai-chat', '/api/paas/v4/chat/completions'),
])
def test_host_catalog_reaches_service_target(tmp_path, monkeypatch, provider, protocol, expected_path):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    service = Path(__file__).resolve().parents[1] / 'agentbench/services/model-interceptor/src'
    monkeypatch.syspath_prepend(str(service))
    from defuzex_model_interceptor.config import _target, Route
    from defuzex_model_interceptor.registry import load_targets
    env = {f'{provider.upper()}_API_KEY': 'test-secret', f'{provider.upper()}_MODEL': 'selected'}
    config = InterceptionConfig(True, 'pem-env', {}, (), ())
    data, _ = prepare_service_config(config, agent_id='fixture', max_trace_bytes=4096,
        secret_dir=tmp_path, secret_resolver=EnvironmentSecretResolver(env), environ=env)
    target = _target(data['target'])
    request = SimpleNamespace(content=b'{"model":"original","stream":true}', headers={})
    result = load_targets()[target.target_plugin].prepare_request(request,
        route=Route('fixture', (), (), (), (), protocol, 'key'), target=target)
    assert request.path == expected_path
    assert json.loads(request.content)['model'] == 'selected'
    assert result.provider_id == provider
