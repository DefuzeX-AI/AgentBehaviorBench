"""Opt-in real containers through the public service and CLI adapters."""
import json
import os
from functools import partial
from pathlib import Path
from uuid import uuid4
import pytest

@pytest.mark.skipif(not os.getenv('ABB_NATIVE_TEST_IMAGE'), reason='Requires local no-KUMA test image')
def test_service_real_containers(monkeypatch, capsys):
    from agentbench.runtime.docker import worker_build
    from agentbench.runtime.docker.evaluation_image import evaluation_image
    from agentbench.sdk.plugin.native.plugin import plugin
    from agentbench.evaluation import EvaluationService
    from agentbench.harness.concurrency import ConcurrencySettings
    from agentbench.cli.main import cli
    image = os.environ['ABB_NATIVE_TEST_IMAGE']
    monkeypatch.setattr(worker_build, 'stage_adapter_dependencies', lambda *args: None)
    monkeypatch.setattr(worker_build, 'stage_runtime_dependencies', lambda *args: None)
    destination = Path(os.getenv('ABB_SERVICE_TEST_ROOT', 'results/verification')) / ('s-' + uuid4().hex[:8])
    destination = destination.resolve()
    destination.mkdir(parents=True)
    root = destination / 'unit'
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
    monkeypatch.setattr(plugin, 'stage_agent', partial(evaluation_image, requirements=plugin.requirements,
        worker_module='agentbench.sdk.integration.worker', install_command=''))
    (root / 'requirement.md').write_text('---\ninput_type: text\n---\nEcho each input exactly.\n')
    (destination / 'resources').mkdir()
    (destination / 'resources/registry.toml').write_text(
        'schema_version="defuzex-bench.registry.v1"\n[[agents]]\nagent_id="native-acceptance"\n'
        'path="unit"\nframework="langgraph"\nstatus="ready"\nenabled=true\ncase=1\n')
    service = EvaluationService(destination, environ={})
    cases = [{'case_id': 'two-turns', 'inputs': [
        {'input_id': 'a', 'payload': 'first'}, {'input_id': 'b', 'payload': 'second'}]}]
    result = service.execute('native-acceptance', cases, timeout=120, concurrency=ConcurrencySettings(1))
    assert result['suite']['counts']['completed'] == 1, result['suite']
    suite, run = result['directory'], result['runs'][0]['id']
    request = service.evidence(suite, run)['request']
    assert [s['result']['output'] for s in request['steps']] == ['first:1', 'second:2']
    path = destination / 'judge.json'
    response = {'schema': 'abb.judge.result.v1', 'request_id': request['request_id'],
        'status': 'issue', 'confidence': 'high', 'reason': 'Echo adds a turn counter.',
        'issues': [{'input_id': 'a', 'message': 'Expected first, received first:1.'}], 'evidence_gaps': []}
    path.write_text(json.dumps(response))
    capsys.readouterr()
    assert cli(['api', '--root', str(destination), 'submit-judge', '--suite', suite,
                '--run-id', run, '--report', str(path)]) == 0
    judged = json.loads(capsys.readouterr().out)
    assert judged['suite']['judge_counts'] == {'issue': 1}
    from tests.test_evaluation_service import install_test_gt
    install_test_gt(service, 'native-acceptance')
    from agentbench.harness.ground_truth import evaluator
    from types import SimpleNamespace
    monkeypatch.setattr(evaluator, '_model', lambda _: SimpleNamespace(model='fixture', base_url='https://example.test'))
    def ask(model, steps, **kwargs):
        evidence = kwargs['payload']['evidence']
        ref = next(k for k in evidence if k.endswith('result.json'))
        if 'report' not in evidence:
            reply = {'conditions': [{'id': 'C1', 'status': 'satisfied',
                'reason': 'Output appends :1.', 'evidence_refs': [ref]}]}
        else:
            assert evidence['report'] == response
            reply = {'detected': True, 'reason': 'Report identifies added counter.', 'evidence_refs': ['report', ref]}
        return reply, json.dumps(reply)
    gt = service.evaluate_gt(suite, ask=ask)
    assert gt['status'] == 'completed' and gt['scores']['discovery_coverage'] == 1
    (destination / 'acceptance.json').write_text(json.dumps(service.result(suite), indent=2))
    print('Service acceptance:', destination)
