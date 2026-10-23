"""Exercise the shared API through real scheduling, worker and persistence logic."""
import json
from types import SimpleNamespace
import pytest

from agentbench.evaluation import EvaluationService
from agentbench.harness.concurrency import ConcurrencySettings
from tests.test_sdk_defaults import make_runner, FakeAgent, unchanged_stage, inprocess_worker_permissions


@pytest.fixture
def project(tmp_path_factory, monkeypatch):
    tmp_path = tmp_path_factory.mktemp('ev')
    unit = tmp_path / 'unit'
    (unit / 'agent').mkdir(parents=True)
    (unit / 'agent/main.py').write_text('pass\n')
    (unit / 'agent.toml').write_text('agent_id="example"\nframework="langgraph"\n')
    (unit / 'requirement.md').write_text('---\ninput_type: text\n---\nEcho input.\n')
    (tmp_path / 'resources').mkdir()
    (tmp_path / 'resources/registry.toml').write_text(
        'schema_version="defuzex-bench.registry.v1"\n[[agents]]\nagent_id="example"\n'
        'path="unit"\nframework="langgraph"\nstatus="ready"\nenabled=true\ncase=1\n')
    registration = SimpleNamespace(path=unit, agent_id='example', framework='langgraph', case_count=1)
    agent = FakeAgent()
    fake, processes = make_runner(tmp_path, registration, monkeypatch, agent=agent)
    from agentbench.runtime.services import RuntimeServices
    from agentbench.sdk.plugin.native.plugin import plugin
    from agentbench.sdk.plugin.native.backend import create_run
    from agentbench.sdk.integration import worker
    monkeypatch.setattr(RuntimeServices, 'create_docker_runtime',
                        lambda self, **kwargs: fake.context.runtime_services.create_docker_runtime(**kwargs))
    monkeypatch.setattr(plugin, 'stage_agent', unchanged_stage)
    monkeypatch.setattr(worker, 'load_factory', lambda _: create_run)
    return EvaluationService(tmp_path, environ={}), agent, processes


def run_one(service):
    return service.execute('example', [{'case_id': 'one', 'inputs': [
        {'input_id': 'a', 'payload': 'hello'}]}], concurrency=ConcurrencySettings(1))


def report(request, status='pass'):
    return {'schema': 'abb.judge.result.v1', 'request_id': request['request_id'],
            'status': status, 'confidence': 'high', 'issues': [], 'evidence_gaps': []}


def test_python_execution_external_report_and_gt(project):
    service, agent, processes = project
    result = run_one(service)
    assert result['suite']['state'] == 'complete'
    assert result['suite']['counts']['completed'] == 1
    assert agent.requests and all(p.closed for p in processes)
    suite, run = result['directory'], result['runs'][0]['id']
    evidence = service.evidence(suite, run)
    request = evidence['request']
    assert request['case']['abb_agent_context']['profile'].endswith('Echo input.\n')
    attachment = next(iter(request['attachments']))
    assert service.attachment(suite, run, attachment)['content']
    response = report(request)
    judged = service.submit_judge(suite, run, response)
    assert judged['suite']['judge_counts'] == {'pass': 1}
    assert judged['suite']['summary']['quality_gate'] == 'passed'
    revision = judged['suite']['revision']
    assert service.submit_judge(suite, run, response)['suite']['revision'] == revision
    gt = service.evaluate_gt(suite)
    assert gt['status'] == 'completed' and gt['provisional'] is True
    assert gt['skipped_agents'] == [{'agent_id': 'example', 'reason': 'no_gt'}]
    assert service.result(suite)['suite']['gt_evaluation']['evaluation_id'] == gt['evaluation_id']


def test_bad_submission_does_not_poison_valid_retry(project):
    service, _, _ = project
    result = run_one(service)
    suite, run = result['directory'], result['runs'][0]['id']
    request = service.evidence(suite, run)['request']
    with pytest.raises(ValueError, match='mismatched'):
        service.submit_judge(suite, run, {**report(request), 'request_id': 'wrong'})
    assert service.submit_judge(suite, run, report(request))['suite']['judge_counts'] == {'pass': 1}
    with pytest.raises(ValueError, match='different'):
        service.submit_judge(suite, run, {**report(request, 'issue'),
            'issues': [{'input_id': 'a', 'message': 'Different finding'}]})
    with pytest.raises(ValueError, match='registered'):
        service.attachment(suite, run, '../../.env')


