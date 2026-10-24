"""Independent SDK acceptance for shared host and worker execution boundaries."""
from contextlib import contextmanager
from dataclasses import replace
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agentbench.harness.result import BenchmarkResult
from agentbench.runtime.contracts.execution import RuntimeLimits
from agentbench.sdk.contracts import PreparedCase
from agentbench.sdk.integration.artifacts import FileArtifactStore
from agentbench.sdk.plugins import evaluation_plan
from agentbench.sdk.runtime import build_evaluation_runner


@contextmanager
def unchanged_stage(agent, *, control, deadline):
    control.check()
    deadline.check()
    yield agent


class IndependentPlugin:
    execution = 'container'

    def create_benchmark_runner(self, *, context, options):
        return IndependentRunner(context, options)


class IndependentRunner:
    def __init__(self, context, options):
        self.context, self.options = context, dict(options)

    def validate_sdk(self, registration):
        return 'independent'

    def prepare_cases(self, registration, **callbacks):
        document = {'case_id': 'independent-case', 'inputs': ['first', 'second'],
                    'expected': ['first:1', 'second:2']}
        content = json.dumps(document).encode()
        path = self.context.artifacts.case(registration.agent_id, 0).publish_case(content)
        digest = hashlib.sha256(content).hexdigest()
        return (PreparedCase(0, document['case_id'], path, digest, digest),)

    def run_case(self, registration, case, **callbacks):
        from agentbench.sdk.integration.execution import run_evaluation
        context = replace(self.context, job_context={'case_index': case.case_index,
                          'case_id': case.case_id, 'attempt_id': 'independent-attempt'})
        self.directory = run_evaluation(
            registration, context=context, output=self.options['output'],
            stage_agent=self.options.get('stage_agent', unchanged_stage),
            settings={'case_file': 'independent/case.json', 'agent_id': registration.agent_id},
            private_directories=('independent',),
            private_files={'independent/case.json': case.artifact_path}, timeout=120)
        status = json.loads((self.directory / 'run.json').read_text())
        assert all(status.get(field) == 'succeeded' for field in (
            'status', 'cleanup_status', 'host_trace_validation')), (
                status, (self.directory / 'diagnostics.json').read_text())
        report = json.loads((self.directory / 'judge/report.json').read_text())
        return BenchmarkResult(registration.agent_id, registration.framework, case.case_id,
                               'completed', SimpleNamespace(**report), (), len(report['outputs']),
                               provider_mode='independent', host_acceptance='accepted',
                               host_trace_validation=status['host_trace_validation'])


def source_agent(tmp_path):
    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'agent/echo.py').write_text('pass\n')
    (root / 'agent.toml').write_text('agent_id="independent-agent"\n')
    return SimpleNamespace(path=root, agent_id='independent-agent', framework='langgraph', case_count=1)


def fake_services(*, reject_trace=False):
    calls = []

    def create_runtime(**options):
        role = 'agent' if options['run_id'].endswith('-agent') else 'controller'
        record = {'role': role, 'options': options, 'validated': [], 'closed': 0}
        calls.append(record)

        def start(agent, *, invocation, **kwargs):
            record.update(invocation=invocation, start_options=kwargs)
            if role == 'controller':
                request, output = invocation
                record['settings'] = json.loads((request / 'evaluation.json').read_text())
                report = output / 'judge/report.json'
                report.parent.mkdir(exist_ok=True)
                report.write_text(json.dumps({'status': 'pass', 'outputs': ['first:1', 'second:2']}))
            def validate(checkpoint):
                record['validated'].append(checkpoint)
                if reject_trace and role == 'agent':
                    raise RuntimeError('Agent evidence rejected')
            def close():
                record['closed'] += 1
            return SimpleNamespace(stdout='', stderr='', wait=lambda **kw: 0,
                                   trace_checkpoint=lambda: role, validate_trace=validate, close=close)
        return SimpleNamespace(start=start)
    return SimpleNamespace(create_docker_runtime=create_runtime, limits=RuntimeLimits()), calls


def make_runner(tmp_path, services, **options):
    store = FileArtifactStore(tmp_path / 'suite')
    return build_evaluation_runner(evaluation_plan(sdk=IndependentPlugin(), options={'output': tmp_path, **options}),
        model=None, trace_sink=None, trace_max_bytes=1024, environ={},
        artifacts=store, runtime_services=services)


def test_independent_sdk_uses_shared_host_and_private_case_storage(tmp_path):
    agent = source_agent(tmp_path)
    services, calls = fake_services()
    runner = make_runner(tmp_path, services)
    case, = runner.prepare_cases(agent)
    result = runner.run_case(agent, case)
    assert result.passed
    controller = next(call for call in calls if call['role'] == 'controller')
    endpoint = next(call for call in calls if call['role'] == 'agent')
    assert controller['settings']['isolated_agent'] is True
    assert controller['settings']['case_file'] == 'independent/case.json'
    assert (runner.directory / 'sdk-repo/independent/case.json').read_bytes() == case.artifact_path.read_bytes()
    assert '/run/abb-sdk-storage' in str(controller['options']['policy'].run_arguments())
    assert '/run/abb-sdk-storage' not in str(endpoint['options']['policy'].run_arguments())
    assert endpoint['start_options']['argv'][-1] == 'agentbench.runtime.agentcontainer.channel'
    assert all(call['closed'] == 1 and call['validated'] == [call['role']] for call in calls)
    status = json.loads((runner.directory / 'run.json').read_text())
    assert (status['status'], status['cleanup_status'], status['host_trace_validation']) == (
        'succeeded', 'succeeded', 'succeeded')


