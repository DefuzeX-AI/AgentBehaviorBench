"""Default gateway selection and the complete ACP credential/route handoff."""
from pathlib import Path
from types import SimpleNamespace
import json
import pytest

from agentbench.runtime.interception.providers import resolve_model_provider
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.interception.native_model import bind_model_routes
from agentbench.runtime.interception.service_config import prepare_service_config
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.contracts.secrets import MissingSecretError
from agentbench.evaluation.model_configuration import agent_model_configuration

MANIFEST = '''schema_version="defuzex-bench.agent.v2"
agent_id="fixture"
framework="acp"
[runtime]
type="docker"
[build]
context="."
dockerfile="Dockerfile"
[launch]
argv=["python", "worker.py"]
[llm_interception]
trust_plugin="pem-env"
'''


def test_default_does_not_fall_back_to_available_openrouter_key():
    env = {'OPENROUTER_API_KEY': 'unused', 'OPENROUTER_MODEL': 'unused'}
    target = resolve_model_provider(environ=env).resolve(env)
    assert target.provider_id == 'defuze_server'
    with pytest.raises(MissingSecretError, match='KUMA_API_KEY'):
        EnvironmentSecretResolver(env).require(target.credential_env)
    assert resolve_model_provider('openrouter', environ=env).resolve(env).provider_id == 'openrouter'


def test_acp_keeps_client_and_upstream_separate(tmp_path):
    (tmp_path/'agent.toml').write_text(MANIFEST)
    (tmp_path/'Dockerfile').write_text('FROM scratch')
    env = {'KUMA_API_KEY': 'fixture-private-key'}
    resolver = EnvironmentSecretResolver(env)
    runtime = AgentContainerConfig.from_agent_dir(tmp_path, environ=env, secret_resolver=resolver)
    config = bind_model_routes(InterceptionConfig.from_agent_dir(tmp_path), runtime.model_target)
    assert runtime.environment['ABB_AGENT_MODEL'] == 'deepseek-chat'
    assert runtime.environment['ABB_AGENT_MODEL_BASE_URL'] == 'https://api.deepseek.com'
    assert 'ABB_AGENT_MODEL_API_KEY' not in runtime.environment
    secret_dir = tmp_path/'secrets'; secret_dir.mkdir()
    data, tokens = prepare_service_config(config, agent_id='fixture', max_trace_bytes=4096,
        secret_dir=secret_dir, secret_resolver=resolver, environ=env,
        model_provider=runtime.replacement_model_provider)
    assert data['target']['model'] == 'deepseek-flash'
    assert data['target']['base_url'].endswith('/sdk/models/deepseek')
    assert '/responses' in data['target']['endpoint_paths']
    assert {r['protocol_plugin'] for r in data['routes']} == {'openai-chat', 'openai-responses'}
    assert data['routes'][0]['host_patterns'] == ('api.deepseek.com',)
    assert tokens['ABB_AGENT_MODEL_API_KEY'] != env['KUMA_API_KEY']
    assert env['KUMA_API_KEY'] not in json.dumps(data)
    assert (secret_dir/'target.secret').read_text() == env['KUMA_API_KEY']
    agents = [SimpleNamespace(path=tmp_path, agent_id='fixture')]
    before = agent_model_configuration(agents, environ=env, model=None)
    after = agent_model_configuration(agents, environ={**env, 'DEFUZE_CLIENT_MODEL': 'alternate'}, model=None)
    assert before != after
    assert env['KUMA_API_KEY'] not in json.dumps(before)


@pytest.mark.parametrize('value', ['http://example.test', 'https://user:key@example.test',
                                   'https://example.test?key=private', 'https://example.test:bad'])
def test_invalid_origin_fails_without_echoing_credentials(value):
    with pytest.raises(ValueError) as error:
        resolve_model_provider(environ={}).resolve({'KUMA_BASE_URL': value})
    assert value not in str(error.value)


def test_family_and_model_overrides():
    env = {'DEFUZE_MODEL_FAMILY': 'minimax', 'DEFUZE_MODEL': 'override'}
    target = resolve_model_provider(environ=env, model='cli-model').resolve(env)
    assert target.model == 'cli-model'
    assert target.base_url.endswith('/sdk/models/minimax')
    with pytest.raises(ValueError, match='FAMILY'):
        resolve_model_provider(environ={}).resolve({'DEFUZE_MODEL_FAMILY': '../x'})
