from agentbench.cli.trace_runtime import build_trace_suite_runner
from agentbench.sdk.kuma.benchmark import ContainerBenchmarkRunner
from agentbench.harness.runner.suite_runner import SuiteRunner
import json
import pytest
from agentbench.sdk.kuma.benchmark import read_result
from agentbench.harness.errors import ProviderSelectionError


@pytest.fixture
def completed_run(tmp_path):
    folder = tmp_path / 'run'; folder.mkdir()
    def save(name, data):
        path = folder / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    save('run.json', {'agent_id':'a', 'run_id':'run', 'status':'succeeded'})
    save('evaluation/manifest.json', {'run_id':'sdk-run', 'case_id':'case', 'execution':'succeeded',
        'otel':'complete', 'submission':'committed', 'evidence':'captured', 'judge':'received',
        'phase':'finished', 'steps':[{'input_id':'i', 'directory':'inputs/0001', 'committed':True}]})
    save('evaluation/case.json', {'case_id':'case', 'inputs':[{'input_id':'i'}]})
    save('evaluation/judge/report.json', {'run_id':'sdk-run', 'report_id':'report', 'status':'issue',
                                         'extensions':{'case_id':'case'}})
    prefix = 'evaluation/inputs/0001/'
    save(prefix+'input.json', {'input_id':'i', 'payload':'unchanged'})
    save(prefix+'request.json', {'agent_id':'a', 'run_id':'inv', 'session_id':'sdk-run'})
    save(prefix+'result.json', {'schema':'abb.result.v1', 'agent_id':'a', 'run_id':'inv',
                               'status':'succeeded', 'output':'report'})
    save(prefix+'submission.json', {'status':'completed', 'output':'report'})
    save(prefix+'otel-status.json', {'status':'complete'})
    save(prefix+'evidence.json', {'spans':[{'span_id':'span'}]})
    return folder, save


def test_issue_is_completed_but_not_benchmark_pass(completed_run):
    from agentbench.harness.result import BenchmarkSuiteResult, SuiteAgentResult
    from agentbench.cli.features.certify import _agent_completed_certification
    folder, _ = completed_run
    result = read_result(folder, 'a')
    assert not result.passed
    suite = BenchmarkSuiteResult('suite', ('a',), (SuiteAgentResult('a', (result,), 1),))
    assert _agent_completed_certification(suite, 'a')


@pytest.mark.parametrize('file,value', [
    ('evaluation/judge/report.json', {'run_id':'wrong'}),
    ('evaluation/inputs/0001/evidence.json', {'spans':[]}),
    ('evaluation/inputs/0001/submission.json', {'status':'completed','output':'wrong'}),
    ('evaluation/inputs/0001/otel-status.json', {'status':'incomplete'}),
])
def test_incomplete_or_mismatched_artifacts_cannot_certify(completed_run, file, value):
    folder, save = completed_run
    save(file, value)
    with pytest.raises((RuntimeError, KeyError)):
        read_result(folder, 'a')


def test_default_suite_uses_container_core():
    assert isinstance(SuiteRunner()._benchmark_runner, ContainerBenchmarkRunner)


@pytest.mark.parametrize('timeout', [0, -1, True, '10', float('inf'), float('nan')])
def test_invalid_timeout_rejected_before_execution(timeout):
    with pytest.raises(ProviderSelectionError, match='timeout'):
        ContainerBenchmarkRunner(options={'timeout': timeout})


def test_host_rejection_marks_run_failed(completed_run, monkeypatch):
    from types import SimpleNamespace
    from agentbench.sdk.kuma import benchmark
    folder, save = completed_run
    save('evaluation/inputs/0001/evidence.json', {'spans': []})
    runner = ContainerBenchmarkRunner()
    monkeypatch.setattr(runner, 'validate_sdk', lambda _: 'official-container')
    prepared = folder / 'prepared'; prepared.mkdir(parents=True, exist_ok=True)
    (prepared / 'abb-case-0001.json').write_text(json.dumps({'schema_version': 'kuma.case_artifact.v1'}))
    runner._case_batches['a'] = {
        'collection': {'schema': 'abb.case_collection.v2', 'requested_count': 1,
                       'cases': [{'case_id': 'case-1', 'artifact': '.kuma/abb-case-0001.json'}]},
        'next_index': 0, 'cases': prepared}
    monkeypatch.setattr(benchmark, 'evaluate', lambda *a, **kw: folder)
    notifications = []
    with pytest.raises(RuntimeError, match='evidence'):
        runner.run(SimpleNamespace(agent_id='a'), on_step_complete=lambda *a: notifications.append(a))
    assert json.loads((folder / 'run.json').read_text())['status'] == 'failed'
    assert notifications == []


def test_run_and_certify_factory_use_same_core_and_model():
    runner = build_trace_suite_runner(mode='off', max_bytes=262144, output_fn=lambda _: None,
                                     model='selected-model')
    assert isinstance(runner._benchmark_runner, ContainerBenchmarkRunner)
    assert runner._benchmark_runner.environ['OPENROUTER_MODEL'] == 'selected-model'


def test_default_kuma_source_is_sibling_checkout(repo_root):
    # Moving the adapter must not shift the default to inside AgentBehaviorBench.
    assert ContainerBenchmarkRunner().sdk == repo_root.parent / 'Defuze-SDK'


def test_custom_sdk_remains_explicit_injection():
    class SDK:
        @staticmethod
        def create_run(**kwargs):
            raise AssertionError('No network expected in construction')
    runner = SuiteRunner(sdk=SDK())
    assert not isinstance(runner._benchmark_runner, ContainerBenchmarkRunner)
