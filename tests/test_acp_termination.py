"""A terminal ACP step stops the Case without manufacturing later failures."""
import asyncio
import json
from agentbench.sdk.plugin.kuma.runner import drive_run
from agentbench.sdk.plugin.kuma.compatibility import run_case
from tests.sdk_fixtures.issue_run import sdk_run


def test_native_failure_stops_and_judges_committed_prefix(tmp_path):
    called = []
    async def invoke(payload, folder, provider):
        called.append(payload)
        (folder / 'otel-status.json').write_text('{"status":"complete"}')
        return {'status': 'aborted', 'error_type': 'AgentAborted',
                'error': 'Native prompt cancelled', 'session_usable': False}
    with sdk_run(tmp_path / 'repo', ['first', 'second', 'third'], on_failure='stop') as (run, provider):
        case = run_case(run)
        output = tmp_path / 'evaluation'
        output.mkdir()
        (output / 'case.json').write_text(json.dumps(case))
        summary = asyncio.run(drive_run(run, invoke, output, provider=provider))
        assert called == ['first']
        assert summary['judge'] == 'received'
        assert summary['termination']['input_id'] == 'input-0'
        assert summary['unexecuted_inputs'] == ['input-1', 'input-2']
        assert len(run.history) == 1
        assert run.history[0].submission.status == 'aborted'
