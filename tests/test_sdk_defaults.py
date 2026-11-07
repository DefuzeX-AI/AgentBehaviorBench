import asyncio
from contextlib import contextmanager
from dataclasses import replace
from functools import partial
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agentbench.runtime.contracts.execution import RuntimeLimits
from agentbench.sdk.contracts import SDKRunnerContext
from agentbench.sdk.integration.artifacts import FileArtifactStore
from agentbench.sdk.integration.cases import case_bytes
from agentbench.sdk.integration.plugin import ContainerSDKPlugin
from agentbench.sdk.integration.run import Report, Run
from agentbench.sdk.integration import worker


@pytest.fixture(autouse=True)
def inprocess_worker_permissions(monkeypatch):
    # These unit tests execute Linux worker code on the host. Real ownership
    # publication is exercised unchanged by the Docker acceptance below.
    if os.name == 'nt':
        monkeypatch.setattr(worker, 'share_output', lambda directory: None)


class ExampleRun(Run):
    def __init__(self, case, *, evidence=None):
        super().__init__(case, evidence=evidence)
        self.judged = 0
        self.closed = False

    def judge(self):
        self.judged += 1
        return Report('pass')

    def close(self):
        self.closed = True


class FakeAgent:
    def __init__(self, *, result_status='succeeded', telemetry='complete'):
        self.result_status, self.telemetry = result_status, telemetry
        self.requests = []
        self.closed = False

    async def invoke(self, envelope, output, evidence):
        self.requests.append(envelope)
        (output / 'otel-status.json').write_text(json.dumps({'status': self.telemetry}))
        (output / 'spans.jsonl').write_text('')
        return {'run_id': envelope['run_id'], 'status': self.result_status,
                'output': envelope['input'], 'error': 'native failure' if self.result_status != 'succeeded' else None}

    async def aclose(self):
        self.closed = True

    def snapshot(self):
        return {'closed': self.closed, 'invocations': len(self.requests)}


@pytest.fixture
def factory(monkeypatch):
    generated, runs = [], []
    def create_run(*, case=None, case_index=0, evidence=None, **kwargs):
        if case is None:
            generated.append(case_index)
            case = {'case_id': f'case-{case_index}', 'inputs': [
                {'input_id': 'one', 'payload': 'first'}, {'input_id': 'two', 'payload': 'second'}]}
        run = ExampleRun(case, evidence=evidence)
        runs.append(run)
        return run
    monkeypatch.setattr(worker, 'load_factory', lambda reference: create_run)
    return SimpleNamespace(create=create_run, generated=generated, runs=runs)


@pytest.fixture
def unit(tmp_path):
    root = tmp_path / 'agent-unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'agent/main.py').write_text('pass\n')
    (root / 'agent.toml').write_text('agent_id="example"\nframework="langgraph"\n')
    return SimpleNamespace(path=root, agent_id='example', framework='langgraph', case_count=2)


@contextmanager
def unchanged_stage(agent, **kwargs):
    yield agent


def make_runner(tmp_path, unit, monkeypatch, *, agent=None, **options):
    processes = []
    def create_runtime(**runtime_options):
        role = 'agent' if runtime_options['run_id'].endswith('-agent') else 'controller'
        def start(descriptor, *, invocation, **kwargs):
            process = SimpleNamespace(stdout='', stderr='', closed=False)
            def close():
                process.closed = True
            process.close = close
            process.trace_checkpoint = lambda: role
            process.validate_trace = lambda checkpoint: None
            def wait(**kwargs):
                if role == 'agent':
                    return 0
                request, output = invocation
                settings = json.loads((request / 'evaluation.json').read_text())
                policy = runtime_options['policy']
                settings['private_storage'] = str(policy.storage)
                settings['case_publications'] = {str(i): str(path) for i, path in policy.publications}
                return asyncio.run(worker.execute(descriptor.path, output, settings, session=agent or FakeAgent()))
            process.wait = wait
            processes.append(process)
            return process
        return SimpleNamespace(start=start)
    requirements = tmp_path / 'requirements.txt'
    requirements.write_text('')
    plugin = ContainerSDKPlugin(create_run='example.backend:create_run', requirements=requirements)
    monkeypatch.setattr(plugin, 'stage_agent', unchanged_stage)
    context = SDKRunnerContext(environ={}, model=None, trace_sink=None, trace_max_bytes=1024,
        artifacts=FileArtifactStore(tmp_path / 'suite'), runtime_services=SimpleNamespace(
            create_docker_runtime=create_runtime, limits=RuntimeLimits()))
    runner = plugin.create_benchmark_runner(context=context, options={'output': tmp_path / 'output', **options})
    return runner, processes


