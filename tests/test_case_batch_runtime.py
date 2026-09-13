"""Batch preparation must happen once, before independent Case execution.

The SDK exposes no batch entry point: preparation creates one Run per Case and saves
each Case as a reusable artifact file, and execution reuses those files by path.
"""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from agentbench.sdk.kuma import benchmark
from agentbench.harness.result import BenchmarkResult
from agentbench.harness.runner.suite_runner import SuiteRunner


def artifact(case_id, prompt):
    """A saved Case artifact in the custom-origin shape, whose content is already normalized.

    Official artifacts keep the signed wire content instead; reading either one goes
    through the SDK converter, which these tests exercise via generation.artifact_case.
    """
    return {'schema_version': 'kuma.case_artifact.v1', 'origin': 'custom', 'integrity': None,
            'case': {'case_id': case_id,
                     'inputs': [{'payload_type': 'text', 'payload': prompt}]}}


@pytest.fixture
def batch_runtime(monkeypatch, tmp_path):
    calls = []
    faults = {}
    runner = benchmark.KumaContainerRunner(options={'max_steps': 6, 'output': tmp_path})
    monkeypatch.setattr(runner, 'validate_sdk', lambda _: 'official-container')

    def evaluate(registration, **kwargs):
        calls.append(kwargs)
        folder = tmp_path / str(len(calls))
        (folder / 'evaluation').mkdir(parents=True)
        (folder / 'run.json').write_text(json.dumps({'status': 'succeeded'}))
        if kwargs.get('generation_count') is not None:
            count = kwargs['generation_count'] + faults.get('count_delta', 0)
            cases = (folder / 'evaluation/cases'); cases.mkdir()
            collection = {'schema': 'abb.case_collection.v2', 'requested_count': kwargs['generation_count'],
                          'cases': []}
            for index in range(count):
                name = f'abb-case-{index + 1:04d}.json'
                prompt = f'Research subject {0 if faults.get("duplicate") else index}'
                (cases / name).write_text(json.dumps(artifact(f'case-{index}', prompt)))
                from agentbench.sdk.common.case_identity import case_content_sha256
                collection['cases'].append({
                    'case_id': f'case-{index}', 'artifact': f'.kuma/{name}', 'origin': 'official',
                    'content_sha256': case_content_sha256(artifact(f'case-{index}', prompt)['case'])})
            (folder / 'evaluation/case-collection.json').write_text(json.dumps(collection))
        else:
            saved = json.loads(Path(kwargs['case_artifact']).read_text())
            (folder / 'evaluation/case.json').write_text(json.dumps(saved['case']))
        return folder

    monkeypatch.setattr(benchmark, 'evaluate', evaluate)
    monkeypatch.setattr(benchmark, 'read_result', lambda directory, agent_id, *args: BenchmarkResult(
        agent_id, 'fixture', directory.name, 'report_ready', SimpleNamespace(status='pass'), (), 1))
    return runner, calls, faults


@pytest.mark.parametrize('count', [1, 2, 10])
def test_registry_count_becomes_one_preparation_and_n_independent_executions(
        batch_runtime, starter_agent, count):
    runner, calls, _ = batch_runtime
    result = SuiteRunner(benchmark_runner=runner).run([replace(starter_agent, case_count=count)])
    assert result.passed and result.items[0].completed_case_count == count
    generations = [c for c in calls if c.get('generation_count') is not None]
    executions = [c for c in calls if c.get('case_artifact') is not None]
    assert len(generations) == 1 and generations[0]['generation_count'] == count
    assert len(executions) == count
    assert all(c['max_steps'] == 6 for c in calls)
    # Every execution reuses a distinct prepared artifact file.
    assert len({Path(c['case_artifact']).name for c in executions}) == count
    assert all(Path(c['case_artifact']).is_file() for c in executions)
    # New suite prepares again, never reuses the previous collection.
    SuiteRunner(benchmark_runner=runner).run([replace(starter_agent, case_count=count)])
    assert len([c for c in calls if c.get('generation_count') is not None]) == 2


