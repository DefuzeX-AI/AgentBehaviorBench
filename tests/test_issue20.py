"""Issue #20: a received Judge remains discoverable when the host rejects it."""
import json
from contextlib import contextmanager
from types import SimpleNamespace as NS

import pytest

from agentbench.runtime.contracts.execution import RuntimeLimits, RunControl
from agentbench.sdk.plugin.kuma import service


@pytest.mark.parametrize('foreign', [False, True])
def test_host_rejection_retains_only_matching_report(monkeypatch, tmp_path, foreign):
    root = tmp_path/'source'
    (root/'agent').mkdir(parents=True)
    agent = NS(path=root, agent_id='agent')

    @contextmanager
    def staged(agent, **kw): yield agent

    def reject(checkpoint): raise RuntimeError('host capture rejected')

    def create_runtime(**kw):
        def start(descriptor, *, invocation, **kwargs):
            _, output = invocation
            (output/'judge').mkdir()
            (output/'case.json').write_text(json.dumps({'case_id': 'case-1'}))
            (output/'manifest.json').write_text(json.dumps({'run_id': 'sdk-run', 'case_id': 'case-1', 'judge': 'received'}))
            report = {'report_id': 'report-1', 'run_id': 'wrong-run' if foreign else 'sdk-run',
                      'status': 'issue', 'extensions': {'case_id': 'case-1'}}
            (output/'judge/report.json').write_text(json.dumps(report))
            return NS(stdout='', stderr='', trace_checkpoint=lambda: 0, wait=lambda **kw: 0,
                      validate_trace=reject, close=lambda: None)
        return NS(start=start)

    monkeypatch.setattr(service, 'evaluation_agent', staged)
    with pytest.raises(RuntimeError, match='host capture rejected') as caught:
        service.evaluate(agent, output=tmp_path/'runs', environ={'KUMA_API_KEY': 'not-a-real-key'},
            runtime_services=NS(create_docker_runtime=create_runtime, limits=RuntimeLimits()),
            identity={'case_id': 'case-1', 'job_id': 'job-1'})
    directory, = (tmp_path/'runs').iterdir()
    status = json.loads((directory/'run.json').read_text())
    assert status['status'] == 'failed'
    assert (directory/'evaluation/judge/report.json').is_file()
    retained = status.get('artifacts', {}).get('received_report')
    if foreign:
        assert retained is None
    else:
        assert retained['status'] == 'issue'
        assert retained['host_accepted'] is False
        assert caught.value.artifacts['received_report'] == retained


def test_case_error_exports_retained_report_without_success():
    from agentbench.harness.jobs import CaseJob, SuiteCallbacks, run_case_job
    from agentbench.sdk.contracts import PreparedCase
    from agentbench.cli.result_export import _case_to_json

    artifacts = {'directory': '/runs/host', 'received_report': {'status': 'issue', 'host_accepted': False}}
    def reject(*a, **kw):
        error = RuntimeError('trace rejected')
        error.artifacts = artifacts
        raise error
    job = CaseJob(NS(agent_id='agent'), NS(run_case=reject), PreparedCase(0), {'job_id': 'job', 'agent_id': 'agent'})
    outcome = run_case_job(job, control=RunControl(), bus=NS(publish=lambda *a, **kw: None), callbacks=SuiteCallbacks(total=1))
    data = _case_to_json(outcome.result)
    assert data['status'] == 'failed' and data['benchmark'] is None
    assert data['artifacts'] == artifacts