def test_default_host_worker_generate_execute_and_reuse_without_regeneration(tmp_path, monkeypatch, factory, unit):
    agent = FakeAgent()
    runner, processes = make_runner(tmp_path, unit, monkeypatch, agent=agent)
    cases = runner.prepare_cases(unit)
    assert factory.generated == [0, 1]
    assert len(cases) == 2
    assert runner.prepare_cases(unit) == cases
    assert factory.generated == [0, 1]
    result = runner.run_case(unit, cases[0])
    assert result.passed and result.host_acceptance == 'accepted' and result.history_count == 2
    assert [r['input'] for r in agent.requests] == ['first', 'second']
    assert len({r['session_id'] for r in agent.requests}) == 1
    assert agent.closed and all(p.closed for p in processes)
    assert all(run.closed for run in factory.runs)
    assert factory.runs[-1].judged == 1


def test_default_runner_also_works_without_a_suite_store(tmp_path, monkeypatch, factory, unit):
    runner, _ = make_runner(tmp_path, unit, monkeypatch)
    runner.context = replace(runner.context, artifacts=None)
    case = runner.prepare_cases(unit)[0]
    assert runner.run_case(unit, case).passed


def test_workspace_change_is_rejected_before_starting_an_agent(tmp_path, monkeypatch, factory, unit):
    manifest = unit.path / 'agent.toml'
    manifest.write_text(manifest.read_text() +
        '[evaluation.workspace]\npath="/home/agent/work"\ninitial_state="empty"\n')
    runner, processes = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    count = len(processes)
    manifest.write_text(manifest.read_text().replace('/home/agent/work', '/home/agent/changed'))
    with pytest.raises(ValueError, match='workspace differs'):
        runner.run_case(unit, case)
    assert len(processes) == count


@pytest.mark.parametrize('judge_fails', [False, True])
def test_sdk_cleanup_failure_is_retained_without_hiding_judge_error(tmp_path, monkeypatch, factory, unit, judge_fails):
    runner, processes = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    def failing_close(**kwargs):
        run = factory.create(**kwargs)
        def close():
            raise RuntimeError('SDK close failed')
        run.close = close
        if judge_fails:
            def judge():
                raise ConnectionError('original Judge error')
            run.judge = judge
        return run
    monkeypatch.setattr(worker, 'load_factory', lambda ref: failing_close)
    with pytest.raises(RuntimeError, match='original Judge error' if judge_fails else 'SDK close failed'):
        runner.run_case(unit, case)
    error = json.loads((runner.directory / 'error.json').read_bytes())
    if judge_fails:
        assert error['sdk_cleanup_error'] == 'SDK close failed'
    assert all(process.closed for process in processes)


def test_immutable_case_rejected_before_execution(tmp_path, monkeypatch, factory, unit):
    runner, processes = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    count = len(processes)
    document = json.loads(case.artifact_path.read_bytes())
    document['case']['inputs'][0]['payload'] = 'changed'
    case.artifact_path.write_bytes(case_bytes(document))
    with pytest.raises(ValueError, match='modified'):
        runner.run_case(unit, case)
    assert len(processes) == count


def test_existing_corrupt_publication_does_not_generate_again(tmp_path, monkeypatch, factory, unit):
    runner, _ = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    case.artifact_path.write_text('broken')
    with pytest.raises(RuntimeError, match='failed'):
        runner.prepare_cases(unit)
    assert factory.generated == [0, 1]


def test_partial_generation_keeps_published_case_and_does_not_retry_failed_request(tmp_path, monkeypatch, factory, unit):
    runner, _ = make_runner(tmp_path, unit, monkeypatch)
    failures = []
    def interrupted(**kwargs):
        if kwargs['case_index'] == 1 and kwargs['case'] is None:
            failures.append(1)
            raise ConnectionError('generation acceptance unknown')
        return factory.create(**kwargs)
    monkeypatch.setattr(worker, 'load_factory', lambda ref: interrupted)
    with pytest.raises(RuntimeError, match='failed'):
        runner.prepare_cases(unit)
    assert factory.generated == [0] and failures == [1]
    published = runner.context.artifacts.case(unit.agent_id, 0).directory / 'case.json'
    original = published.read_bytes()
    # Even another preparation call must not duplicate the unknown request.
    monkeypatch.setattr(worker, 'load_factory', lambda ref: factory.create)
    with pytest.raises(RuntimeError, match='failed'):
        runner.prepare_cases(unit)
    assert published.read_bytes() == original
    assert factory.generated == [0]
    error = json.loads((runner.directory / 'error.json').read_bytes())
    assert 'reconcile' in error['error']


