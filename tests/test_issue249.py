"""ACP stdio MCP configuration and credential boundary regressions for issue #249."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from agentbench.adapter.acp.config import ACPConfig, ACPMCPServer

SERVER = Path(__file__).parent / 'acp_fixtures/server.py'
MCP_SERVER = Path(__file__).parent / 'acp_fixtures/mcp_server.py'


def _quote(value):
    return json.dumps(value)


def _entry(*, name='search', command='/opt/agent/search-mcp', args=(), env_keys=(), extra=''):
    lines = [
        '[[adapter.mcp_servers]]',
        f'name = {_quote(name)}',
        f'command = {_quote(command)}',
        f'args = {json.dumps(list(args))}',
        f'env_keys = {json.dumps(list(env_keys))}',
    ]
    if extra:
        lines.append(extra)
    return '\n'.join(lines) + '\n'


def _agent(root, *, server_entries='', adapter_tail='', runtime_keys=()):
    root.mkdir(parents=True, exist_ok=True)
    content = (
        'agent_id = "issue-249-fixture"\n'
        'framework = "acp"\n'
        '[runtime]\n'
        f'env_keys = {json.dumps(list(runtime_keys))}\n'
        '[adapter]\n'
        'type = "acp"\n'
        f'command = {json.dumps([sys.executable, str(SERVER)])}\n'
        f'cwd = {_quote(str(root))}\n'
    )
    if adapter_tail:
        content += adapter_tail.rstrip() + '\n'
    if server_entries:
        content += server_entries
    (root / 'agent.toml').write_text(content)
    return root


def test_stdio_mcp_configuration_is_immutable_and_keeps_values_out_of_manifest(tmp_path):
    root = _agent(tmp_path / 'agent', runtime_keys=('MCP_API_KEY',),
                  server_entries=_entry(name='search', command='/opt/mcp/search',
                                        args=('--root', '/workspace'), env_keys=('MCP_API_KEY',)))

    config = ACPConfig.from_agent_dir(root)

    assert config.mcp_servers == (
        ACPMCPServer('search', '/opt/mcp/search', ('--root', '/workspace'), ('MCP_API_KEY',)),
    )
    assert isinstance(config.mcp_servers, tuple)
    assert 'MCP_API_KEY' in config.env_keys
    assert 'dummy-secret-value' not in repr(config)
    assert 'value =' not in (root / 'agent.toml').read_text()


@pytest.mark.parametrize(('declaration', 'runtime_keys', 'message'), [
    (_entry(command='search-mcp'), (), 'absolute container path'),
    (_entry(command='/opt/mcp/search\x00invalid'), (), 'absolute container path'),
    (_entry(name=''), (), 'non-empty string'),
    (_entry(name='same') + _entry(name='same', command='/opt/mcp/other'), (), 'unique'),
    (_entry(env_keys=('MISSING_TOKEN',)), (), 'undeclared environment key'),
    (_entry(extra='type = "http"'), (), 'HTTP and SSE.*not supported'),
    (_entry(extra='type = "sse"'), (), 'HTTP and SSE.*not supported'),
    (_entry(extra='type = "unknown"'), (), 'type/transport.*not supported'),
    (_entry(extra='transport = "http"'), (), 'HTTP and SSE.*not supported'),
    (_entry(args=('ok',)).replace('args = ["ok"]', 'args = "ok"'), (), 'mcp_servers.args'),
    ('mcp_servers = ["not-a-table"]\n', (), 'entry must be a table'),
    ('[adapter.mcp_servers]\nname = "search"\n', (), 'array of tables'),
])
def test_invalid_mcp_configuration_fails_explicitly(tmp_path, declaration, runtime_keys, message):
    if declaration.startswith('mcp_servers =') or declaration.startswith('[adapter.mcp_servers]'):
        root = _agent(tmp_path / 'agent', adapter_tail=declaration)
    else:
        root = _agent(tmp_path / 'agent', runtime_keys=runtime_keys, server_entries=declaration)

    with pytest.raises(ValueError, match=message):
        ACPConfig.from_agent_dir(root)


def test_unconfigured_units_keep_an_empty_mcp_server_list(tmp_path):
    root = _agent(tmp_path / 'agent')

    assert ACPConfig.from_agent_dir(root).mcp_servers == ()


def test_session_sends_exact_acp_v1_stdio_shape_and_omits_type(tmp_path, monkeypatch):
    pytest.importorskip('acp')
    from agentbench.adapter.acp import ACPAdapter

    token = 'fixture-token-value-1234567890'
    monkeypatch.setenv('MCP_API_KEY', token)
    root = _agent(tmp_path / 'agent', runtime_keys=('MCP_API_KEY',),
                  server_entries=_entry(name='search', command=sys.executable,
                                        args=(str(MCP_SERVER), '--env-key', 'MCP_API_KEY'),
                                        env_keys=('MCP_API_KEY',)))
    adapter = ACPAdapter.from_agent_dir(root)
    try:
        result = adapter.invoke('mcp-shape')
    finally:
        adapter.close()

    assert json.loads(result.output) == [{
        'name': 'search',
        'command': sys.executable,
        'args': [str(MCP_SERVER), '--env-key', 'MCP_API_KEY'],
        'env': [{'name': 'MCP_API_KEY', 'value': token}],
    }]
    assert 'type' not in json.loads(result.output)[0]


def test_stdio_empty_args_and_env_are_present_on_the_wire(tmp_path):
    pytest.importorskip('acp')
    from agentbench.adapter.acp import ACPAdapter

    root = _agent(tmp_path / 'agent', server_entries=(
        '[[adapter.mcp_servers]]\n'
        'name = "echo"\n'
        f'command = {_quote(sys.executable)}\n'
        f'args = {json.dumps([str(MCP_SERVER)])}\n'
    ))
    adapter = ACPAdapter.from_agent_dir(root)
    try:
        result = adapter.invoke('mcp-shape')
    finally:
        adapter.close()

    assert json.loads(result.output) == [{
        'name': 'echo',
        'command': sys.executable,
        'args': [str(MCP_SERVER)],
        'env': [],
    }]


def test_empty_servers_are_still_sent_as_an_empty_list(tmp_path):
    pytest.importorskip('acp')
    from agentbench.adapter.acp import ACPAdapter

    adapter = ACPAdapter.from_agent_dir(_agent(tmp_path / 'agent'))
    try:
        result = adapter.invoke('mcp-shape')
    finally:
        adapter.close()

    assert json.loads(result.output) == []


def test_real_stdio_mcp_server_is_started_and_its_tool_is_called(tmp_path):
    pytest.importorskip('acp')
    from agentbench.adapter.acp import ACPAdapter

    root = _agent(tmp_path / 'agent', server_entries=_entry(
        name='echo', command=sys.executable, args=(str(MCP_SERVER),),
    ))
    adapter = ACPAdapter.from_agent_dir(root)
    try:
        result = adapter.invoke('mcp-call')
    finally:
        adapter.close()

    assert result.output == 'MCP tool invoked'
    assert result.raw_output['stop_reason'] == 'end_turn'


def test_missing_declared_mcp_environment_fails_before_agent_start(tmp_path, monkeypatch):
    pytest.importorskip('acp')
    from agentbench.adapter.acp import ACPAdapter
    from agentbench.adapter.acp.errors import ACPError

    monkeypatch.delenv('MCP_API_KEY', raising=False)
    root = _agent(tmp_path / 'agent', runtime_keys=('MCP_API_KEY',),
                  server_entries=_entry(command=sys.executable,
                                        args=(str(MCP_SERVER), '--env-key', 'MCP_API_KEY'),
                                        env_keys=('MCP_API_KEY',)))
    adapter = ACPAdapter.from_agent_dir(root)
    try:
        with pytest.raises(ACPError, match='requires declared environment key') as raised:
            adapter.invoke('mcp-shape')
    finally:
        adapter.close()

    assert raised.value.code == 'mcp_env_missing'
    assert adapter._session.process is None


def test_agent_invalid_params_rejection_is_an_execution_failure(tmp_path, monkeypatch):
    pytest.importorskip('acp')
    from agentbench.runtime.agentcontainer.worker import execute

    monkeypatch.setenv('ABB_ACP_REJECT_MCP', '1')
    root = _agent(tmp_path / 'agent',
                  adapter_tail='env_keys = ["ABB_ACP_REJECT_MCP"]\n',
                  server_entries=_entry(name='echo', command=sys.executable,
                                        args=(str(MCP_SERVER),)))
    output = tmp_path / 'artifacts'
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({
        'schema': 'abb.invocation.v1',
        'run_id': 'issue-249-invalid-params',
        'session_id': 'issue-249-invalid-params',
        'agent_id': 'issue-249-fixture',
        'framework': 'acp',
        'input': 'mcp-shape',
    }))

    assert asyncio.run(execute(root, request, output)) == 1

    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'failed'
    assert result['error_type']


def test_mcp_environment_echo_is_redacted_from_worker_artifacts(tmp_path, monkeypatch):
    pytest.importorskip('acp')
    from agentbench.runtime.agentcontainer.worker import execute

    key = 'ABB_MCP_TEST_VALUE'
    value = 'nonstandard-fixture-secret-value-12345'
    monkeypatch.setenv(key, value)
    root = _agent(tmp_path / 'agent', runtime_keys=(key,),
                  server_entries=_entry(name='echo', command=sys.executable,
                                        args=(str(MCP_SERVER), '--env-key', key), env_keys=(key,)))
    output = tmp_path / 'artifacts'
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({
        'schema': 'abb.invocation.v1',
        'run_id': 'issue-249-redaction',
        'session_id': 'issue-249-redaction',
        'agent_id': 'issue-249-fixture',
        'framework': 'acp',
        'input': 'mcp-echo',
    }))

    assert asyncio.run(execute(root, request, output)) == 0

    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'succeeded'
    assert result['output'] == '[REDACTED]'
    assert json.loads((output / 'result-redaction.json').read_text())['status'] == 'applied'
    evidence = '\n'.join(path.read_text() for path in output.rglob('*') if path.is_file())
    assert value not in evidence
    assert '[REDACTED]' in evidence


def test_mcp_environment_echo_is_redacted_from_channel_span_transport(tmp_path, monkeypatch):
    pytest.importorskip('acp')
    pytest.importorskip('opentelemetry.sdk')
    from agentbench.runtime.agentcontainer.channel import serve

    key = 'ABB_MCP_TEST_VALUE'
    value = '{{CHANNEL_MCP_SECRET_8df2}}'
    monkeypatch.setenv(key, value)
    root = _agent(tmp_path / 'agent', runtime_keys=(key,),
                  server_entries=_entry(name='echo', command=sys.executable,
                                        args=(str(MCP_SERVER), '--env-key', key), env_keys=(key,)))
    requests = tmp_path / 'requests'
    responses = tmp_path / 'responses'
    requests.mkdir()
    responses.mkdir()

    async def run_channel():
        channel = asyncio.create_task(serve(root=root, requests=requests, responses=responses))
        try:
            (requests / '00000000.json').write_text(json.dumps({
                'schema': 'abb.invocation.v1',
                'run_id': 'issue-249-channel-redaction',
                'session_id': 'issue-249-channel-redaction',
                'agent_id': 'issue-249-fixture',
                'framework': 'acp',
                'input': 'mcp-secret-metadata',
            }))
            await asyncio.wait_for(_wait_for_file(responses / '00000000' / 'done.json'), timeout=15)
            (requests / '00000001.json').write_text(json.dumps({'operation': 'close'}))
            await asyncio.wait_for(channel, timeout=15)
        finally:
            if not channel.done():
                channel.cancel()
                await asyncio.gather(channel, return_exceptions=True)

    asyncio.run(run_channel())

    spans = (responses / '00000000' / 'spans.jsonl').read_text()
    assert value not in spans
    assert '[REDACTED]' in spans


async def _wait_for_file(path):
    while not path.is_file():
        await asyncio.sleep(0.01)


def test_mcp_environment_echo_is_redacted_from_host_observation(tmp_path):
    pytest.importorskip('opentelemetry.sdk')
    from agentbench.observe.host import HostObservation

    value = '{{HOST_MCP_SECRET_7f21}}'
    registration = SimpleNamespace(agent_id='host-fixture', framework='acp')
    sdk_run = SimpleNamespace(run_id='host-issue-249')
    observation = HostObservation(tmp_path / 'observed', registration, sdk_run)

    class Running:
        adapter = SimpleNamespace(observation_secrets=lambda: (value,))

        async def ainvoke(self, _payload, *, run_config):
            for callback in run_config['callbacks']:
                callback.on_acp_event('secret_echo', {'value': value})
            return SimpleNamespace(output=f'echo {value}', raw_output={'value': value})

    test_input = SimpleNamespace(input_id='host-input', payload={'prompt': 'echo'})
    invocation = asyncio.run(observation.invoke(Running(), test_input, {}))
    assert invocation.output == 'echo [REDACTED]'
    assert invocation.raw_output == {'value': '[REDACTED]'}

    files = [path for path in observation.directory.rglob('*') if path.is_file()]
    contents = {path.relative_to(observation.directory).as_posix(): path.read_text() for path in files}
    assert contents['steps/0001/result.json']
    assert 'echo [REDACTED]' in contents['steps/0001/result.json']
    receipt = json.loads(contents['steps/0001/result-redaction.json'])
    assert receipt['status'] == 'applied'
    assert set(receipt['fields']) == {'output', 'raw_output'}
    assert '[REDACTED]' in contents['steps/0001/framework.jsonl']
    assert '[REDACTED]' in contents['steps/0001/acp-events.jsonl']
    assert not any(value in content for content in contents.values())
    assert any('[REDACTED]' in content for name, content in contents.items() if name.startswith('steps/0001/otel'))

    observation.finish(result=SimpleNamespace(
        run_id='host-issue-249', history_count=1,
        report=SimpleNamespace(status='complete', confidence='high',
                               issues=[f'Agent echoed {value}'], evidence_gaps=[]),
    ))
    run_data = (observation.directory / 'run.json').read_text()
    assert value not in run_data
    assert '[REDACTED]' in run_data


def test_host_runner_redacts_mcp_values_from_failure_events_and_errors():
    from agentbench.harness.errors import AgentInvocationError
    from agentbench.harness.runner.benchmark_runner import BenchmarkRunner

    value = '{{HOST_RUNNER_MCP_SECRET_0c52}}'

    class SDKRun:
        run_id = 'host-issue-249-runner'

        def get_input(self, *, full):
            assert full is True
            return SimpleNamespace(input_id='input-1', payload={'prompt': 'echo'})

        def submit(self, **_kwargs):
            return None

    class Observation:
        redaction_secrets = (value,)

        async def invoke(self, *_args):
            raise RuntimeError(f'MCP server echoed {value}')

    failures = []
    with pytest.raises(AgentInvocationError) as raised:
        asyncio.run(BenchmarkRunner(environ={})._drive_inputs(
            SimpleNamespace(agent_id='host-fixture'), SDKRun(),
            SimpleNamespace(adapter_name='acp'), observation=Observation(),
            on_step_failure=lambda _agent, failure: failures.append(failure),
        ))

    assert value not in str(raised.value)
    assert '[REDACTED]' in str(raised.value)
    assert value not in failures[0].error_message
    assert '[REDACTED]' in failures[0].error_message


def test_mcp_values_are_written_to_interceptor_secret_files_not_json(tmp_path):
    from agentbench.runtime.interception.service_config import prepare_service_config

    value = '{{INTERCEPTOR_MCP_SECRET_3921}}'
    interception = SimpleNamespace(
        mode='observe', observation_headers={}, observation_tool_purposes={},
        routes=(), tool_routes=(), token_counting={}, credentials=(),
    )
    data, environment = prepare_service_config(
        interception, agent_id='host-fixture', max_trace_bytes=4096,
        secret_dir=tmp_path, secret_resolver=None, environ={}, redaction_values=(value,),
    )

    assert environment == {}
    assert value not in json.dumps(data)
    assert len(data['redaction_secret_files']) == 1
    secret_file = tmp_path / Path(data['redaction_secret_files'][0]).name
    assert secret_file.read_text() == value


def test_docker_runtime_uses_only_resolved_mcp_values_for_redaction(tmp_path):
    from agentbench.runtime.docker.runtime import _prepare_mcp_redaction_values

    value = '{{DOCKER_MCP_SECRET_b4e9}}'
    root = _agent(tmp_path / 'agent', runtime_keys=('MCP_API_KEY',),
                  server_entries=_entry(env_keys=('MCP_API_KEY',)))
    environment = {'MCP_API_KEY': value, 'UNDECLARED_SECRET': 'must-not-be-forwarded'}
    values = _prepare_mcp_redaction_values(
        SimpleNamespace(framework='acp', path=root), environment,
    )

    assert values == (value,)
    assert environment == {'MCP_API_KEY': value, 'UNDECLARED_SECRET': 'must-not-be-forwarded'}


def test_docker_runtime_rejects_unresolved_mcp_values_before_start(tmp_path):
    from agentbench.runtime.docker.runtime import DockerRuntimeError, _prepare_mcp_redaction_values

    root = _agent(tmp_path / 'agent', runtime_keys=('MCP_API_KEY',),
                  server_entries=_entry(env_keys=('MCP_API_KEY',)))
    with pytest.raises(DockerRuntimeError, match='MCP_API_KEY'):
        _prepare_mcp_redaction_values(SimpleNamespace(framework='acp', path=root), {})
