"""Issue #52: the evaluation container calls, and may only call, the KUMA Backend that was selected."""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from agentbench.harness.errors import ProviderSelectionError
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts.secrets import EnvironmentSecretResolver
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.plugin.kuma.configuration import DEFAULT_BASE_URL, backend_url
from agentbench.sdk.plugin.kuma.diagnostics import failure_message
from agentbench.sdk.plugin.kuma.image import evaluation_agent
from tests.test_kuma_requirement import unit  # noqa: F401 - pytest fixture

ROOT = Path(__file__).resolve().parents[1]
STAGING = 'https://kuma.staging.example/api/agentdefuze'


@pytest.mark.parametrize('value,expected', [
    (None, DEFAULT_BASE_URL),
    ('', DEFAULT_BASE_URL),
    ('https://defuzex.ai/api/agentdefuze/', DEFAULT_BASE_URL),
    (STAGING + '//', STAGING),
    ('http://host.docker.internal:8000/api/agentdefuze', 'http://host.docker.internal:8000/api/agentdefuze'),
])
def test_backend_url_is_the_override_or_the_default_normalized(value, expected):
    environ = {} if value is None else {'KUMA_BASE_URL': value}
    assert backend_url(environ) == expected


@pytest.mark.parametrize('value', [
    'http://kuma.staging.example/api', 'https://user:pass@kuma.example/api', 'https://kuma.example/api?x=1',
    'https://kuma.example/api#frag', 'ftp://kuma.example/api', 'https://*.example/api', 'https://kuma.example:99999/',
])
def test_unacceptable_overrides_are_rejected_before_any_paid_work(value, tmp_path):
    with pytest.raises(ValueError, match='KUMA_BASE_URL'):
        backend_url({'KUMA_BASE_URL': value})
    registration = NS(path=tmp_path, agent_id='agent')
    (tmp_path / 'requirement.md').write_text('profile')
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'dfx_offline', 'KUMA_BASE_URL': value})
    with pytest.raises(ProviderSelectionError, match='KUMA_BASE_URL'):
        runner.validate_sdk(registration)


def _routes(staged):
    config = InterceptionConfig.from_agent_dir(staged.path)
    return [(tuple(route.host_patterns), tuple(route.path_patterns), tuple(route.methods))
            for route in config.tool_routes]


def _policy(staged):
    import sys
    sys.path.insert(0, str(ROOT / 'agentbench/services/model-interceptor/src'))
    from defuzex_model_interceptor.routing.policy import EgressPolicy
    config = InterceptionConfig.from_agent_dir(staged.path)
    return EgressPolicy(NS(routes=[], tool_routes=[NS(**{
        'host_patterns': route.host_patterns, 'ports': route.ports, 'methods': route.methods,
        'path_patterns': route.path_patterns}) for route in config.tool_routes]))


def _staged_manifest_agent(unit):  # noqa: F811
    toml = 'schema_version = "defuzex-bench.agent.v2"\n' + (unit / 'agent.toml').read_text()
    toml += ('[build]\ncontext = "."\ndockerfile = "Dockerfile"\n'
             '[llm_interception]\ntrust_plugin = "pem-env"\n'
             '[[llm_interception.credentials]]\nid = "model"\nagent_env = "OPENAI_API_KEY"\n'
             'auth_plugin = "bearer-token"\n'
             '[[llm_interception.routes]]\nid = "chat"\ncredential = "model"\nhost_patterns = ["api.openai.com"]\n'
             'ports = [443]\nmethods = ["POST"]\npath_patterns = ["/v1/chat/completions"]\n'
             'protocol_plugin = "openai-chat"\n')
    (unit / 'agent.toml').write_text(toml)
    return NS(path=unit, agent_id='requirement-test', framework='fixture')


def test_selected_backend_is_forwarded_and_is_the_only_backend_route(unit):  # noqa: F811
    agent = _staged_manifest_agent(unit)
    with evaluation_agent(agent, backend=STAGING) as staged:
        routes = _routes(staged)
        policy = _policy(staged)
        environment = AgentContainerConfig.from_agent_dir(
            staged.path, secret_resolver=EnvironmentSecretResolver({}),
            environ={'KUMA_BASE_URL': STAGING, 'KUMA_API_KEY': 'dfx_offline'}).environment
    assert (('kuma.staging.example',), ('/api/agentdefuze',), ('GET', 'POST')) in routes
    assert (('kuma.staging.example',), ('/api/agentdefuze/*',), ('GET', 'POST')) in routes
    assert not any('defuzex.ai' in hosts for hosts, _, _ in routes)
    request = NS(pretty_host='kuma.staging.example', path='/api/agentdefuze/sdk/v2/operations/x/',
                 method='GET', port=443)
    assert policy.permits_tool(request) is True
    assert policy.permits_tool(NS(pretty_host='defuzex.ai', path='/api/agentdefuze/sdk/v2/judge/',
                                  method='POST', port=443)) is False
    assert environment['KUMA_BASE_URL'] == STAGING


def test_default_backend_and_release_check_routes_are_unchanged(unit):  # noqa: F811
    agent = _staged_manifest_agent(unit)
    with evaluation_agent(agent) as staged:
        routes = _routes(staged)
        environment = AgentContainerConfig.from_agent_dir(
            staged.path, secret_resolver=EnvironmentSecretResolver({}), environ={'KUMA_API_KEY': 'dfx'}).environment
    assert routes == [
        (('api.github.com',), ('/repos/DefuzeX-AI/KUMA-DefuzeX/releases/latest',), ('GET',)),
        (('defuzex.ai',), ('/api/agentdefuze',), ('GET', 'POST')),
        (('defuzex.ai',), ('/api/agentdefuze/*',), ('GET', 'POST')),
    ]
    assert 'KUMA_BASE_URL' not in environment


def test_unreachable_backend_during_case_generation_is_named(tmp_path, monkeypatch):
    from agentbench.sdk.common.artifacts import Artifacts
    registration = NS(path=tmp_path / 'agent', case_count=1, agent_id='excelmind')
    registration.path.mkdir()
    (registration.path / 'requirement.md').write_text('profile')
    directory = tmp_path / 'generated'

    def evaluate(agent, **kwargs):
        files = Artifacts(directory, environ={})
        files.save('run.json', {'status': 'failed', 'agent_id': agent.agent_id})
        kwargs['on_artifacts_ready'](directory)
        files.save('evaluation/process.json', {'sdk_base_url': STAGING})
        files.save('evaluation/case-collection.json', {
            'schema': 'abb.case_collection.v2', 'requested_count': 1, 'cases': [], 'selected_case_indices': [0],
            'unattempted_indices': [], 'failures': [{
                'case_index': 0, 'phase': 'case_generation', 'error_type': 'ServiceError',
                'error_message': 'The KUMA service could not be reached.', 'code': 'network_error',
                'retryable': True, 'client_request_id': None, 'request_id': None}]})
        return directory

    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate', evaluate)
    batch = KumaContainerRunner(environ={'KUMA_API_KEY': 'dfx_offline', 'KUMA_BASE_URL': STAGING}
                                ).prepare_case_batch(registration)
    assert batch.failures_by_index[0].error_message == (
        f'The KUMA service could not be reached. (KUMA backend: {STAGING})')


def test_client_side_network_failure_names_the_backend():
    artifacts = {'sdk_error': {'type': 'ServiceError', 'code': 'network_error',
                               'message': 'The KUMA service could not be reached.'},
                 'sdk_base_url': STAGING}
    assert failure_message(artifacts) == ('ServiceError [network_error]: The KUMA service could not be reached.; '
                                          f'KUMA backend: {STAGING}')