@pytest.mark.parametrize('fault', ['duplicate', 'short', 'long'])
def test_invalid_batch_stops_before_any_agent_execution(batch_runtime, starter_agent, fault):
    runner, calls, faults = batch_runtime
    faults.update({'duplicate': True} if fault == 'duplicate'
                  else {'count_delta': -1 if fault == 'short' else 1})
    result = SuiteRunner(benchmark_runner=runner).run([replace(starter_agent, case_count=2)])
    assert not result.passed and result.items[0].completed_case_count == 0
    assert len(calls) == 1 and calls[0]['generation_count'] == 2


class FakeRun:
    """Minimal stand-in for the SDK Run object used during preparation."""

    def __init__(self, repo, case_id, prompt, failure=None):
        self.repo, self.case_id, self.prompt, self.failure = repo, case_id, prompt, failure
        self.cancelled = False

    def save_case(self, relative):
        if self.failure is not None:
            raise self.failure
        destination = self.repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(artifact(self.case_id, self.prompt)))
        return destination

    def cancel(self):
        self.cancelled = True


def test_preparation_creates_one_run_per_case_and_never_executes(tmp_path):
    from agentbench.sdk.kuma.generation import generate_collection
    from agentbench.sdk.common.artifacts import Artifacts
    repo = tmp_path / 'repo'; (repo / '.kuma').mkdir(parents=True)
    created = []

    def create_run(**options):
        run = FakeRun(repo, f'case-{len(created)}', f'Subject {len(created)}')
        created.append(run)
        return run

    collection = generate_collection(create_run, count=3, options={}, files=Artifacts(tmp_path), repo=repo)
    assert len(created) == 3 and all(run.cancelled for run in created)
    assert [entry['artifact'] for entry in collection['cases']] == [
        '.kuma/abb-case-0001.json', '.kuma/abb-case-0002.json', '.kuma/abb-case-0003.json']
    assert all((repo / entry['artifact']).is_file() for entry in collection['cases'])
    assert len({entry['content_sha256'] for entry in collection['cases']}) == 3


def test_preparation_failure_keeps_collected_cases_without_claiming_completion(tmp_path):
    from agentbench.sdk.kuma.generation import generate_collection
    from agentbench.sdk.common.artifacts import Artifacts
    repo = tmp_path / 'repo'; (repo / '.kuma').mkdir(parents=True)
    created = []

    def create_run(**options):
        index = len(created)
        failure = RuntimeError('generation failed') if index == 1 else None
        run = FakeRun(repo, f'case-{index}', f'Subject {index}', failure=failure)
        created.append(run)
        return run

    with pytest.raises(RuntimeError, match='generation failed'):
        generate_collection(create_run, count=3, options={}, files=Artifacts(tmp_path), repo=repo)
    saved = json.loads((tmp_path / 'case-collection.json').read_text())
    assert len(saved['cases']) == 1 and saved['requested_count'] == 3
    # The Run whose save failed is still released.
    assert all(run.cancelled for run in created)


def test_saved_collection_import_does_not_generate(batch_runtime, starter_agent, tmp_path):
    runner, calls, _ = batch_runtime
    store = tmp_path / 'saved'; (store / 'cases').mkdir(parents=True)
    from agentbench.sdk.common.case_identity import case_content_sha256
    entries = []
    for index in range(2):
        name = f'abb-case-{index + 1:04d}.json'
        content = artifact(f'case-{index}', f'Task {index}')
        (store / 'cases' / name).write_text(json.dumps(content))
        entries.append({'case_id': f'case-{index}', 'artifact': f'.kuma/{name}',
                        'content_sha256': case_content_sha256(content['case'])})
    saved = store / 'saved.json'
    saved.write_text(json.dumps({'schema': 'abb.case_collection.v2', 'requested_count': 2, 'cases': entries}))
    runner.case_collection = saved
    original = saved.read_bytes()
    result = SuiteRunner(benchmark_runner=runner).run([replace(starter_agent, case_count=2)])
    assert result.passed
    assert len(calls) == 2 and all(c.get('generation_count') is None for c in calls)
    assert [Path(c['case_artifact']).name for c in calls] == ['abb-case-0001.json', 'abb-case-0002.json']
    assert saved.read_bytes() == original


