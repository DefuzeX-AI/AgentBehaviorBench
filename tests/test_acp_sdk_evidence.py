"""ACP stream notifications must not exhaust the SDK's span event budget."""
import json

from agentbench.observe.invocation import InvocationObservation
from tests.sdk_fixtures.issue_run import sdk_run


def test_stream_updates_keep_local_evidence_without_exhausting_sdk_events(tmp_path):
    with sdk_run(tmp_path / 'repo', ['Inspect the workspace']) as (run, provider):
        run.get_input()
        folder = tmp_path / 'observation'
        observed = InvocationObservation(folder, 'invoke', run.run_id, 'acp', provider=provider)
        observed.store.record('execution_start', input='Inspect the workspace')
        callback = observed.callbacks[0]
        callback.on_acp_event('prompt_started', {'text': 'Inspect the workspace'})
        for _ in range(300):
            callback.on_acp_event('session_update', {'update': {
                'sessionUpdate': 'agent_message_chunk',
                'content': {'type': 'text', 'text': 'chunk'},
            }})
        callback.on_acp_event('session_update', {'update': {
            'sessionUpdate': 'tool_call', 'toolCallId': 'tool-1',
            'title': 'bash', 'kind': 'execute',
        }})
        callback.on_acp_event('session_update', {'update': {
            'sessionUpdate': 'tool_call_update', 'toolCallId': 'tool-1',
            'status': 'completed', 'rawInput': {'command': 'pwd'},
            'rawOutput': {'stdout': '/workspace', 'exit_code': 0},
        }})
        callback.on_acp_event('prompt_completed', {'stopReason': 'end_turn'})
        observed.store.record('execution_end', output='Workspace inspected')
        observed.close()
        run.submit(output='Workspace inspected', status='completed')

        evidence = run.history[0].submission.extensions['trace_evidence']
        assert 'trace_event_limit' not in evidence['reasons']
        tool = next(s for s in evidence['spans'] if s.get('tool_content_status'))
        assert dict(tool['tool_content_status']) == {'arguments': 'present', 'result': 'present'}
        spans = [json.loads(line)['data'] for line in (folder / 'otel.jsonl').read_text().splitlines()]
        assert all(span['dropped_events'] == 0 for span in spans)
        root = next(span for span in spans if span['name'] == 'abb.execute')
        assert [event['name'] for event in root['events']] == ['acp.prompt_started', 'acp.prompt_completed']
        # All original notifications and payloads remain available for local inspection.
        assert len((folder / 'acp-events.jsonl').read_text().splitlines()) == 304
        payloads = list((folder / 'otel-payloads').glob('*-events.jsonl'))
        assert sum(len(p.read_text().splitlines()) for p in payloads) == 304
