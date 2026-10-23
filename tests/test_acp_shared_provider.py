"""Shared provider selection through the real ACP container and native launchers."""
import importlib.util
import inspect
import json

import pytest

from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.runtime.interception.config import InterceptionConfig
from tests.registered_agents import unit

AGENTS = (
    'opencode', 'kilo-code', 'goose', 'cline', 'kimi-cli', 'pi-coding-agent',
    'copilot-cli', 'openclaw', 'hermes-agent', 'openhands', 'deepagents-code',
    'open-interpreter', 'claurst', 'oh-my-pi', 'kode-cli', 'zeroclaw', 'jcode',
    'mastracode', 'nanocoder', 'mini-agent',
)
from agentbench.adapter.acp.config import ACPConfig
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver, MissingSecretError
from agentbench.runtime.interception.native_model import (
    KEY_ENV, BASE_ENV, MODEL_ENV, PROVIDER_ENV, bind_model_routes,
)

PROVIDERS = (
    ('openrouter', 'OPENROUTER_API_KEY', 'OPENROUTER_MODEL', 'OPENROUTER_BASE_URL',
     'https://openrouter.ai/api/v1', 'openai/gpt-4.1-mini'),
    ('deepseek', 'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'DEEPSEEK_BASE_URL',
     'https://api.deepseek.com', 'deepseek-flash'),
    ('glm', 'GLM_API_KEY', 'GLM_MODEL', 'GLM_API_BASE_URL',
     'https://open.bigmodel.cn/api/paas/v4', 'glm-4.7'),
)
KEY = 'synthetic-selected-key'


def container(agent, env, **kwargs):
    return AgentContainerConfig.from_agent_dir(unit(agent), environ=env,
        secret_resolver=EnvironmentSecretResolver(env), **kwargs)



