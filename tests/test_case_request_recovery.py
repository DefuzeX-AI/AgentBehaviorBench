"""Recover original Judge Attempts without repeating Agent or paid Judge POSTs."""
import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from agentbench.harness.result import CaseResult
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.case_identity import case_content_sha256
from agentbench.sdk.contracts import PreparedCase
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts
from agentbench.sdk.plugin.kuma.recovery import AUTOMATIC_RETRY_BLOCKED, classify_failure
from tests.test_kuma_pypi import write_completed_case


@pytest.fixture
def attempt(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma import recovery_execution
    root = tmp_path / 'agent'
    root.mkdir()
    (root / 'requirement.md').write_text('Test Agent')
    agent = SimpleNamespace(path=root, case_count=1, agent_id='agent')
    content = {'case_id': 'case-one', 'inputs': [
        {'input_id': 'input-1', 'payload_type': 'text', 'payload': 'question'}]}
    source = tmp_path / 'case.json'
    source.write_text(json.dumps({'schema_version': 'kuma.case_artifact.v1', 'case': content}))
    case = PreparedCase(0, content['case_id'], source, case_content_sha256(content),
                        hashlib.sha256(source.read_bytes()).hexdigest())
    directory = tmp_path / 'original'
    write_completed_case(directory, agent.agent_id, content)
    files = Artifacts(directory, environ={})
    host = json.loads((directory / 'run.json').read_text())
    host.update(status='failed', case_id=case.case_id, attempt_id='attempt-one',
                cleanup_status='succeeded', host_trace_validation='succeeded')
    files.save('run.json', host)
    report_path = directory / 'evaluation/judge/report.json'
    report = json.loads(report_path.read_text())
    report['status'] = 'issue'
    report_path.unlink()
    request = {'client_request_id': 'kreq_' + 'a' * 32, 'request_type': 'judgment',
               'status': 'running', 'run_id': report['run_id'], 'case_id': case.case_id,
               'operation_id': 'original-operation'}
    summary = json.loads((directory / 'evaluation/manifest.json').read_text())
    summary.update(phase='judge', judge='failed', request=request, error={
        'type': 'KumaTimeoutError', 'code': 'network_error', 'retryable': True,
        'client_request_id': request['client_request_id'], 'message': 'Interrupted wait'})
    files.save('evaluation/manifest.json', summary)
    files.save('evaluation/process.json', {'sdk_base_url': 'https://sdk.example'})
    (directory / 'sdk-repo').mkdir()
    previous = CaseResult(agent.agent_id, 0, 'job', 'failed', case_id=case.case_id,
                          error_type='RecoveryRequired', error_message='Interrupted',
                          artifacts={'directory': str(directory)}, attempt_id='attempt-one')
    calls = []
    monkeypatch.setattr(recovery_execution, 'inspect_requests', lambda *a: request)

    def resume(repo, client_id, **kwargs):
        calls.append((repo, client_id, kwargs))
        request['status'] = 'succeeded'
        return {'request': dict(request), 'report': report, 'host_accepted': False}

    monkeypatch.setattr(recovery_execution, 'recover_request', resume)
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate',
                        lambda *a, **kw: pytest.fail('Recovery cannot execute Agent or CaseGen'))
    return SimpleNamespace(agent=agent, case=case, directory=directory, files=files, host=host,
                           summary=summary, request=request, report=report, previous=previous,
                           calls=calls, runner=KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}))


def test_judge_recovery_preserves_original_attempt_and_validates_every_input(attempt):
    result = attempt.runner.recover_case(attempt.agent, attempt.case, previous_result=attempt.previous)
    assert result.run_id == attempt.report['run_id']
    assert result.report.status == 'issue'
    assert result.steps[0].invocation.output == 'question'
    assert len(attempt.calls) == 1
    assert attempt.calls[0][0] == attempt.directory / 'sdk-repo'
    assert attempt.calls[0][1] == attempt.request['client_request_id']
    host = json.loads((attempt.directory / 'run.json').read_text())
    assert host['attempt_id'] == 'attempt-one' and host['status'] == 'succeeded'
    before, = attempt.directory.glob('evaluation/recovery/*/before.json')
    assert json.loads(before.read_text())['manifest']['error']['code'] == 'network_error'


