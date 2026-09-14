"""KUMA package installation belongs to its plugin, not a local source checkout."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agentbench.cli.main import build_parser
from agentbench.harness.errors import ProviderSelectionError
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.docker.image_builder import DockerImageBuilder
from agentbench.runtime.docker.policy import DockerPolicy
from agentbench.runtime.docker.worker_build import worker_build_context
from agentbench.sdk import discover_sdks, resolve_sdk
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.plugin.kuma.image import evaluation_agent
from agentbench.sdk.common.case_identity import case_content_sha256


@pytest.fixture
def echo_agent(tmp_path):
    root = tmp_path / 'echo-agent'
    (root / 'agent').mkdir(parents=True)
    (root / 'agent' / 'main.py').write_text('print("echo")\n')
    (root / 'evaluation').mkdir()
    (root / 'evaluation' / 'profile.md').write_text('Offline profile fixture\n')
    (root / 'evaluation' / 'input-contract.json').write_text('{"encoding":"identity"}')
    (root / 'agent.toml').write_text(
        'agent_id = "kuma-pypi-echo"\nframework = "fixture"\n'
        '[runtime]\ntype = "docker"\ntimeout_sec = 60\n'
        '[build]\ncontext = "."\ndockerfile = "Dockerfile"\n'
        '[launch]\nargv = ["python", "/opt/agent/agent/main.py"]\n')
    (root / 'Dockerfile').write_text('FROM python:3.11-slim\nUSER agent\n')
    return SimpleNamespace(path=root, agent_id='kuma-pypi-echo', framework='fixture', case_count=1)


def test_kuma_is_only_available_at_its_new_plugin_path():
    reference = resolve_sdk('kuma').reference
    assert reference.object_ref == 'agentbench.sdk.plugin.kuma.plugin:plugin'
    assert 'kuma' in {item.name for item in discover_sdks()}
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module('agentbench.sdk.kuma')


def test_overlay_installs_pypi_requirements_without_sdk_source(echo_agent):
    original_manifest = (echo_agent.path / 'agent.toml').read_bytes()
    original_dockerfile = (echo_agent.path / 'Dockerfile').read_bytes()
    with evaluation_agent(echo_agent) as staged:
        dockerfile = (staged.path / 'Dockerfile').read_text()
        assert '--index-url https://pypi.org/simple' in dockerfile
        assert 'python -m pip --isolated install' in dockerfile
        assert '-r /opt/abb-sdk/requirements.txt' in dockerfile
        assert dockerfile.rstrip().endswith('USER agent')
        requirements = staged.path / '.abb-sdk/requirements.txt'
        assert 'kuma-defuzex[otel]==' in requirements.read_text()
        assert {item.name for item in requirements.parent.iterdir()} == {'requirements.txt'}
        assert 'agentbench.sdk.plugin.kuma.worker' in (staged.path / 'agent.toml').read_text()
        assert not (staged.path / '.abb-sdk/src').exists()
        assert (staged.path / 'agent/.gitignore').read_text().strip() == '/.kuma/'
    assert (echo_agent.path / 'agent.toml').read_bytes() == original_manifest
    assert (echo_agent.path / 'Dockerfile').read_bytes() == original_dockerfile
    assert not (echo_agent.path / '.abb-sdk').exists()
    assert not (echo_agent.path / 'agent/.gitignore').exists()


def test_preflight_does_not_require_host_sdk_checkout_or_import(echo_agent, monkeypatch):
    import builtins
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == 'kuma' or name.startswith('kuma.'):
            pytest.fail('Host preflight must not import the container SDK')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline-not-used'})
    assert runner.validate_sdk(echo_agent) == 'official-container'
    assert not hasattr(runner, 'sdk')


def test_old_sdk_source_option_and_cli_flag_are_removed():
    with pytest.raises(ProviderSelectionError, match='sdk_source'):
        KumaContainerRunner(options={'sdk_source': '/old/checkout'})
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(['evaluate', '--sdk-source', '/old/checkout'])
    assert error.value.code == 2


def test_kuma_factory_isolates_case_state_and_forwards_shared_control(echo_agent):
    from agentbench.runtime.contracts.execution import RunControl
    from agentbench.sdk.plugins import evaluation_plan
    from agentbench.sdk.runtime import build_evaluation_runner_factory

    factory = build_evaluation_runner_factory(
        evaluation_plan(selection=resolve_sdk('kuma')), model='test-model',
        trace_sink=None, trace_max_bytes=1024, environ={'KUMA_API_KEY': 'offline'},
    )
    assert factory.supports_concurrency is True
    control = RunControl()
    suite = factory.open_suite('suite-one', control)
    first = suite.create(echo_agent, {'job_id': 'first', 'registration_index': 0})
    second = suite.create(echo_agent, {'job_id': 'second', 'registration_index': 1})
    assert first is not second
    assert callable(first.prepare_cases) and callable(first.run_case)
    assert not hasattr(first, 'run')
    assert not hasattr(first, '_case_batches')
    assert not hasattr(first, '_case_fingerprints')
    assert first.control is second.control is control
    assert first.runtime_services is second.runtime_services
    assert first.environ == {'KUMA_API_KEY': 'offline', 'OPENROUTER_MODEL': 'test-model'}
    first.environ['OPENROUTER_MODEL'] = 'modified'
    assert second.environ['OPENROUTER_MODEL'] == 'test-model'
    suite.close()


def test_cancelled_kuma_job_never_starts_generation(echo_agent, monkeypatch):
    from agentbench.runtime.contracts.execution import RunCancelled, RunControl

    control = RunControl()
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}, control=control)
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate',
                        lambda *a, **kw: pytest.fail('Cancelled job must not create a container'))
    control.cancel()
    with pytest.raises(RunCancelled):
        runner.prepare_cases(echo_agent)


def case_collection(directory, count=2):
    cases = directory / 'cases'
    cases.mkdir(parents=True)
    collection = {'schema': 'abb.case_collection.v2', 'requested_count': count, 'cases': []}
    for index in range(count):
        case = {'case_id': f'case-{index}', 'inputs': [
            {'input_id': 'input-1', 'payload_type': 'text', 'payload': f'marker-{index}'}]}
        artifact = {'schema_version': 'kuma.case_artifact.v1', 'origin': 'custom', 'case': case}
        name = f'case-{index}.json'
        (cases / name).write_text(json.dumps(artifact))
        collection['cases'].append({'case_id': case['case_id'], 'artifact': f'.kuma/{name}',
                                    'content_sha256': case_content_sha256(case)})
    path = directory / 'case-collection.json'
    path.write_text(json.dumps(collection))
    return path


def test_kuma_prepares_immutable_complete_batch_without_host_sdk_import(echo_agent, tmp_path, monkeypatch):
    collection = case_collection(tmp_path / 'import')
    echo_agent.case_count = 2
    import builtins
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == 'kuma' or name.startswith('kuma.'):
            pytest.fail('Preparation must not import the container SDK')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}, options={
        'output': tmp_path / 'output', 'case_collection': collection})
    prepared = runner.prepare_cases(echo_agent)
    assert isinstance(prepared, tuple)
    assert [case.case_index for case in prepared] == [0, 1]
    assert [case.case_id for case in prepared] == ['case-0', 'case-1']
    for case in prepared:
        assert case.artifact_path.is_absolute()
        assert case.artifact_path.is_file()
        assert case.artifact_sha256 == hashlib.sha256(case.artifact_path.read_bytes()).hexdigest()
    with pytest.raises(FrozenInstanceError):
        prepared[0].case_index = 2
    assert not hasattr(runner, '_case_batches')


def test_kuma_generation_prepares_entire_selection_in_one_session(echo_agent, tmp_path, monkeypatch):
    echo_agent.case_count = 2
    generation_calls = []
    generated = tmp_path / 'generated'
    def evaluate(agent, **kwargs):
        generation_calls.append(kwargs['generation_count'])
        assert kwargs['identity']['case_index'] is None
        case_collection(generated / 'evaluation', count=kwargs['generation_count'])
        (generated / 'run.json').write_text(json.dumps({'status': 'succeeded'}))
        return generated
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate', evaluate)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'})
    prepared = runner.prepare_cases(echo_agent)
    assert generation_calls == [2]
    assert [case.case_id for case in prepared] == ['case-0', 'case-1']


@pytest.mark.parametrize('duplicate', ['case_id', 'content_sha256', 'artifact'])
def test_kuma_rejects_batch_duplicates_before_execution(echo_agent, tmp_path, monkeypatch, duplicate):
    collection_path = case_collection(tmp_path / 'import')
    collection = json.loads(collection_path.read_text())
    collection['cases'][1][duplicate] = collection['cases'][0][duplicate]
    collection_path.write_text(json.dumps(collection))
    echo_agent.case_count = 2
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate',
                        lambda *a, **kw: pytest.fail('A rejected import must not start a container'))
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}, options={
        'output': tmp_path / 'output', 'case_collection': collection_path})
    with pytest.raises(ValueError, match='duplicate'):
        runner.prepare_cases(echo_agent)
    status_path, = (tmp_path / 'output').glob('*/run.json')
    assert json.loads(status_path.read_text())['validation'] == 'failed'


def test_kuma_rejects_modified_wire_artifact_before_creating_run(echo_agent, tmp_path, monkeypatch):
    source = case_collection(tmp_path / 'import', count=1)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}, options={
        'output': tmp_path / 'output', 'case_collection': source})
    prepared, = runner.prepare_cases(echo_agent)
    prepared.artifact_path.chmod(0o644)
    prepared.artifact_path.write_text('{}')
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate',
                        lambda *a, **kw: pytest.fail('Modified artifacts must not create a remote Run'))
    with pytest.raises(ValueError, match='modified'):
        runner.run_case(echo_agent, prepared)


def write_completed_case(directory, agent_id, case):
    from agentbench.sdk.common.artifacts import Artifacts

    files = Artifacts(directory, environ={})
    run_id = f"sdk-{case['case_id']}"
    files.save('run.json', {'run_id': directory.name, 'agent_id': agent_id, 'status': 'succeeded'})
    files.save('evaluation/case.json', case)
    files.save('evaluation/manifest.json', {
        'run_id': run_id, 'case_id': case['case_id'], 'execution': 'succeeded', 'otel': 'complete',
        'submission': 'committed', 'evidence': 'captured', 'judge': 'received', 'phase': 'finished',
        'steps': [{'input_id': 'input-1', 'directory': 'inputs/0001', 'committed': True}]})
    files.save('evaluation/judge/report.json', {'run_id': run_id, 'report_id': 'report',
        'status': 'pass', 'extensions': {'case_id': case['case_id']}})
    item = case['inputs'][0]
    prefix = 'evaluation/inputs/0001/'
    files.save(prefix + 'input.json', item)
    files.save(prefix + 'result.json', {'schema': 'abb.result.v1', 'status': 'succeeded',
        'agent_id': agent_id, 'run_id': 'invocation', 'output': item['payload']})
    files.save(prefix + 'request.json', {'agent_id': agent_id, 'run_id': 'invocation', 'session_id': run_id})
    files.save(prefix + 'submission.json', {'status': 'completed', 'output': item['payload']})
    files.save(prefix + 'otel-status.json', {'status': 'complete'})
    files.save(prefix + 'evidence.json', {'spans': ['span']})


def test_independent_kuma_runners_execute_explicit_cases_concurrently(echo_agent, tmp_path, monkeypatch):
    echo_agent.case_count = 2
    source = case_collection(tmp_path / 'import')
    preparer = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}, options={
        'output': tmp_path / 'output', 'case_collection': source})
    prepared = preparer.prepare_cases(echo_agent)
    rendezvous = threading.Barrier(2)
    identities = []
    def evaluate(agent, **kwargs):
        assert 'generation_count' not in kwargs
        case = json.loads(kwargs['case_artifact'].read_text())['case']
        identities.append(kwargs['identity'])
        directory = tmp_path / 'executed' / uuid4().hex
        write_completed_case(directory, agent.agent_id, case)
        kwargs['on_artifacts_ready'](directory)
        rendezvous.wait(timeout=3)
        return directory
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate', evaluate)
    runners = [KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'},
        job_context={'suite_id': 'suite', 'job_id': f'job-{i}'}) for i in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(runners[index].run_case, echo_agent, prepared[case_index])
                   for index, case_index in enumerate((1, 0))]
        results = [future.result() for future in futures]
    assert [result.steps[0].invocation.output for result in results] == ['marker-1', 'marker-0']
    assert {identity['case_index'] for identity in identities} == {0, 1}
    assert len({result.report.extensions['abb_artifact_directory'] for result in results}) == 2


def test_kuma_checks_executed_content_against_prepared_identity(echo_agent, tmp_path, monkeypatch):
    source = case_collection(tmp_path / 'import', count=1)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}, options={
        'output': tmp_path / 'output', 'case_collection': source})
    prepared, = runner.prepare_cases(echo_agent)
    directory = tmp_path / 'executed'
    def evaluate(agent, **kwargs):
        case = json.loads(kwargs['case_artifact'].read_text())['case']
        case['inputs'][0]['payload'] = 'unexpected-but-internally-consistent'
        write_completed_case(directory, agent.agent_id, case)
        return directory
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate', evaluate)
    with pytest.raises(RuntimeError, match='content does not match'):
        runner.run_case(echo_agent, prepared)
    assert json.loads((directory / 'run.json').read_text())['validation'] == 'failed'


@pytest.mark.parametrize('cleanup_failure', [False, True])
def test_service_retains_identity_trace_and_diagnostics_on_cleanup_failure(
    echo_agent, tmp_path, monkeypatch, capsys, cleanup_failure,
):
    from agentbench.runtime.contracts.execution import DockerCleanupError, RunControl
    from agentbench.runtime.interception import TraceEvent
    from agentbench.sdk.plugin.kuma import service

    @contextmanager
    def staged(agent, **kwargs):
        kwargs['control'].check()
        yield agent

    emitted = []
    session = SimpleNamespace(
        stdout='stdout evidence', stderr='stderr evidence',
        trace_checkpoint=lambda: 0, validate_trace=lambda checkpoint: None,
    )
    def close():
        if cleanup_failure:
            raise DockerCleanupError('container fixture still exists')
    session.close = close
    session.wait = lambda **kwargs: 0
    runtime_options = []

    def runtime(**kwargs):
        runtime_options.append(kwargs)
        def start(agent, *, invocation, preparation_deadline):
            preparation_deadline.check()
            event = TraceEvent('llm_response', {
                'call_id': 'shared-call-id', 'agent_id': 'untrusted-agent',
                'payload': {'output_text': 'secret-snapshot ' + 'x' * 2000},
            })
            kwargs['trace_sink'].emit(event)
            return session
        return SimpleNamespace(start=start)

    monkeypatch.setattr(service, 'evaluation_agent', staged)
    monkeypatch.setenv('KUMA_API_KEY', 'different-process-secret')
    control = RunControl()
    from agentbench.runtime.contracts.execution import RuntimeLimits
    services = SimpleNamespace(create_docker_runtime=runtime, limits=RuntimeLimits())
    output = tmp_path / 'output'
    parameters = dict(
        output=output, environ={'KUMA_API_KEY': 'secret-snapshot'},
        control=control, runtime_services=services,
        identity={'suite_id': 'suite', 'job_id': 'job', 'case_index': 1, 'case_id': 'case'},
        trace_sink=SimpleNamespace(emit=emitted.append),
    )
    if cleanup_failure:
        with pytest.raises(DockerCleanupError):
            service.evaluate(echo_agent, **parameters)
    else:
        service.evaluate(echo_agent, **parameters)
    directory, = output.iterdir()
    status = json.loads((directory / 'run.json').read_text())
    assert status['job_id'] == 'job' and status['suite_id'] == 'suite'
    assert status['artifact_run_id'] == status['run_id'] == directory.name
    assert status['case_id'] == 'case' and status['case_index'] == 1
    assert status['cleanup_status'] == ('failed' if cleanup_failure else 'succeeded')
    assert status['status'] == ('failed' if cleanup_failure else 'succeeded')
    diagnostics = json.loads((directory / 'diagnostics.json').read_text())
    assert diagnostics['stdout'] == 'stdout evidence'
    assert runtime_options[0]['control'] is control
    trace = json.loads((directory / 'network.jsonl').read_text())
    assert trace['data']['agent_id'] == echo_agent.agent_id
    assert trace['data']['payload']['output_text'].endswith('x' * 2000)
    assert 'secret-snapshot' not in json.dumps(trace)
    assert emitted[0].data['job_id'] == 'job'
    assert emitted[0].data['agent_id'] == echo_agent.agent_id
    assert len(emitted[0].data['payload']['output_text']) < 600
    assert 'secret-snapshot' not in str(emitted[0].data)
    assert capsys.readouterr().out == ''


@pytest.mark.skipif(not os.getenv('ABB_KUMA_PYPI_BASE_IMAGE'), reason='Opt-in real PyPI image build')
def test_real_pypi_overlay_and_offline_case_judge(echo_agent):
    """Build the actual overlay, then run the real PyPI SDK without network."""
    base = os.environ['ABB_KUMA_PYPI_BASE_IMAGE']
    # Use an existing image with Python and an unprivileged agent user. A fresh
    # runtime path prevents old code in that image from hiding migration errors.
    (echo_agent.path / 'Dockerfile').write_text(
        f'FROM {base}\nWORKDIR /opt/agent\n'
        'ENV PYTHONPATH=/opt/abb-current-runtime\n'
        'COPY .abb-runtime/ /opt/abb-current-runtime/\n'
        'COPY agent/ /opt/agent/agent/\n'
        'COPY agent.toml /opt/agent/agent.toml\nUSER agent\n')
    output = Path(__file__).resolve().parents[1] / 'results/verification' / f'kuma-pypi-{uuid4().hex}'
    output.mkdir(parents=True)
    with evaluation_agent(echo_agent) as staged:
        config = AgentContainerConfig.from_agent_dir(
            staged.path, secret_resolver=EnvironmentSecretResolver({}), environ={})
        assert config.argv[-1] == 'agentbench.sdk.plugin.kuma.worker'
        assert config.environment == {}
        (output / 'Dockerfile').write_text((staged.path / 'Dockerfile').read_text())
        requirements = (staged.path / '.abb-sdk/requirements.txt').read_text()
        (output / 'requirements.txt').write_text(requirements)
        with worker_build_context(config) as (context, dockerfile):
            assert (context / '.abb-runtime/agentbench/sdk/plugin/kuma/requirements.txt').is_file()
            assert not (context / '.abb-runtime/agentbench/sdk/kuma').exists()
            image = DockerImageBuilder().build(context=context, dockerfile=dockerfile,
                                              repository='kuma-pypi-acceptance')
    print(f'Built PyPI evaluation image: {image}', flush=True)
    fixtures = (Path(__file__).parent / 'sdk_fixtures').resolve()
    result = subprocess.run([
        'docker', 'run', '--rm', '--network', 'none', '--user', '10001:10001',
        *DockerPolicy().run_arguments(), '--env', 'PYTHONDONTWRITEBYTECODE=1',
        '--env', 'KUMA_API_KEY=', '--env', 'DEFUZEX_API_KEY=',
        '--mount', f'type=bind,source={fixtures},target=/checks,readonly',
        '--mount', f'type=bind,source={output},target=/artifacts',
        '--entrypoint', 'python', image, '/checks/pypi_check.py',
    ], capture_output=True, text=True, timeout=60)
    (output / 'container.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    assert result.returncode == 0, f'See {output / "container.log"}'
    package = json.loads((output / 'package.json').read_text())
    expected_version = next(line.split('==', 1)[1] for line in requirements.splitlines()
                            if line.startswith('kuma-defuzex'))
    assert package['version'] == expected_version
    assert package['adapter'] == 'agentbench.sdk.plugin.kuma.plugin:plugin'
    assert package['runtime'].startswith('/opt/abb-current-runtime/')
    run = json.loads((output / 'run.json').read_text())
    assert run['report']['status'] == 'pass'
    assert run['sdk_version'] == expected_version
    for name in ('case.json', 'agent-output.json', 'judge.json'):
        assert (output / name).is_file()
    (output / 'verification.json').write_text(json.dumps({
        'status': 'passed', 'image': image, 'package': package,
        'dependency_source': 'https://pypi.org/simple', 'execution_network': 'none',
        'providers': 'offline-custom', 'production_services_called': False,
    }, indent=2))
    print(f'PyPI acceptance artifacts retained: {output}', flush=True)
