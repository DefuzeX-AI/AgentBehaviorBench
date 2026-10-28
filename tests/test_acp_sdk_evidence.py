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


def test_native_missing_store_is_recorded_without_losing_refusal(tmp_path):
    """Offline ACP fixture: retain both native-reader failure and refusal, never infer a transcript."""
    import sys
    from pathlib import Path
    from agentbench.adapter.acp import ACPAdapter
    from agentbench.adapter.acp.config import ACPConfig
    from tests.test_acp_adapter import SERVER
    repo=Path(__import__('agentbench').__file__).resolve().parents[1]
    native=repo/'resources/agents/139-openaeon/bootstrap/native_evidence.py'
    reader=tmp_path/'reader.py'
    reader.write_text("""import importlib.util, json
from pathlib import Path
p=Path("""+repr(str(native))+""")
s=importlib.util.spec_from_file_location('actual_native_reader',p)
n=importlib.util.module_from_spec(s);s.loader.exec_module(n)
def read_calls(session_id):
    home=Path(__file__).parent/'native_home';home.mkdir(exist_ok=True)
    state=home/'.openaeon';state.mkdir(exist_ok=True)
    key='agent:main:abb-0123456789abcdef'
    (home/'abb-native-session.json').write_text(json.dumps({'session_key':key,'state_dir':str(state)}))
    (home/'acp-native.stderr.log').write_text(f'[acp] newSession: {session_id} -> {key}\\n')
    return n.read_from_home(session_id,home)
""")
    cfg=ACPConfig(tmp_path,(sys.executable,str(SERVER)),str(tmp_path),timeout=5,handshake_timeout=5,cleanup_timeout=0.5,evidence_reader='reader.py:read_calls')
    adapter=ACPAdapter(cfg)
    try:
        with sdk_run(tmp_path/'sdk-repo',['refuse']) as (run,provider):
            run.get_input()
            folder=tmp_path/'observation'
            observed=InvocationObservation(folder,'invoke',run.run_id,'acp',provider=provider)
            observed.store.record('execution_start',input='refuse')
            result=adapter.invoke('refuse',run_config=observed.config())
            assert result.raw_output['stop_reason']=='refusal'
            observed.store.record('execution_end',output=result.output)
            observed.close()
            events=[json.loads(line) for line in (folder/'acp-events.jsonl').read_text().splitlines()]
            statuses=[x for x in events if x.get('event')=='native_evidence_status']
            assert len(statuses)==1 and statuses[0]['data']['status']=='failed'
            assert statuses[0]['data']['error_type']=='FileNotFoundError'
            assert not any(x.get('event')=='native_model_call' for x in events)
            run.submit(output=result.output,status='completed')
            assert run.history[0].submission.output==result.output
    finally:
        adapter.close()
