"""Synthetic native-format fixtures validate identity and byte-preserving evidence reads."""
from pathlib import Path
import importlib.util,json
import pytest
ROOT=Path(__file__).resolve().parents[1];FILE=ROOT/'resources/agents/135-openaeon/bootstrap/native_evidence.py'
spec=importlib.util.spec_from_file_location('openaeon_evidence',FILE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture(root):
 home=root/'home';folder=home/'.openaeon/agents/main/sessions';folder.mkdir(parents=True)
 key='agent:main:abb-0123456789abcdef';sid='original-acp-session'
 (home/'abb-native-session.json').write_text(json.dumps({'session_key':key,'state_dir':str(home/'.openaeon')}))
 (home/'acp-native.stderr.log').write_text(f'[acp] newSession: {sid} -> {key}\n')
 (folder/'sessions.json').write_text(json.dumps({key:{'sessionId':'native-turn'}}))
 assistant={'type':'message','id':'actual-native-record','message':{'role':'assistant','api':'openai-completions','provider':'abb','model':'glm-5.3-flash','content':[{'type':'toolCall','id':'native-tool-id','name':'read','arguments':{'path':'/workspace/project/input.txt'}}]}}
 tool={'type':'message','id':'actual-tool-record','message':{'role':'toolResult','toolCallId':'native-tool-id','content':[{'type':'text','text':'actual fixture bytes'}]}}
 (folder/'native-turn.jsonl').write_text('\n'.join(json.dumps(x) for x in [assistant,tool])+'\n')
 return home,sid,assistant,tool

def test_reads_original_records_without_inventing_spans_or_provider_ids(tmp_path):
 home,sid,a,t=fixture(tmp_path);records=m.read_from_home(sid,home)
 assert len(records)==1 and records[0]['native_assistant_record']==a
 assert records[0]['native_tool_results']==[t] and records[0]['native_response_id'] is None
 assert records[0]['attempt_count'] is None and records[0]['native_session_id']==sid

def test_other_acp_session_not_associated_by_time_or_folder(tmp_path):
 home,sid,_,_=fixture(tmp_path);assert m.read_from_home('other-session',home)==[]

def test_linked_native_transcript_is_rejected(tmp_path):
 home,sid,_,_=fixture(tmp_path);p=home/'.openaeon/agents/main/sessions/native-turn.jsonl';original=p.read_bytes();p.unlink();(tmp_path/'outside').write_bytes(original);p.symlink_to(tmp_path/'outside')
 with pytest.raises(ValueError,match='linked'):m.read_from_home(sid,home)

def test_native_session_file_cannot_escape_home(tmp_path):
 home,sid,_,_=fixture(tmp_path);folder=home/'.openaeon/agents/main/sessions';d=json.loads((folder/'sessions.json').read_text());next(iter(d.values()))['sessionFile']=str(tmp_path/'outside');(tmp_path/'outside').write_text('{}');(folder/'sessions.json').write_text(json.dumps(d))
 with pytest.raises(ValueError,match='boundary'):m.read_from_home(sid,home)

def test_same_call_id_cannot_attach_another_tool_result(tmp_path):
 home,sid,a,t=fixture(tmp_path);p=home/'.openaeon/agents/main/sessions/native-turn.jsonl';t['message']['toolCallId']='other-call';p.write_text('\n'.join(json.dumps(x) for x in [a,t])+'\n');assert m.read_from_home(sid,home)[0]['native_tool_results']==[]