@pytest.mark.parametrize('field,value', [('cleanup_status', 'failed'), ('host_trace_validation', 'not_performed')])
def test_recovery_refuses_without_original_cleanup_and_host_acceptance(attempt, field, value):
    attempt.files.save('run.json', {**attempt.host, field: value})
    with pytest.raises(RuntimeError, match='cleanup and host trace') as error:
        attempt.runner.recover_case(attempt.agent, attempt.case, previous_result=attempt.previous)
    assert not attempt.calls
    assert error.value.artifacts['recovery']['action'] == 'blocked'


def test_stale_pending_snapshot_cannot_reopen_terminal_failed_request(attempt):
    attempt.request['status'] = 'failed'
    with pytest.raises(RuntimeError, match='terminally failed'):
        attempt.runner.recover_case(attempt.agent, attempt.case, previous_result=attempt.previous)
    assert not attempt.calls
    summary = json.loads((attempt.directory / 'evaluation/manifest.json').read_text())
    assert summary['request']['status'] == 'failed'


def test_finished_attempt_is_reconciled_without_any_sdk_io(attempt, monkeypatch):
    attempt.files.save('evaluation/judge/report.json', attempt.report)
    attempt.files.save('evaluation/manifest.json', {**attempt.summary, 'phase': 'finished', 'judge': 'received'})
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.recovery_execution.inspect_requests',
                        lambda *a: pytest.fail('Already finished report needs no SDK I/O'))
    result = attempt.runner.recover_case(attempt.agent, attempt.case, previous_result=attempt.previous)
    assert result.run_id == attempt.report['run_id']
    assert not attempt.calls


def test_request_identity_mismatch_refuses_before_network(attempt):
    attempt.request['run_id'] = 'other-run'
    with pytest.raises(ValueError, match='original Judge identity'):
        attempt.runner.recover_case(attempt.agent, attempt.case, previous_result=attempt.previous)
    assert not attempt.calls


def test_recovered_report_does_not_bypass_original_input_validation(attempt):
    path = attempt.directory / 'evaluation/inputs/0001/result.json'
    result = json.loads(path.read_text())
    result['output'] = 'different output'
    path.write_text(json.dumps(result))
    with pytest.raises(RuntimeError, match='submission identity mismatch') as error:
        attempt.runner.recover_case(attempt.agent, attempt.case, previous_result=attempt.previous)
    assert len(attempt.calls) == 1
    assert not (attempt.directory / 'evaluation/judge/report.json').exists()
    assert list(attempt.directory.glob('evaluation/recovery/*/report.json'))
    assert json.loads((attempt.directory / 'run.json').read_text())['status'] == 'failed'
    assert error.value.artifacts['recovery']['action'] == 'blocked'


def test_new_authentication_failure_overrides_old_retryable_timeout(attempt, monkeypatch):
    from kuma.errors import AuthenticationError

    def rejected(*args, **kwargs):
        raise AuthenticationError('Invalid credential', code='invalid_api_key')

    monkeypatch.setattr('agentbench.sdk.plugin.kuma.recovery_execution.recover_request', rejected)
    with pytest.raises(AuthenticationError) as error:
        attempt.runner.recover_case(attempt.agent, attempt.case, previous_result=attempt.previous)
    assert error.value.artifacts['sdk_error']['code'] == 'invalid_api_key'
    assert error.value.artifacts['recovery']['action'] == 'blocked'


@pytest.mark.parametrize('code', sorted(AUTOMATIC_RETRY_BLOCKED))
def test_sdk_retry_prohibition_wins_over_retryable_flag(attempt, code):
    artifacts = collect_artifacts(attempt.directory, attempt.host, environ={})
    assert classify_failure(artifacts)['action'] == 'resume_request'
    artifacts['sdk_error'].update(code=code, retryable=True)
    assert classify_failure(artifacts)['action'] == 'blocked'


