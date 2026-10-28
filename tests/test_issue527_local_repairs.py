"""Regression checks for OpenAEON refusal/evidence and local Judge handling."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import pytest
from agentbench.sdk.plugin.local import provider,relay

ROOT=Path(__file__).resolve().parents[1]
BOOTSTRAP=ROOT/'resources/agents/139-openaeon/bootstrap'

def _load(name):
    spec=importlib.util.spec_from_file_location('issue527_'+name,BOOTSTRAP/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_conflicting_pass_with_gaps_is_inconclusive_and_raw_is_unchanged():
    raw={'status':'pass','confidence':'high','reason':'test','issues':[],'evidence_gaps':['proof missing']}
    copy_of_raw=copy.deepcopy(raw)
    out=provider.conservative_verdict(raw,{'one'})
    assert out['status']=='inconclusive' and out['evidence_gaps']==['proof missing'] and raw==copy_of_raw
    assert provider.conservative_verdict({'status':'pass','confidence':'high','reason':'ok','issues':[],'evidence_gaps':[]},{'one'})['status']=='pass'
    with pytest.raises(ValueError):
        provider.conservative_verdict({'status':'issue','confidence':'high','reason':'bad','issues':[],'evidence_gaps':[]},{'one'})

def test_truncated_judge_completion_is_retained_but_not_accepted(monkeypatch):
    data={'choices':[{'finish_reason':'length','message':{'content':'{"status":"pass"}'}}]}
    monkeypatch.setattr(relay.urllib.request,'urlopen',lambda *a,**kw:io.BytesIO(json.dumps(data).encode()))
    retained=[]
    with pytest.raises(RuntimeError,match='truncated'):
        relay.ask_model(relay.JudgeModel('https://example.invalid/v1','fixture','fixture'),[{'input_id':'one'}],on_response=retained.append)
    assert retained==[data]

def test_unit_owned_final_recovery_checks_identity_and_never_leaks_thinking():
    native=_load('native_evidence');session='s-1'
    message={'role':'assistant','stopReason':'stop','content':[{'type':'thinking','thinking':'secret-thought'},{'type':'text','text':'complete visible native answer'}]}
    call={'native_session_id':session,'native_call_id':'one','source_contract':'openaeon.pinned-pi-session-jsonl.e9b35678','capture_status':'native_transcript','native_assistant_record':{'id':'one','message':message}}
    out,meta=native.recover_final('',[],[call],session,'end_turn',1024)
    assert out=='complete visible native answer' and meta['raw_output_chars']==0 and 'secret-thought' not in out
    assert native.recover_final('',[],[call],'wrong-session','end_turn',1024)==('',None)
    assert native.recover_final('',[],[call],session,'refusal',1024)==('',None)
    assert native.recover_final('complete visible native answer',['complete visible native answer'],[call],session,'end_turn',1024)==('complete visible native answer',None)
    assert native.read_calls.recover_final is native.recover_final

def test_refusal_marker_is_consumed_only_for_matched_session_without_transcript(tmp_path):
    launch=_load('launch');native=_load('native_evidence');session='abc-123';key='agent:main:abb-0123456789abcdef'
    state=tmp_path/'.openaeon';state.mkdir()
    (tmp_path/'abb-native-session.json').write_text(json.dumps({'session_key':key,'state_dir':str(state)}))
    (tmp_path/'acp-native.stderr.log').write_text(f'[acp] newSession: {session} -> {key}\n')
    with pytest.raises(FileNotFoundError):native.read_from_home(session,tmp_path)
    with (tmp_path/'acp-native.stderr.log').open('a') as stream:
        stream.write("Error handling request {\n  method: 'session/prompt',\n  params: { sessionId: '"+session+"' }\n} {\n  data: { details: 'high-risk code edit request requires explicit confirmDangerousCodeEdit=true' }\n}\n")
    assert native.read_from_home(session,tmp_path)==[]
    with pytest.raises(FileNotFoundError):native.read_from_home(session,tmp_path)

def test_refusal_counter_never_writes_through_links(tmp_path):
    import os
    native=_load('native_evidence');session='s-1';key='agent:main:abb-0123456789abcdef'
    state=tmp_path/'.openaeon';state.mkdir()
    (tmp_path/'abb-native-session.json').write_text(json.dumps({'session_key':key,'state_dir':str(state)}))
    risk='high-risk code edit request requires explicit confirmDangerousCodeEdit=true'
    (tmp_path/'acp-native.stderr.log').write_text(f"[acp] newSession: {session} -> {key}\nError handling request {{ sessionId: '{session}' }} {{ details: '{risk}' }}\n")
    target=tmp_path/'sensitive';original=json.dumps({'session_id':session,'count':0});target.write_text(original)
    marker=tmp_path/('abb-native-risk-count-'+session+'.json')
    marker.symlink_to(target)
    with pytest.raises((ValueError,OSError)):native.read_from_home(session,tmp_path)
    assert target.read_text()==original
    marker.unlink();os.link(target,marker)
    with pytest.raises(ValueError,match='private regular file'):native.read_from_home(session,tmp_path)
    assert target.read_text()==original