def test_shared_host_cleans_both_sessions_when_agent_evidence_is_rejected(tmp_path):
    agent = source_agent(tmp_path)
    services, calls = fake_services(reject_trace=True)
    runner = make_runner(tmp_path, services)
    case, = runner.prepare_cases(agent)
    with pytest.raises(RuntimeError, match='Agent evidence rejected'):
        runner.run_case(agent, case)
    assert all(call['closed'] == 1 for call in calls)
    directory = runner.context.artifacts.case(agent.agent_id, 0).attempt('independent-attempt').directory
    status = json.loads((directory / 'run.json').read_text())
    assert status['status'] == 'failed' and status['cleanup_status'] == 'succeeded'
    assert status['host_trace_validation'] == 'failed'
    assert (directory / 'judge/report.json').is_file()


def test_shared_host_imports_without_vendor_sdk():
    script = '''
import importlib.abc, sys
class RejectVendor(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'kuma' or fullname.startswith(('kuma.', 'agentbench.sdk.plugin.kuma')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, RejectVendor())
from agentbench.sdk.integration.execution import run_evaluation
from agentbench.sdk.integration.agent import ManagedAgentSession
from agentbench.runtime.docker.evaluation_image import evaluation_image
assert callable(run_evaluation) and callable(ManagedAgentSession) and callable(evaluation_image)
'''
    subprocess.run([sys.executable, '-c', script], check=True, capture_output=True, text=True)


@pytest.mark.skipif(not os.getenv('ABB_INDEPENDENT_SDK_IMAGE'), reason='Opt-in existing local image, offline only')
def test_independent_sdk_real_container_retains_case_output_and_judge(tmp_path, monkeypatch):
    from agentbench.runtime.docker import worker_build
    from agentbench.runtime.docker.evaluation_image import evaluation_image
    from agentbench.runtime.services import RuntimeServices
    image = os.environ['ABB_INDEPENDENT_SDK_IMAGE']
    # Inspect before building: an absent image fails without implicitly pulling it.
    subprocess.run(['docker', 'image', 'inspect', image], check=True, capture_output=True)
    monkeypatch.setattr(worker_build, 'stage_adapter_dependencies', lambda *args: None)
    monkeypatch.setattr(worker_build, 'stage_runtime_dependencies', lambda *args: None)
    agent = source_agent(tmp_path)
    root = agent.path
    (root / 'acceptance').mkdir()
    (root / 'acceptance/__init__.py').write_text('')
    (root / 'acceptance/worker.py').write_bytes(
        (Path(__file__).parent / 'sdk_fixtures/independent_worker.py').read_bytes())
    (root / 'agent/echo.py').write_text(
        'from pathlib import Path\n'
        'class Echo:\n'
        ' def __init__(self): self.turns = 0\n'
        ' def invoke(self, value, config=None):\n'
        '  assert not Path("/run/abb-sdk-storage").exists()\n'
        '  assert not Path("/run/abb-output/case.json").exists()\n'
        '  self.turns += 1\n'
        '  return f"{value}:{self.turns}"\n'
        'graph = Echo()\n')
    (root / 'agent/langgraph.json').write_text('{"graphs":{"echo":"echo.py:graph"}}')
    (root / 'agent.toml').write_text(
        'agent_id="independent-agent"\nframework="langgraph"\n'
        '[runtime]\ntype="docker"\ntimeout_sec=120\nenv_keys=[]\n'
        '[build]\ncontext="."\ndockerfile="Dockerfile"\n'
        '[launch]\nargv = ["python","-m","acceptance.worker"]\nworkdir="/opt/agent"\n'
        '[adapter]\ntype="langgraph"\nconfig="langgraph.json"\ngraph_id="echo"\n')
    (root / 'Dockerfile').write_text(
        f'FROM {image}\nWORKDIR /opt/agent\n'
        'ENV PYTHONPATH=/opt/abb-runtime:/opt/abb-sdk-runtime:/opt/agent\n'
        'COPY .abb-runtime/ /opt/abb-runtime/\n'
        'COPY agent/ ./agent/\nCOPY acceptance/ /opt/abb-sdk-runtime/acceptance/\n'
        'COPY agent.toml ./\nUSER agent\n')
    original_manifest = (root / 'agent.toml').read_bytes()
    original_dockerfile = (root / 'Dockerfile').read_bytes()
    requirements = tmp_path / 'requirements.txt'
    requirements.write_text('')
    stage_agent = partial(evaluation_image, requirements=requirements,
                          worker_module='acceptance.worker', install_command='')
    destination = Path(__file__).resolve().parents[1] / 'results/verification' / ('independent-sdk-' + uuid4().hex)
    services = RuntimeServices(environ={})
    runner = make_runner(destination, services, stage_agent=stage_agent)
    try:
        case, = runner.prepare_cases(agent)
        result = runner.run_case(agent, case)
        assert result.passed
        evaluation = runner.directory
        report = json.loads((evaluation / 'judge/report.json').read_text())
        assert report['outputs'] == ['first:1', 'second:2']
        assert json.loads((evaluation / 'case.json').read_text()) == json.loads(case.artifact_path.read_text())
        assert json.loads((evaluation / 'session.json').read_text())['invocations'] == 2
        verification = json.loads((evaluation / 'verification.json').read_text())
        assert verification['vendor_imported'] is False and verification['span_count'] > 0
        assert json.loads((runner.directory / 'run.json').read_text())['cleanup_status'] == 'succeeded'
        assert (root / 'agent.toml').read_bytes() == original_manifest
        assert (root / 'Dockerfile').read_bytes() == original_dockerfile
        print('Independent SDK acceptance:', runner.directory)
    finally:
        services.close()