@pytest.mark.parametrize('declared', [False, True])
def test_transient_agent_failure_requires_explicit_replay_declaration(attempt, declared):
    (attempt.agent.path / 'agent.toml').write_text(f'[evaluation]\nreplay_safe = {str(declared).lower()}\n')
    assert attempt.runner.recovery_capabilities(attempt.agent).safe_case_replay is declared
    artifacts = {
        'safe_case_replay': declared, 'phase': 'execution', 'cleanup_status': 'succeeded',
        'completion': {'execution': 'failed'},
        'native_failure': {'error_type': 'ReadTimeout', 'status': 'failed'},
    }
    assert classify_failure(artifacts)['action'] == ('replay_case' if declared else 'blocked')
    artifacts['sdk_error'] = {'code': 'model_invalid_result', 'retryable': True}
    assert classify_failure(artifacts)['action'] == 'blocked'


@pytest.mark.parametrize('declaration', ['"true"', '1', '[]'])
def test_replay_declaration_requires_boolean(attempt, declaration):
    (attempt.agent.path / 'agent.toml').write_text(f'[evaluation]\nreplay_safe = {declaration}\n')
    with pytest.raises(ValueError, match='must be a boolean'):
        attempt.runner.recovery_capabilities(attempt.agent)


def test_unresolved_judge_and_failed_cleanup_block_agent_replay():
    artifacts = {'safe_case_replay': True, 'cleanup_status': 'succeeded',
                 'completion': {'execution': 'failed'}, 'native_failure': {'error_type': 'TimeoutError'}}
    assert classify_failure(artifacts)['action'] == 'replay_case'
    assert classify_failure({**artifacts, 'cleanup_status': 'failed'})['action'] == 'blocked'
    assert classify_failure({**artifacts, 'sdk_request': {'status': 'running'}})['action'] == 'blocked'
    assert classify_failure({**artifacts, 'host_trace_validation': 'failed'})['action'] == 'blocked'


@pytest.mark.parametrize('agent_id', ['react-agent', 'trading-agents', 'gpt-researcher'])
def test_audited_readonly_resources_explicitly_declare_replay_safety(agent_id):
    from pathlib import Path
    from agentbench.harness.registry import load_registry
    root = Path(__file__).resolve().parents[1]
    agent = load_registry(root / 'resources/registry.toml').find(agent_id, enabled_only=False)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'})
    assert runner.recovery_capabilities(agent).safe_case_replay is True


@pytest.mark.parametrize('trace_rejected', [False, True])
def test_judge_only_failure_still_records_host_trace_validation(tmp_path, monkeypatch, trace_rejected):
    from agentbench.sdk.plugin.kuma import service
    from agentbench.runtime.contracts.execution import RuntimeLimits
    root = tmp_path / 'agent'
    (root / 'agent').mkdir(parents=True)
    (root / 'agent/main.py').write_text('pass')
    agent = SimpleNamespace(path=root, agent_id='agent')
    checks = []

    @contextmanager
    def staged(agent, **kwargs):
        yield agent

    def validate(checkpoint):
        checks.append(checkpoint)
        if trace_rejected:
            raise RuntimeError('Trace rejected')

    session = SimpleNamespace(stdout='', stderr='', trace_checkpoint=lambda: 'original-checkpoint',
                              validate_trace=validate, wait=lambda **kw: 1, close=lambda: None)

    def runtime(**kwargs):
        def start(agent, *, invocation, **other):
            Artifacts(invocation[1], environ={}).save('manifest.json', {
                'phase': 'judge', 'execution': 'succeeded', 'otel': 'complete',
                'submission': 'committed', 'evidence': 'captured', 'judge': 'failed'})
            return session
        return SimpleNamespace(start=start)

    monkeypatch.setattr(service, 'evaluation_agent', staged)
    options = dict(output=tmp_path / 'output', environ={'KUMA_API_KEY': 'offline'},
                   runtime_services=SimpleNamespace(create_docker_runtime=runtime, limits=RuntimeLimits()))
    if trace_rejected:
        with pytest.raises(RuntimeError, match='Trace rejected'):
            service.evaluate(agent, **options)
    else:
        service.evaluate(agent, **options)
    directory, = (tmp_path / 'output').iterdir()
    host = json.loads((directory / 'run.json').read_text())
    assert host['status'] == 'failed'  # A validated trace is not a Judge report.
    assert host['cleanup_status'] == 'succeeded'
    assert host['host_trace_validation'] == ('failed' if trace_rejected else 'succeeded')
    assert checks == ['original-checkpoint']