@pytest.mark.parametrize('generation_count', [None, 2])
def test_only_agent_execution_requires_a_model_trace(monkeypatch, tmp_path, generation_count):
    from contextlib import contextmanager
    from agentbench.sdk.kuma import service
    root = tmp_path / 'unit'; (root / 'agent').mkdir(parents=True)
    agent = SimpleNamespace(path=root, agent_id='a')

    @contextmanager
    def overlay(*args):
        yield agent

    checked = []
    session = SimpleNamespace(trace_checkpoint=lambda: None, wait=lambda **kw: 0,
                              validate_trace=lambda checkpoint: checked.append(checkpoint),
                              close=lambda: None, stdout='', stderr='')
    monkeypatch.setattr(service, 'evaluation_agent', overlay)
    monkeypatch.setattr(service, 'DockerRuntime', lambda **kw: SimpleNamespace(start=lambda *a, **kw: session))
    output = service.evaluate(agent, output=tmp_path / 'out', sdk=tmp_path,
                              environ={'DEFUZEX_API_KEY': 'fixture'}, generation_count=generation_count)
    assert json.loads((output / 'run.json').read_text())['status'] == 'succeeded'
    assert len(checked) == (1 if generation_count is None else 0)


@pytest.mark.parametrize('fault', ['missing_id', 'foreign_path', 'short_digest', 'duplicate', 'wrong_count'])
def test_invalid_saved_selection_rejected_before_execution(batch_runtime, starter_agent, tmp_path, fault):
    runner, calls, _ = batch_runtime
    store = tmp_path / 'invalid'; (store / 'cases').mkdir(parents=True)
    content = artifact('a', 'Question')
    (store / 'cases/abb-case-0001.json').write_text(json.dumps(content))
    from agentbench.sdk.common.case_identity import case_content_sha256
    entry = {'case_id': 'a', 'artifact': '.kuma/abb-case-0001.json',
             'content_sha256': case_content_sha256(content['case'])}
    collection = {'schema': 'abb.case_collection.v2', 'requested_count': 1, 'cases': [entry]}
    if fault == 'missing_id':
        entry['case_id'] = ''
    elif fault == 'foreign_path':
        entry['artifact'] = '/etc/passwd'
    elif fault == 'short_digest':
        entry['content_sha256'] = 'abc'
    elif fault == 'duplicate':
        collection.update(requested_count=2, cases=[entry, dict(entry)])
    else:
        collection['requested_count'] = 2
    path = store / 'invalid.json'; path.write_text(json.dumps(collection)); runner.case_collection = path
    count = 2 if fault in ('duplicate', 'wrong_count') else 1
    result = SuiteRunner(benchmark_runner=runner).run([replace(starter_agent, case_count=count)])
    assert not result.passed and not calls


def test_host_rejection_keeps_the_judge_verdict_it_already_paid_for(monkeypatch, tmp_path):
    from contextlib import contextmanager
    from agentbench.sdk.kuma import service
    root = tmp_path / 'unit'; (root / 'agent').mkdir(parents=True)
    agent = SimpleNamespace(path=root, agent_id='a')

    @contextmanager
    def overlay(*args):
        yield agent

    def reject(checkpoint):
        raise RuntimeError('Agent invocation completed without a matched LLM request/response trace')

    def container_wrote_a_verdict(directory):
        judge = directory / 'evaluation/judge'; judge.mkdir(parents=True)
        (judge / 'report.json').write_text(json.dumps(
            {'status': 'fail', 'report_id': 'report_fixture', 'run_id': 'run_fixture'}))

    session = SimpleNamespace(trace_checkpoint=lambda: None, wait=lambda **kw: 0,
                              validate_trace=reject, close=lambda: None, stdout='', stderr='')
    monkeypatch.setattr(service, 'evaluation_agent', overlay)
    monkeypatch.setattr(service, 'DockerRuntime', lambda **kw: SimpleNamespace(start=lambda *a, **kw: session))
    with pytest.raises(RuntimeError):
        service.evaluate(agent, output=tmp_path / 'out', sdk=tmp_path,
                         environ={'DEFUZEX_API_KEY': 'fixture'},
                         on_artifacts_ready=container_wrote_a_verdict)
    directory = next((tmp_path / 'out').iterdir())
    status = json.loads((directory / 'run.json').read_text())
    # The guard still rejects the Run; it just no longer hides what was bought.
    assert status['status'] == 'failed' and status['exit_code'] == 0
    assert status['judge']['status'] == 'fail'
    assert status['judge']['report_id'] == 'report_fixture'
    assert Path(status['judge']['report']).is_file()


