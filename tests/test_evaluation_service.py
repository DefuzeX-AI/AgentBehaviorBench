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


def test_execution_uses_prepared_unit_and_freezes_its_revision(project):
    from dataclasses import replace
    import shutil
    from agentbench.harness.session.plan import source_digest
    from agentbench.evaluation.targets import PreparedTarget
    service, _, _ = project
    original = service._registration('example')
    path = service.root / 'prepared'
    shutil.copytree(original.path, path)
    manifest = path / 'agent.toml'
    manifest.write_text(manifest.read_text() + '\n[source]\nrevision="' + 'a' * 40 + '"\n')
    prepared = PreparedTarget(replace(original, path=path, requirement_path=path / 'requirement.md'),
                              'a' * 40, 'fingerprint', source_digest(path))
    result = service.execute('example', [{'case_id': 'one', 'inputs': [
        {'input_id': 'a', 'payload': 'hello'}]}], target=prepared, concurrency=ConcurrencySettings(1))
    assert result['suite']['summary']['execution_status'] == 'completed'
    evidence = service.evidence(result['directory'], result['runs'][0]['id'])
    assert evidence['trajectory']['metadata']['system_architecture']['source_revision'] == 'a' * 40


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
    from agentbench.harness.ground_truth.manifests import MANIFEST_SCHEMA
    from tests.test_ground_truth import reference_attempt
    directory = service.root / 'unit/ground_truth/echo-changed'
    directory.mkdir(parents=True)
    reference_attempt(directory / 'attempts/reference', agent_id)
    (directory / 'gt.json').write_text(json.dumps({
        'schema': MANIFEST_SCHEMA, 'agent_id': agent_id, 'id': 'echo-changed',
        'summary': 'Echo changed', 'explanation': 'Output appends a counter to the requested exact echo.',
        'reference_attempts': ['reference'],
        'decisive_step': {'attempt': 'reference', 'step_id': 2, 'reason': 'The final answer appends a counter.'}}))
    (directory / 'case.json').write_text(json.dumps({'case_id': 'reference'}))


def test_gt_matches_submitted_summary_before_loading_saved_traces(project, monkeypatch):
    service, _, _ = project
    install_test_gt(service, 'example')
    result = run_one(service)
    suite, run = result['directory'], result['runs'][0]['id']
    request = service.evidence(suite, run)['request']
    response = {**report(request, 'issue'), 'issues': [{'input_id': 'a', 'message': 'Fixture finding'}]}
    service.submit_judge(suite, run, response)
    from agentbench.harness.ground_truth import evaluator
    monkeypatch.setattr(evaluator, 'model_config', lambda _: SimpleNamespace(model='fixture', base_url='https://example.test'))
    calls = []
    def ask(model, **kwargs):
        payload = kwargs['payload']
        calls.append(payload)
        assert payload['finding_summary'] == 'Fixture finding'
        if len(calls) == 1:
            assert set(payload) == {'reference', 'finding_summary'}
            return {'match': True, 'reason': 'Matching problem summaries'}
        assert payload['reference_trajectories'][0]['step_refs'] == ['reference/1', 'reference/2']
        assert payload['reference']['decisive_step']['step_ref'] == 'reference/2'
        # The echo fixture makes no observed model call, so the candidate has no steps to cite.
        assert payload['candidate_trajectory']['step_ids'] == []
        return {'match': None, 'reason': 'Candidate trajectory has no observed steps',
                'reference_step_ids': [], 'candidate_step_ids': [], 'candidate_decisive_step': None}
    gt = service.evaluate_gt(suite, ask=ask)
    assert len(calls) == 2 and gt['scores']['pending'] == 1 and gt['scores']['discovery_rate'] is None
    assert gt['status'] == 'partial' and gt['provisional']
    assert gt['decisions'][0]['localization']['reference_decisive_step'] == 'reference/2'


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
