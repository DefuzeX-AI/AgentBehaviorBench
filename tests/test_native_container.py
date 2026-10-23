"""Opt-in real Docker acceptance using an image with KUMA absent."""
import json
import os
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest


@pytest.mark.skipif(not os.getenv('ABB_NATIVE_TEST_IMAGE'), reason='Requires local no-KUMA test image')
def test_real_native_containers(tmp_path, monkeypatch):
    from agentbench.runtime.docker import worker_build
    from agentbench.runtime.docker.evaluation_image import evaluation_image
    from agentbench.runtime.services import RuntimeServices
    from agentbench.sdk.contracts import SDKRunnerContext
    from agentbench.sdk.integration.artifacts import FileArtifactStore
    from agentbench.sdk.plugin.native.plugin import plugin
    image = os.environ['ABB_NATIVE_TEST_IMAGE']
    # This prebuilt image contains runtime dependencies; no package downloads.
    monkeypatch.setattr(worker_build, 'stage_adapter_dependencies', lambda *args: None)
    monkeypatch.setattr(worker_build, 'stage_runtime_dependencies', lambda *args: None)
    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'agent/main.py').write_text(
        'import importlib.util\nassert importlib.util.find_spec("kuma") is None\n'
        'class Echo:\n'
        ' def __init__(self): self.turns = 0\n'
        ' def invoke(self, value, config=None):\n'
        '  self.turns += 1\n  return f"{value}:{self.turns}"\ngraph = Echo()\n')
    (root / 'agent/langgraph.json').write_text('{"graphs":{"echo":"main.py:graph"}}')
    (root / 'agent.toml').write_text(
        'agent_id="native-acceptance"\nframework="langgraph"\n'
        '[runtime]\ntype="docker"\ntimeout_sec=120\nenv_keys=[]\n'
        '[build]\ncontext="."\ndockerfile="Dockerfile"\n'
        '[launch]\nargv = ["python","-c","pass"]\nworkdir="/opt/agent"\n'
        '[adapter]\ntype="langgraph"\nconfig="langgraph.json"\ngraph_id="echo"\n')
    (root / 'Dockerfile').write_text(
        f'FROM {image}\nWORKDIR /opt/agent\n'
        'ENV PYTHONPATH=/opt/abb-runtime:/opt/abb-sdk-runtime:/opt/agent\n'
        'COPY .abb-runtime/ /opt/abb-runtime/\nCOPY agent/ ./agent/\nCOPY agent.toml ./\nUSER agent\n')
    registration = SimpleNamespace(path=root, agent_id='native-acceptance', framework='langgraph', case_count=1)
    monkeypatch.setattr(plugin, 'stage_agent', partial(evaluation_image, requirements=plugin.requirements,
        worker_module='agentbench.sdk.integration.worker', install_command=''))
    destination = Path(__file__).resolve().parents[1] / 'results/verification' / ('native-' + uuid4().hex)
    destination.mkdir(parents=True)
    source = destination / 'custom-cases.json'
    source.write_text(json.dumps({'schema': 'abb.cases.v1', 'cases': [{
        'case_id': 'two-turns', 'inputs': [{'input_id': 'a', 'payload': 'first'},
                                         {'input_id': 'b', 'payload': 'second'}]}]}))
    services = RuntimeServices(environ={})
    context = SDKRunnerContext(environ={}, model=None, trace_sink=None, trace_max_bytes=262144,
        artifacts=FileArtifactStore(destination / 'suite'), runtime_services=services)
    runner = plugin.create_benchmark_runner(context=context, options={'output': destination, 'case_file': str(source), 'timeout': 120})
    try:
        case = runner.prepare_cases(registration)[0]
        result = runner.run_case(registration, case)
        assert result.execution_only and result.report is None
        assert [step.invocation.output for step in result.steps] == ['first:1', 'second:2']
        spans = runner.directory / 'evaluation/inputs/0001/spans.jsonl'
        assert spans.read_text().strip()
        request = json.loads((runner.directory / 'evaluation/judge/request.json').read_bytes())
        from agentbench.sdk.judges import execute_judge
        class Judge:
            def judge(self, request, **kwargs):
                assert [s['result']['output'] for s in request['steps']] == ['first:1', 'second:2']
                return {'schema': 'abb.judge.result.v1', 'request_id': request['request_id'],
                        'status': 'pass', 'issues': [], 'evidence_gaps': []}
        assert execute_judge(Judge(), request, directory=runner.directory, environ={}).status == 'pass'
        assert json.loads((runner.directory / 'run.json').read_bytes())['cleanup_status'] == 'succeeded'
        print('Native acceptance artifacts:', runner.directory)
    finally:
        services.close()