def test_submit_can_return_final_report_without_setting_run_report(tmp_path, monkeypatch, factory, unit):
    runner, _ = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    def automatic(**kwargs):
        run = factory.create(**kwargs)
        original = run.submit
        def submit(*args, **kwargs):
            original(*args, **kwargs)
            return Report('pass') if len(run.history) == 2 else None
        run.submit = submit
        return run
    monkeypatch.setattr(worker, 'load_factory', lambda ref: automatic)
    assert runner.run_case(unit, case).passed
    assert factory.runs[-1].judged == 0


def test_judge_error_preserves_steps_and_closes_sdk_and_agent(tmp_path, monkeypatch, factory, unit):
    agent = FakeAgent()
    runner, processes = make_runner(tmp_path, unit, monkeypatch, agent=agent)
    case = runner.prepare_cases(unit)[0]
    def unavailable(**kwargs):
        run = factory.create(**kwargs)
        def judge():
            run.judged += 1
            raise ConnectionError('Judge request acceptance unknown')
        run.judge = judge
        return run
    monkeypatch.setattr(worker, 'load_factory', lambda ref: unavailable)
    with pytest.raises(RuntimeError, match='failed'):
        runner.run_case(unit, case)
    error = json.loads((runner.directory / 'error.json').read_bytes())
    assert error['phase'] == 'judge' and all(step['submitted'] for step in error['steps'])
    assert factory.runs[-1].judged == 1 and factory.runs[-1].closed
    assert agent.closed and all(p.closed for p in processes)


def test_torn_publication_blocks_generation(tmp_path, monkeypatch, factory, unit):
    runner, _ = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    (case.artifact_path.parent / 'publication.json').unlink()
    with pytest.raises(RuntimeError, match='failed'):
        runner.prepare_cases(unit)
    assert factory.generated == [0, 1]


def test_valid_json_edit_of_publication_is_detected(tmp_path, monkeypatch, factory, unit):
    runner, _ = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    document = json.loads(case.artifact_path.read_bytes())
    document['case']['inputs'][0]['payload'] = 'modified'
    case.artifact_path.write_bytes(case_bytes(document))
    with pytest.raises(RuntimeError, match='failed'):
        runner.prepare_cases(unit)
    assert factory.generated == [0, 1]


def test_agent_failure_is_preserved_and_not_a_passing_case(tmp_path, monkeypatch, factory, unit):
    runner, _ = make_runner(tmp_path, unit, monkeypatch, agent=FakeAgent(result_status='failed'))
    result = runner.run_case(unit, runner.prepare_cases(unit)[0])
    assert result.report.status == 'pass' and not result.passed
    assert result.execution_status == 'failed'
    assert all(f.error_message == 'native failure' for f in result.failures)
    assert all(row['error'] == 'native failure' for row in factory.runs[-1].history)


def test_incomplete_evidence_prevents_submission_and_closes_session(tmp_path, monkeypatch, factory, unit):
    agent = FakeAgent(telemetry='incomplete')
    runner, processes = make_runner(tmp_path, unit, monkeypatch, agent=agent)
    with pytest.raises(RuntimeError, match='failed'):
        runner.run_case(unit, runner.prepare_cases(unit)[0])
    assert factory.runs[-1].history == () and factory.runs[-1].judged == 0
    assert agent.closed and all(p.closed for p in processes)


def test_max_steps_rejects_extra_input_without_execution(tmp_path, monkeypatch, factory, unit):
    agent = FakeAgent()
    runner, _ = make_runner(tmp_path, unit, monkeypatch, agent=agent, max_steps=1)
    with pytest.raises(RuntimeError, match='failed'):
        runner.run_case(unit, runner.prepare_cases(unit)[0])
    assert len(agent.requests) == 1 and factory.runs[-1].judged == 0 and agent.closed


def test_loading_case_cannot_regenerate_a_different_case(tmp_path, monkeypatch, factory, unit):
    runner, processes = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    def bad_factory(**kwargs):
        run = factory.create(**kwargs)
        run.case['case_id'] = 'regenerated'
        return run
    monkeypatch.setattr(worker, 'load_factory', lambda reference: bad_factory)
    with pytest.raises(RuntimeError, match='failed'):
        runner.run_case(unit, case)
    assert factory.runs[-1].judged == 0 and all(p.closed for p in processes)


@pytest.mark.parametrize('artifact,change', [
    ('steps/0001/submission.json', lambda d: d.update(input_id='another')),
    ('steps/0001/request.json', lambda d: d.update(input='different input')),
    ('steps/0001/result.json', lambda d: d.update(run_id='wrong invocation')),
    ('case.json', lambda d: d['case'].update(case_id='different Case')),
    ('manifest.json', lambda d: d.update(case_id='different Case')),
])
def test_host_rejects_mismatched_saved_evidence(tmp_path, monkeypatch, factory, unit, artifact, change):
    runner, _ = make_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[0]
    runner.run_case(unit, case)
    path = runner.directory / artifact
    value = json.loads(path.read_bytes())
    change(value)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='mismatch'):
        runner._read_result(runner.directory, unit, case, json.loads(case.artifact_path.read_bytes()))