def launcher(agent):
    spec = importlib.util.spec_from_file_location('shared_' + agent.replace('-', '_'),
                                                unit(agent) / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(agent, env, home):
    module = launcher(agent)
    method = module.validate if agent == 'openclaw' else module.prepare
    parameters = inspect.signature(method).parameters
    extra = {'home': home} if 'home' in parameters else {}
    if 'builtin' in parameters:
        extra['builtin'] = ['openai', 'deepseek', 'glm', 'web']
    return module, method(dict(env), **extra)


def native_config(agent, module, result, home):
    if agent == 'openclaw':
        _, base, model = result
        return module.gateway_config(base, model, 18789, str(home))
    if agent == 'zeroclaw':
        _, base, model = result
        return tomllib.loads(module.config_toml(base, model))
    if agent == 'kilo-code':
        return json.loads((home/'.config/kilo/kilo.json').read_text())
    if agent == 'cline':
        return module.provider_settings(result[2], result[3], result[1]["CLINE_PROVIDER"])
    if agent == 'copilot-cli':
        return {k: v for k, v in result[1].items() if k.startswith('COPILOT_PROVIDER_') or k == 'COPILOT_MODEL'}
    if agent == 'nanocoder':
        return json.loads(result[1]['NANOCODER_PROVIDERS'])
    value = result[2]
    return tomllib.loads(value) if isinstance(value, str) else value


@pytest.mark.parametrize('agent', AGENTS)
@pytest.mark.parametrize('provider,key_name,model_name,base_name,base,model', PROVIDERS)
def test_selected_provider_reaches_native_config_and_exact_observed_route(
        agent, provider, key_name, model_name, base_name, base, model, tmp_path):
    config = container(agent, {key_name: KEY, model_name: model})
    assert config.environment[PROVIDER_ENV] == provider
    assert config.environment[KEY_ENV] == KEY
    assert key_name not in config.environment
    assert set(config.environment) <= set(ACPConfig.from_agent_dir(unit(agent)).env_keys)
    module, result = prepare(agent, config.environment, tmp_path)
    native = native_config(agent, module, result, tmp_path)
    serialized = json.dumps(native)
    assert model in serialized
    assert base in serialized
    if agent not in ('openclaw', 'zeroclaw'):
        assert KEY not in json.dumps(result[0])
    if agent not in ('copilot-cli', 'openhands', 'kode-cli', 'mastracode', 'mini-agent'):
        assert KEY not in serialized
    if agent in ('opencode', 'kilo-code'):
        assert native['model'] == 'abb/' + model
        assert native['provider']['abb']['options']['apiKey'] == '{env:ABB_AGENT_MODEL_API_KEY}'
    if agent == 'cline':
        native_provider = {'openrouter': 'openrouter', 'deepseek': 'deepseek', 'glm': 'zhipuai'}[provider]
        assert native['lastUsedProvider'] == native_provider
        assert native['providers'][native_provider]['settings']['model'] == model
        assert result[1]['CLINE_API_KEY'] == KEY
    if agent == 'hermes-agent':
        assert native['model']['provider'] == 'openai-api'
        assert result[1]['OPENAI_API_KEY'] == KEY
        assert result[1]['OPENAI_BASE_URL'] == base
    if agent == 'kode-cli':
        assert native['primaryProvider'] == 'custom-openai'
    route = bind_model_routes(InterceptionConfig.from_agent_dir(unit(agent)),
                              config.model_target, config.model_metadata_paths)
    from urllib.parse import urlsplit
    parsed = urlsplit(base)
    assert route.mode == 'observe'
    assert not route.credentials  # No fake credential or replacement at the proxy.
    assert len(route.routes) == 1
    assert route.routes[0].matches(host=parsed.hostname, port=443, method='POST',
                                  path=parsed.path + '/chat/completions')
    assert not route.routes[0].matches(host='unselected.invalid', port=443,
                                      method='POST', path=parsed.path + '/chat/completions')


@pytest.mark.parametrize('agent', AGENTS)
def test_all_keys_choose_openrouter_and_only_forward_selected_secret(agent):
    env = {name: ('unselected-' + provider) for provider, name, *_ in PROVIDERS}
    env.update(OPENROUTER_API_KEY=KEY, OPENROUTER_MODEL='selected')
    config = container(agent, env)
    assert config.environment[PROVIDER_ENV] == 'openrouter'
    assert config.environment[KEY_ENV] == KEY
    assert not any(value.startswith('unselected-') for value in config.environment.values())


@pytest.mark.parametrize('agent', AGENTS)
def test_explicit_provider_overrides_priority(agent):
    env = {'OPENROUTER_API_KEY': 'unused', 'DEEPSEEK_API_KEY': KEY,
           'ABB_MODEL_PROVIDER': 'deepseek', 'DEEPSEEK_MODEL': 'chosen'}
    assert container(agent, env).environment[PROVIDER_ENV] == 'deepseek'


@pytest.mark.parametrize('agent', AGENTS)
def test_selected_provider_missing_model_does_not_fall_through(agent):
    with pytest.raises(ValueError, match='OPENROUTER_MODEL'):
        container(agent, {'OPENROUTER_API_KEY': KEY, 'DEEPSEEK_API_KEY': 'other',
                          'DEEPSEEK_MODEL': 'unused'})


@pytest.mark.parametrize('agent', AGENTS)
def test_selected_provider_missing_key_does_not_fall_through(agent):
    with pytest.raises(MissingSecretError, match='DEEPSEEK_API_KEY'):
        container(agent, {'ABB_MODEL_PROVIDER': 'deepseek', 'DEEPSEEK_MODEL': 'chosen',
                          'OPENROUTER_API_KEY': 'unused'})


@pytest.mark.parametrize('agent', AGENTS)
def test_explicit_url_and_model_overrides_reach_launchers(agent, tmp_path):
    config = container(agent, {'DEEPSEEK_API_KEY': KEY, 'DEEPSEEK_MODEL': 'unused',
        'ABB_MODEL': 'custom-model', 'DEEPSEEK_BASE_URL': 'https://gateway.example:8443/custom/v1'})
    if agent == 'cline':
        with pytest.raises(ValueError, match="not in Cline's pinned"):
            prepare(agent, config.environment, tmp_path)
        return
    module, result = prepare(agent, config.environment, tmp_path)
    serialized = json.dumps(native_config(agent, module, result, tmp_path))
    assert 'custom-model' in serialized
    assert 'https://gateway.example:8443/custom/v1' in serialized
    route = bind_model_routes(InterceptionConfig.from_agent_dir(unit(agent)), config.model_target)
    assert route.routes[0].matches(host='gateway.example', port=8443, method='POST',
                                  path='/custom/v1/chat/completions')


@pytest.mark.parametrize('provider,key_name,model_name,base_name,base,model', PROVIDERS)
def test_pi_thinking_settings_follow_selected_service(provider,key_name,model_name,base_name,base,model,tmp_path):
    config = container('pi-coding-agent', {key_name: KEY, model_name: model})
    _, result = prepare('pi-coding-agent', config.environment, tmp_path)
    compat = result[2]['models.json']['providers']['abb']['compat']
    assert compat.get('thinkingFormat') == {'deepseek': 'deepseek', 'glm': 'zai'}.get(provider)
    _, result = prepare('oh-my-pi', config.environment, tmp_path)
    compat = result[2]['models.yml']['providers']['abb']['models'][0]['compat']
    assert compat.get('requiresReasoningContentForToolCalls', False) == (provider == 'deepseek')
    assert 'abb' not in result[2]['config.yml']['disabledProviders']
    assert 'deepseek' in result[2]['config.yml']['disabledProviders']


@pytest.mark.parametrize('provider,key_name,model_name,base_name,base,model', PROVIDERS)
def test_hermes_metadata_route_follows_selected_service(provider,key_name,model_name,base_name,base,model):
    from urllib.parse import urlsplit
    config = container('hermes-agent', {key_name: KEY, model_name: model})
    routes = bind_model_routes(InterceptionConfig.from_agent_dir(unit('hermes-agent')),
                              config.model_target, config.model_metadata_paths)
    metadata = [r for r in routes.tool_routes if r.purpose == 'metadata']
    parsed = urlsplit(base)
    assert len(metadata) == 1
    assert metadata[0].host_patterns == (parsed.hostname,)
    assert metadata[0].methods == ('GET',)
    assert metadata[0].path_patterns == (parsed.path + '/models',)
