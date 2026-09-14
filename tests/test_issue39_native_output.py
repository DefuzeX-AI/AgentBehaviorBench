"""Issue #39 audit: native public results survive the real KUMA submission path."""
import asyncio
import json

from agentbench.observe.invocation import InvocationObservation
from agentbench.observe.store import json_value
from agentbench.sdk.plugin.kuma.runner import drive_run
from tests.sdk_fixtures.issue_run import sdk_run


def test_structured_native_result_reaches_sdk_without_flattening_or_trace_expansion(tmp_path):
    """Use PyPI KUMA, its immutable history and the production submission loop.

    The native public return includes distinct analysis and decision fields. A
    private diagnostic remains local; retaining a public result must not turn
    every raw/debug field into Agent output or alter the SDK trace allowlist.
    """
    public = {'final_state': {'market_report': 'Observed facts and uncertainty',
                             'final_trade_decision': 'Hold'}, 'decision': 'Hold'}
    native_raw = {'public_result': public, 'diagnostic': 'LOCAL_DIAGNOSTIC_ONLY'}
    folder = tmp_path/'output'
    with sdk_run(tmp_path/'repo', ['{"ticker":"AAPL","date":"2026-09-11"}']) as (run, provider):
        async def invoke(payload, step, shared_provider):
            observed = InvocationObservation(step, 'invoke', run.run_id, 'langgraph', provider=shared_provider)
            observed.store.record('execution_start', input=payload)
            observed.store.record('execution_end', output=public)
            observed.close()
            return json_value({'status': 'succeeded', 'output': public, 'raw_output': native_raw})

        summary = asyncio.run(drive_run(run, invoke, folder, provider=provider))
        assert summary['judge'] == 'received'
        assert summary['submission'] == 'committed'
        assert json_value(run.history[0].submission.output) == public
        stored = json.loads((folder/'inputs/0001/submission.json').read_text())
        assert stored['output'] == public
        assert 'LOCAL_DIAGNOSTIC_ONLY' not in json.dumps(stored)
        assert json.loads((folder/'inputs/0001/result.json').read_text())['raw_output'] == native_raw
        assert (folder/'judge/report.json').is_file()