def test_no_isolation_fails_before_factory_import(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'load_factory', lambda ref: pytest.fail('SDK imported before isolation check'))
    assert asyncio.run(worker.execute(tmp_path, tmp_path / 'out', {'mode': 'execute'})) == 1
    assert 'isolated' in (tmp_path / 'out/error.json').read_text()


@pytest.mark.skipif(not os.getenv('ABB_DEFAULT_SDK_IMAGE'), reason='Opt-in local image; no network or credentials')
def test_default_sdk_real_containers(tmp_path, monkeypatch):
    from agentbench.runtime.docker import worker_build
    from agentbench.runtime.docker.evaluation_image import evaluation_image
    from agentbench.runtime.services import RuntimeServices
    image = os.environ['ABB_DEFAULT_SDK_IMAGE']
    subprocess.run(['docker', 'image', 'inspect', image], check=True, capture_output=True)
    monkeypatch.setattr(worker_build, 'stage_adapter_dependencies', lambda *args: None)
    monkeypatch.setattr(worker_build, 'stage_runtime_dependencies', lambda *args: None)
    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'acceptance').mkdir()
    (root / 'acceptance/__init__.py').write_text('')
    (root / 'acceptance/sdk.py').write_bytes((Path(__file__).parent / 'sdk_fixtures/default_sdk.py').read_bytes())
    (root / 'agent/main.py').write_text(
        'from pathlib import Path\nclass Echo:\n'
        ' def __init__(self): self.turns = 0\n'
        ' def invoke(self, value, config=None):\n'
        '  assert not Path("/run/abb-sdk-storage").exists()\n'
        '  assert not Path("/run/abb-output/case.json").exists()\n'
        '  self.turns += 1\n  return f"{value}:{self.turns}"\ngraph = Echo()\n')
    (root / 'agent/langgraph.json').write_text('{"graphs":{"echo":"main.py:graph"}}')
    (root / 'agent.toml').write_text(
        'agent_id="default-sdk-agent"\nframework="langgraph"\n'
        '[runtime]\ntype="docker"\ntimeout_sec=120\nenv_keys=[]\n'
        '[build]\ncontext="."\ndockerfile="Dockerfile"\n'
        '[launch]\nargv = ["python", "-c", "pass"]\nworkdir="/opt/agent"\n'
        '[adapter]\ntype="langgraph"\nconfig="langgraph.json"\ngraph_id="echo"\n')
    (root / 'Dockerfile').write_text(
        f'FROM {image}\nWORKDIR /opt/agent\n'
        'ENV PYTHONPATH=/opt/abb-runtime:/opt/abb-sdk-runtime:/opt/agent\n'
        'COPY .abb-runtime/ /opt/abb-runtime/\nCOPY agent/ ./agent/\n'
        'COPY acceptance/ /opt/abb-sdk-runtime/acceptance/\nCOPY agent.toml ./\nUSER agent\n')
    registration = SimpleNamespace(path=root, agent_id='default-sdk-agent', framework='langgraph', case_count=1)
    requirements = tmp_path / 'requirements.txt'
    requirements.write_text('')
    plugin = ContainerSDKPlugin(create_run='acceptance.sdk:create_run', requirements=requirements)
    monkeypatch.setattr(plugin, 'stage_agent', partial(evaluation_image, requirements=requirements,
        worker_module='agentbench.sdk.integration.worker', install_command=''))
    destination = Path(__file__).resolve().parents[1] / 'results/verification' / ('default-sdk-' + uuid4().hex)
    services = RuntimeServices(environ={})
    context = SDKRunnerContext(environ={}, model=None, trace_sink=None, trace_max_bytes=262144,
        artifacts=FileArtifactStore(destination / 'suite'), runtime_services=services)
    runner = plugin.create_benchmark_runner(context=context, options={'output': destination, 'timeout': 120})
    try:
        cases = runner.prepare_cases(registration)
        result = runner.run_case(registration, cases[0])
        assert result.passed and result.host_acceptance == 'accepted'
        assert [step.payload for step in result.steps] == ['first', 'first:1']
        assert [step.invocation.output for step in result.steps] == ['first:1', 'first:1:2']
        assert cases[0].artifact_path.is_file()
        assert json.loads((runner.directory / 'session.json').read_bytes())['invocations'] == 2
        assert json.loads((runner.directory / 'session.json').read_bytes())['closed'] is True
        assert json.loads((runner.directory / 'run.json').read_bytes())['cleanup_status'] == 'succeeded'
        print('Default SDK acceptance:', runner.directory)
    finally:
        services.close()
