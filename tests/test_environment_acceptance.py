"""Opt-in acceptance through the actual DockerRuntime and pinned SDK worker."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agentbench.runtime.docker.runtime import DockerRuntime
from tests.test_kuma_requirement import REQUIREMENT


@pytest.mark.skipif(not os.getenv('ABB_ENVIRONMENT_BASE_IMAGE'), reason='Opt-in pinned SDK Docker image')
@pytest.mark.parametrize('workspace', [False, True])
def test_environment_reaches_case_generation_and_execution(tmp_path, workspace):
    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'agent/echo.py').write_text(
        'class Echo:\n    def invoke(self, value, config=None):\n        return value\ngraph = Echo()\n')
    (root / 'agent/langgraph.json').write_text('{"graphs":{"echo":"echo.py:graph"}}')
    (root / 'agent.toml').write_text(
        'agent_id="environment-acceptance"\nframework="langgraph"\n'
        '[runtime]\ntype="docker"\ntimeout_sec=60\nenv_keys=["KUMA_API_KEY"]\n'
        '[build]\ncontext="."\ndockerfile="Dockerfile"\n'
        '[launch]\nargv=["python", "/opt/agent/check.py"]\nworkdir="/opt/agent"\n'
        '[adapter]\ntype="langgraph"\nconfig="langgraph.json"\ngraph_id="echo"\n')
    policy_options = {}
    if workspace:
        from agentbench.sdk.plugin.kuma.service import EvaluationPolicy
        with (root / 'agent.toml').open('a') as manifest:
            manifest.write('[evaluation.workspace]\npath="/home/agent/workspace"\ninitial_state="empty"\n')
        task_directory = tmp_path / 'workspace'
        task_directory.mkdir()
        ledger = tmp_path / 'ledger'
        ledger.mkdir()
        policy_options['policy'] = EvaluationPolicy(ledger, repository=task_directory,
                                                   target='/home/agent/workspace', writable=True)
    (root / 'requirement.md').write_text(REQUIREMENT)
    (root / 'check.py').write_bytes((Path(__file__).parent / 'sdk_fixtures/environment_check.py').read_bytes())
    (root / 'Dockerfile').write_text(
        f'FROM {os.environ["ABB_ENVIRONMENT_BASE_IMAGE"]}\nWORKDIR /opt/agent\n'
        'ENV PYTHONPATH=/opt/abb-environment-runtime\nCOPY .abb-runtime/ /opt/abb-environment-runtime/\n'
        'COPY agent/ ./agent/\nCOPY agent.toml requirement.md check.py ./\nUSER agent\n')
    output = Path(__file__).parents[1] / 'results/verification' / f'execution-environment-{uuid4().hex}'
    inputs = output / 'request'
    inputs.mkdir(parents=True)
    (inputs / 'evaluation.json').write_text('{"mode":"generate","count":1,"max_steps":1}')
    runtime = DockerRuntime(environ={'KUMA_API_KEY': 'offline-not-sent'}, artifact_root=output, **policy_options)
    session = runtime.start(SimpleNamespace(path=root, agent_id='environment-acceptance'), invocation=(inputs, output))
    try:
        code = session.wait(timeout=90)
        (output / 'container.log').write_text(session.stdout + session.stderr)
        assert code == 0, f'See {output}/container.log'
    finally:
        session.close()
    facts = json.loads((output / 'generation/execution-environment.json').read_text())
    assert facts['runtime'] == 'docker' and facts['process']['uid'] == 10001
    assert facts['limits']['timeout_seconds'] == 60
    assert (facts['workspace'] is not None) is workspace
    assert str(root) not in json.dumps(facts)
    assert (output / 'execution/case.json').is_file()
    assert (output / 'execution/inputs/0001/result.json').is_file()
    assert (output / 'execution/judge/report.json').is_file()
    print(f'Acceptance artifacts: {output}')
