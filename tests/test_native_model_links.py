import json
from agentbench.observe.interactions import interactions
from agentbench.observe.native_links import response_ids


def test_pure_text_native_id_assignment_and_replay_ambiguity(tmp_path):
    folder=tmp_path/'evaluation/inputs/0001';folder.mkdir(parents=True)
    (folder/'input.json').write_text(json.dumps({'case_id':'case','input_id':'step-1'}))
    event={'event':'native_model_call','data':{'native_call_id':'native-call','native_turn_id':'turn-a',
        'native_session_id':'session-a','native_response_id':'msg-1','purpose':'agent'}}
    (folder/'framework.jsonl').write_text(json.dumps(event))
    rows=[{'event':'llm_request','data':{'call_id':'http-1','case_id':'case'}},
          {'event':'llm_response','data':{'call_id':'http-1','payload':{'events':[
              {'type':'message_start','message':{'id':'msg-1'}}]}}}]
    path=tmp_path/'network.jsonl';path.write_text('\n'.join(map(json.dumps,rows)))
    row,=interactions(tmp_path,{'kinds':'chat'})['items']
    assert row['input_id']=='step-1' and row['link_evidence']=='native_response_id'
    assert row['native_turn_id']=='turn-a' and row['framework_span_id'] is None
    rows += [{**r,'data':{**r['data'],'call_id':'http-2'}} for r in rows[:]]
    path.write_text('\n'.join(map(json.dumps,rows)))
    assert all(r['association_status']=='ambiguous' for r in interactions(tmp_path,{'kinds':'chat'})['items'])


def test_message_id_in_history_or_text_cannot_link():
    assert response_ids({'messages':[{'id':'history'}],'content':[{'id':'nested'}]})==set()


def test_evidence_reader_is_bounded_to_unit(tmp_path):
    from agentbench.adapter.acp.config import ACPConfig
    from agentbench.adapter.acp.evidence import load_reader, validate_reader
    import pytest
    for ref in ('/etc/file.py:read','../file.py:read','file.py:bad-symbol'):
        with pytest.raises(ValueError):validate_reader(ref)
    (tmp_path/'reader.py').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):
        load_reader(ACPConfig(tmp_path,('command',),str(tmp_path),evidence_reader='reader.py:read'))


def test_pinned_native_reader_exports_only_ids(tmp_path, monkeypatch):
    from pathlib import Path
    import base64, importlib.util
    source=Path(__file__).parents[1]/'resources/agents/16-minimax-code/bootstrap/native_evidence.py'
    spec=importlib.util.spec_from_file_location('minimax_reader_test',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    session=tmp_path/'abb-byok-profile/v2/sessions/2026/session';folder=session/'llm-context-inspector'
    (folder/'payloads').mkdir(parents=True)
    (session/'manifest.json').write_text(json.dumps({'sessionId':'session-a'}))
    (folder/'events.jsonl').write_text(json.dumps({'v':1,'type':'call.captured','callId':'call-a',
        'turnId':'turn-a','responseState':'AVAILABLE','attemptCount':2}))
    name=base64.urlsafe_b64encode(b'call-a').decode().rstrip('=')
    (folder/'payloads'/f'{name}.response.json').write_text(json.dumps({'id':'msg-a','content':'private body'}))
    monkeypatch.setenv('MINIMAX_DATA_DIR',str(tmp_path))
    calls=module.read_calls('session-a')
    assert calls[0]['native_response_id']=='msg-a'
    assert 'private body' not in str(calls)
    assert module.read_calls('another-session')==[]


def test_observation_headers_do_not_accept_credentials_or_authoritative_ids():
    import pytest
    from agentbench.runtime.interception.config import _observation_headers
    assert _observation_headers({'native_session_id':'X-Mavis-Session-Id'})
    for value in ({'case_id':'X-Case'}, {'native_session_id':'Authorization'},
                  {'native_session_id':'X-Api-Key'}, {'native_session_id':'Cookie'}):
        with pytest.raises(ValueError):_observation_headers(value)
