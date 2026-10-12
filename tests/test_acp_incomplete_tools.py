"""Missing native tool outcomes remain visible without losing a captured Case."""
import json
from agentbench.observe.invocation import InvocationObservation
from tests.sdk_fixtures.issue_run import sdk_run


def test_prompt_boundary_closes_observation_without_inventing_tool_success(tmp_path):
    with sdk_run(tmp_path / 'repo', ['task']) as (run, provider):
        run.get_input()
        observed = InvocationObservation(tmp_path / 'trace', 'inv', run.run_id, 'acp', provider=provider)
        observed.store.record('execution_start', input='task')
        callback = observed.callbacks[0]
        callback.on_acp_event('session_update', {'update': {'sessionUpdate': 'tool_call',
            'toolCallId': 't1', 'title': 'write_file', 'status': 'in_progress', 'rawInput': {'path': 'note'}}})
        callback.on_acp_event('prompt_completed', {'stopReason': 'end_turn'})
        observed.store.record('execution_end', output='done')
        observed.close()
        status = json.loads((tmp_path / 'trace/otel-status.json').read_text())
        assert status['status'] == 'complete'
        summary = json.loads((tmp_path / 'trace/acp-summary.json').read_text())
        assert summary['incomplete_tools'] == ['t1']
        spans = [json.loads(line)['data'] for line in (tmp_path / 'trace/otel.jsonl').read_text().splitlines()]
        tool = next(s for s in spans if s['attributes'].get('abb.kind') == 'tool')
        assert 'gen_ai.tool.call.result' not in tool['attributes']
        assert tool['attributes']['abb.control_flow'] == 'acp_outcome_not_observed'
        assert tool['status']['status_code'] != 'OK'
        run.submit(output='done')
        evidence = run.history[0].submission.extensions['trace_evidence']
        assert any(s.get('tool_content_status', {}).get('result') != 'present' for s in evidence['spans'])