def test_cli_reads_same_result_and_report(project, capsys):
    from agentbench.cli.main import cli
    service, _, _ = project
    result = run_one(service)
    suite, run = result['directory'], result['runs'][0]['id']
    request = service.evidence(suite, run)['request']
    path = service.root / 'report.json'
    path.write_text(json.dumps(report(request)))
    capsys.readouterr()
    assert cli(['api', '--root', str(service.root), 'submit-judge', '--suite', suite,
                 '--run-id', run, '--report', str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == service.result(suite)


def install_test_gt(service, agent_id):
    """Synthetic GT for protocol tests, never a benchmark finding."""
    from agentbench.harness.session.plan import source_digest, digest_json
    from agentbench.harness.ground_truth.files import file_digest
    unit = service.root / 'unit'
    directory = unit / 'ground_truth'
    directory.mkdir(exist_ok=True)
    observations = []
    for index in range(2):
        path = directory / f'observation-{index}.txt'
        path.write_text('Synthetic fixture: expected exact echo, observed modified output.')
        observations.append({'id': str(index), 'case_sha256': 'a' * 64,
            'evidence_path': path.name, 'evidence_sha256': file_digest(path)})
    defect = {'id': 'echo-changed', 'title': 'Echo changed', 'expected_behavior': 'Echo input exactly',
        'observed_behavior': 'Output contains an added turn counter', 'source_sha256': source_digest(unit),
        'case_sha256': 'a' * 64, 'confirmed_by': 'synthetic-test-fixture',
        'confirmed_at': '2026-10-21T00:00:00+00:00', 'observations': observations}
    (directory / 'manifest.json').write_text(json.dumps({'schema': 'abb.agent.ground_truth.v1',
        'agent_id': agent_id, 'defects': [defect]}))
    (directory / 'matching.json').write_text(json.dumps({'schema': 'abb.gt.matching.v1', 'rules': [{
        'ground_truth_id': defect['id'], 'ground_truth_sha256': digest_json(defect),
        'review_status': 'approved', 'conditions': [{'id': 'C1', 'text': 'Output appends a counter to the requested exact echo.'}]}]}))


def test_gt_reads_submitted_report_in_second_stage_only(project, monkeypatch):
    service, _, _ = project
    install_test_gt(service, 'example')
    result = run_one(service)
    suite, run = result['directory'], result['runs'][0]['id']
    request = service.evidence(suite, run)['request']
    response = {**report(request, 'issue'), 'issues': [{'input_id': 'a', 'message': 'Fixture finding'}]}
    service.submit_judge(suite, run, response)
    from agentbench.harness.ground_truth import evaluator
    monkeypatch.setattr(evaluator, '_model', lambda _: SimpleNamespace(model='fixture', base_url='https://example.test'))
    calls = []
    def ask(model, steps, **kwargs):
        evidence = kwargs['payload']['evidence']
        calls.append(evidence)
        ref = next(k for k in evidence if k.endswith('result.json'))
        if len(calls) == 1:
            assert 'report' not in evidence
            value = {'conditions': [{'id': 'C1', 'status': 'satisfied', 'reason': 'Fixture', 'evidence_refs': [ref]}]}
        else:
            assert evidence['report'] == response
            value = {'detected': True, 'reason': 'Fixture', 'evidence_refs': ['report', ref]}
        return value, json.dumps(value)
    gt = service.evaluate_gt(suite, ask=ask)
    assert len(calls) == 2 and gt['scores']['discovery_coverage'] == 1
    assert gt['status'] == 'completed' and gt['provisional']


def test_cli_execute_and_gt_use_shared_service(project, capsys):
    from agentbench.cli.main import cli
    service, _, _ = project
    path = service.root / 'cases.json'
    path.write_text(json.dumps({'schema': 'abb.cases.v1', 'cases': [
        {'case_id': 'cli', 'inputs': [{'input_id': 'a', 'payload': 'hello'}]}]}))
    capsys.readouterr()
    assert cli(['api', '--root', str(service.root), 'execute', 'example', '--case-file', str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['suite']['counts']['completed'] == 1
    assert result == service.result(result['directory'])
    assert cli(['api', '--root', str(service.root), 'gt', '--suite', result['directory']]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'completed'
