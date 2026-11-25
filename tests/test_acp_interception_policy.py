"""The single host switch controls ACP credentials, routing and provenance."""
import json
from types import SimpleNamespace

import pytest

from agentbench.runtime.interception import policy
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.runtime.interception.native_model import bind_model_routes, KEY_ENV
from agentbench.runtime.interception.service_config import prepare_service_config
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.evaluation.model_configuration import agent_model_configuration

MANIFEST = '''schema_version="defuzex-bench.agent.v2"
agent_id="fixture"
framework="acp"
[model]
provider="deepseek"
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
ENV = {'ABB_MODEL_PROVIDER': 'openrouter', 'OPENROUTER_MODEL': 'unused',
       'OPENROUTER_API_KEY': 'unused-secret', 'DEEPSEEK_MODEL': 'chosen',
       'DEEPSEEK_API_KEY': 'test-real-key', 'DEEPSEEK_BASE_URL': 'https://model.example/v1'}


@pytest.mark.parametrize('mode', ['observe', 'replace'])
def test_switch_controls_complete_host_handoff(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(policy, 'ACP_MODEL_MODE', mode)
    (tmp_path / 'agent.toml').write_text(MANIFEST)
    (tmp_path / 'Dockerfile').write_text('FROM scratch')
    resolver = EnvironmentSecretResolver(ENV)
    runtime = AgentContainerConfig.from_agent_dir(tmp_path, environ=ENV, secret_resolver=resolver)
    config = bind_model_routes(InterceptionConfig.from_agent_dir(tmp_path), runtime.model_target)
    secrets = tmp_path / 'secrets'; secrets.mkdir()
    data, tokens = prepare_service_config(config, agent_id='fixture', max_trace_bytes=4096,
        secret_dir=secrets, secret_resolver=resolver, environ=ENV,
        model_provider=runtime.replacement_model_provider)
    assert data['mode'] == mode
    assert data['routes'][0]['host_patterns'] == ('model.example',)
    assert data['routes'][0]['path_patterns'] == ('/v1/chat/completions',)
    assert not config.routes[0].matches(host='other.example', port=443, method='POST', path='/v1/chat/completions')
    agent_env = {**runtime.environment, **tokens}
    assert agent_env['ABB_AGENT_MODEL'] == 'chosen'
    if mode == 'replace':
        assert KEY_ENV not in runtime.environment
        assert agent_env[KEY_ENV] != ENV['DEEPSEEK_API_KEY']
        assert (secrets / 'shared.token').read_text() == agent_env[KEY_ENV]
        assert (secrets / 'target.secret').read_text() == ENV['DEEPSEEK_API_KEY']
        assert data['target']['provider_id'] == 'deepseek'
        assert data['target']['model'] == 'chosen'
        assert data['routes'][0]['credential'] == data['credentials'][0]['id'] == 'shared'
        assert ENV['DEEPSEEK_API_KEY'] not in json.dumps(agent_env)
    else:
        assert agent_env[KEY_ENV] == ENV['DEEPSEEK_API_KEY']
        assert not list(secrets.iterdir())
        assert 'target' not in data
    saved = agent_model_configuration([SimpleNamespace(path=tmp_path, agent_id='fixture')], environ=ENV, model=None)
    assert saved['fixture']['mode'] == mode
    assert saved['fixture']['target']['base_url'] == runtime.model_target.base_url
    assert ENV['DEEPSEEK_API_KEY'] not in json.dumps(saved)


def test_native_exception_and_invalid_switch(tmp_path, monkeypatch):
    (tmp_path/'agent.toml').write_text(MANIFEST.replace('provider="deepseek"', 'provider="deepseek"\nsource="native"'))
    monkeypatch.setattr(policy, 'ACP_MODEL_MODE', 'replace')
    assert InterceptionConfig.from_agent_dir(tmp_path).mode == 'observe'
    (tmp_path/'agent.toml').write_text(MANIFEST)
    monkeypatch.setattr(policy, 'ACP_MODEL_MODE', 'invalid')
    with pytest.raises(ValueError, match='ACP_MODEL_MODE'):
        InterceptionConfig.from_agent_dir(tmp_path)


def test_mode_change_invalidates_resume(tmp_path, monkeypatch):
    from agentbench.harness.registry import AgentRegistration
    from agentbench.harness.session.plan import build_plan, validate_provenance, SuiteProvenanceError
    (tmp_path/'agent.toml').write_text(MANIFEST)
    agents = [AgentRegistration('fixture', tmp_path, True, 'ready', 'acp', 'fixture')]
    monkeypatch.setattr(policy, 'ACP_MODEL_MODE', 'observe')
    before = {'agent_models': agent_model_configuration(agents, environ=ENV, model=None)}
    plan = build_plan('mode_switch', agents, configuration=before)
    monkeypatch.setattr(policy, 'ACP_MODEL_MODE', 'replace')
    after = {'agent_models': agent_model_configuration(agents, environ=ENV, model=None)}
    with pytest.raises(SuiteProvenanceError):
        validate_provenance(plan, agents, after)