def test_a_run_without_a_verdict_reports_no_judge_field(monkeypatch, tmp_path):
    from contextlib import contextmanager
    from agentbench.sdk.kuma import service
    root = tmp_path / 'unit'; (root / 'agent').mkdir(parents=True)
    agent = SimpleNamespace(path=root, agent_id='a')

    @contextmanager
    def overlay(*args):
        yield agent

    def reject(checkpoint):
        raise RuntimeError('no trace')

    session = SimpleNamespace(trace_checkpoint=lambda: None, wait=lambda **kw: 0,
                              validate_trace=reject, close=lambda: None, stdout='', stderr='')
    monkeypatch.setattr(service, 'evaluation_agent', overlay)
    monkeypatch.setattr(service, 'DockerRuntime', lambda **kw: SimpleNamespace(start=lambda *a, **kw: session))
    with pytest.raises(RuntimeError):
        service.evaluate(agent, output=tmp_path / 'out', sdk=tmp_path,
                         environ={'DEFUZEX_API_KEY': 'fixture'})
    status = json.loads((next((tmp_path / 'out').iterdir()) / 'run.json').read_text())
    assert status['status'] == 'failed' and 'judge' not in status


def _failed_run(directory, *, error, network_events=()):
    """Write the artifacts a container leaves behind when a phase fails."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'run.json').write_text(json.dumps(
        {'agent_id': 'a1', 'run_id': directory.name, 'status': 'failed'}))
    (directory / 'evaluation').mkdir(exist_ok=True)
    (directory / 'evaluation' / 'manifest.json').write_text(json.dumps({'error': error}))
    if network_events:
        (directory / 'network.jsonl').write_text(
            '\n'.join(json.dumps(event) for event in network_events))


def test_container_failure_names_the_sdk_error_and_the_blocked_upstream(tmp_path):
    directory = tmp_path / 'run1'
    _failed_run(
        directory,
        error={'type': 'ServiceError', 'message': 'The KUMA service request failed.',
               'code': 'invalid_response'},
        network_events=[
            {'event': 'llm_request', 'data': {'host': 'example.test'}},
            {'event': 'tool_error', 'data': {'method': 'GET', 'host': 'defuzex.ai',
                                             'path': '/sdk/v2/operations/abc/',
                                             'error': "[Errno 110] Connect call failed"}},
        ],
    )
    with pytest.raises(RuntimeError) as failure:
        benchmark.read_result(directory, 'a1')
    message = str(failure.value)
    # The SDK's own classification, which alone does not say the connection never opened.
    assert 'ServiceError: The KUMA service request failed. [invalid_response]' in message
    # The Interceptor names the upstream, which is what makes the cause attributable.
    assert 'GET defuzex.ai/sdk/v2/operations/abc/' in message
    assert '[Errno 110] Connect call failed' in message


def test_container_failure_without_interceptor_errors_still_names_the_cause(tmp_path):
    directory = tmp_path / 'run2'
    _failed_run(directory, error={'type': 'CaseIntegrityError',
                                  'message': 'The Case integrity metadata does not match.',
                                  'code': 'invalid_case_integrity'})
    with pytest.raises(RuntimeError) as failure:
        benchmark.read_result(directory, 'a1')
    message = str(failure.value)
    assert 'CaseIntegrityError: The Case integrity metadata does not match.' in message
    assert 'invalid_case_integrity' in message
    # Nothing to attribute to the Interceptor, so it is not mentioned at all.
    assert 'interceptor' not in message


def test_container_failure_falls_back_to_the_path_when_nothing_is_recorded(tmp_path):
    directory = tmp_path / 'run3'
    directory.mkdir()
    (directory / 'run.json').write_text(json.dumps(
        {'agent_id': 'a1', 'run_id': 'run3', 'status': 'failed'}))
    with pytest.raises(RuntimeError, match='Container evaluation did not complete'):
        benchmark.read_result(directory, 'a1')
