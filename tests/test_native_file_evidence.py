"""Regression fixtures only; no model or Agent responses count as acceptance."""
from pathlib import Path
import json, os, hashlib, importlib
import pytest
from agentbench.sdk.plugin.local import relay, provider
from agentbench.sdk.common.artifacts import Artifacts

def collector(root, **kw):
    return importlib.import_module('agentbench.sdk.common.file_evidence').FileEvidence(root, **kw)

def test_collect_real_created_file(tmp_path):
    root=tmp_path/'workspace';root.mkdir();c=collector(root);before=c.capture();(root/'a.txt').write_bytes(b'A\r\nB\r\n');out=Artifacts(tmp_path/'out');m=c.publish(before,c.capture(),out,'steps/0001',export=True,diff=True)
    assert m['status']=='complete' and len(m['changes'])==1;row=m['changes'][0];assert row['path']=='a.txt' and row['change_type']=='created';raw=json.loads((out.directory/row['after']['artifact']).read_text());assert raw['content']=='A\r\nB\r\n';assert hashlib.sha256(raw['content'].encode()).hexdigest()==row['after']['sha256']

def test_capture_modified_deleted_and_unchanged(tmp_path):
    (tmp_path/'changed').write_text('old');(tmp_path/'deleted').write_text('gone');(tmp_path/'same').write_text('same');c=collector(tmp_path);a=c.capture();(tmp_path/'changed').write_text('new');(tmp_path/'deleted').unlink();b=c.capture();out=Artifacts(tmp_path.parent/'observed-output');m=c.publish(a,b,out,'steps/0001',export=True,diff=True);assert {(x['path'],x['change_type']) for x in m['changes']}=={('changed','modified'),('deleted','deleted')};assert 'same' not in str(m['changes'])

@pytest.mark.parametrize('name,content',[('.env','API_KEY=fiction'),('credential.json','{"api_key":"unconfigured-secret-value"}'),('text.txt','Bearer abcdefghijklmnopqrstuvwxyz'),('key.pem','-----BEGIN PRIVATE KEY-----')])
def test_sensitive_files_omitted(tmp_path,name,content):
    (tmp_path/name).write_text(content);c=collector(tmp_path);s=c.capture();assert s['status']=='partial';row=s['entries'][name];assert 'content' not in row and row['omitted']=='sensitive_content'

def test_declared_secret_omitted_not_rewritten(tmp_path):
    (tmp_path/'note').write_text('contains hidden-fixture-value');s=collector(tmp_path,secrets=('hidden-fixture-value',)).capture();assert s['entries']['note']['omitted']=='sensitive_content' and s['status']=='partial'

def test_symlink_cannot_leak_outside(tmp_path):
    root=tmp_path/'root';root.mkdir();(tmp_path/'outside').write_text('not workspace');(root/'link').symlink_to(tmp_path/'outside');s=collector(root).capture();assert s['status']=='partial' and 'content' not in s['entries']['link'];assert 'not workspace' not in json.dumps(s)

def test_binary_and_limits_are_explicit(tmp_path):
    (tmp_path/'bin').write_bytes(b'\x00\xff');(tmp_path/'large').write_text('x'*100);s=collector(tmp_path,max_file_bytes=16).capture();assert s['status']=='partial';assert s['entries']['bin']['omitted']=='binary_content';assert s['entries']['large']['omitted']=='file_size_limit'

def test_metadata_only_never_claims_export(tmp_path):
    c=collector(tmp_path);a=c.capture();(tmp_path/'x').write_text('data');out=Artifacts(tmp_path.parent/'meta-output');m=c.publish(a,c.capture(),out,'steps/0001',export=False,diff=False);assert m['changes'][0]['after']['sha256'];assert 'artifact' not in m['changes'][0]['after'];assert not (out.directory/'steps/0001/file-content').exists()

def test_judge_budget_default_and_opt_in():
    e={'ABB_LOCAL_JUDGE_BASE_URL':'https://fixture.example/v1','ABB_LOCAL_JUDGE_MODEL':'fixture','ABB_LOCAL_JUDGE_API_KEY':'fixture-key'};assert relay.judge_model(e).max_tokens==2048;assert relay.judge_model({**e,'ABB_LOCAL_JUDGE_MAX_TOKENS':'8192'}).max_tokens==8192
@pytest.mark.parametrize('value',['0','-1','32769','junk','2.5'])
def test_judge_invalid_budget_rejected(value):
    e={'ABB_LOCAL_JUDGE_BASE_URL':'https://fixture.example/v1','ABB_LOCAL_JUDGE_MODEL':'fixture','ABB_LOCAL_JUDGE_API_KEY':'fixture-key','ABB_LOCAL_JUDGE_MAX_TOKENS':value}
    with pytest.raises(ValueError,match='MAX_TOKENS'):relay.judge_model(e)

def test_truncated_json_never_accepted_even_if_parseable(monkeypatch):
    import io
    data={'choices':[{'finish_reason':'length','message':{'content':'{"status":"pass","confidence":"high","issues":[]}'}}]}
    monkeypatch.setattr(relay.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(json.dumps(data).encode()));seen=[]
    with pytest.raises(RuntimeError,match='truncated'):relay.ask_model(relay.JudgeModel('https://fixture.example','fixture','fixture-key'),[],on_response=seen.append)
    assert seen==[data]

def test_worker_collects_without_kuma(tmp_path,monkeypatch):
    # Reuse the actual generic worker's existing isolated-session fixture.
    import asyncio, builtins
    from agentbench.sdk.integration import worker
    from agentbench.sdk.integration.cases import pack_case,case_bytes,digest
    from agentbench.sdk.integration.run import Run
    from tests.test_sdk_defaults import FakeAgent
    root=tmp_path/'unit';root.mkdir();(root/'agent.toml').write_text('agent_id="fixture"\nframework="langgraph"\n[evaluation.workspace]\npath="/home/agent/workspace"\ninitial_state="empty"\n[evaluation.file_evidence]\ntrack_files=true\nexport_changed_files=true\nupload_diff=true\n');work=tmp_path/'workspace';work.mkdir();storage=tmp_path/'private';storage.mkdir();output=tmp_path/'out';output.mkdir();case={'case_id':'fixture-case','inputs':[{'input_id':'one','payload':'write supplied text'}]};document=pack_case(case,factory='fixture:create',index=0,workspace={'path':str(work)});raw=case_bytes(document);(storage/'case.json').write_bytes(raw)
    settings={'private_storage':str(storage),'expected_artifact_sha256':digest(raw),'expected_case_id':'fixture-case','expected_content_sha256':digest(case_bytes(case)),'sdk_factory':'fixture:create','case_index':0,'workspace':{'path':str(work)},'sdk_options':{},'agent_id':'fixture','framework':'langgraph','execution_only':True}
    original=builtins.__import__
    def guarded(name,*a,**kw):
        assert name!='kuma' and not name.startswith('kuma.');return original(name,*a,**kw)
    monkeypatch.setattr(builtins,'__import__',guarded)
    class Write(FakeAgent):
        async def invoke(self,*a,**kw):
            (work/'actual.txt').write_text('observed fixture write');return await super().invoke(*a,**kw)
    summary={'steps':[]};asyncio.run(worker.execute_case(lambda **kw:Run(kw['case']),root,work,settings,Artifacts(output),summary,session=Write()));m=json.loads((output/'steps/0001/file-evidence.json').read_text());assert m['status']=='complete' and m['changes'][0]['path']=='actual.txt'


def file_request(tmp_path, *, partial=False):
    from types import SimpleNamespace
    from agentbench.sdk.judges import build_request
    root=tmp_path/'workspace';root.mkdir();out=tmp_path/'output';step=out/'steps/0001';step.mkdir(parents=True);unit=tmp_path/'unit';unit.mkdir();(unit/'agent.toml').write_text('agent_id="fixture"\nframework="langgraph"\n[evaluation.workspace]\npath="/home/agent/workspace"\ninitial_state="empty"\n[evaluation.file_evidence]\ntrack_files=true\nexport_changed_files=true\nupload_diff=true\n')
    c=collector(root);before=c.capture();(root/'actual.txt').write_text('actual captured content')
    if partial:(root/'binary').write_bytes(b'\x00\xff')
    c.publish(before,c.capture(),Artifacts(out),'steps/0001',export=True,diff=True)
    for name,value in [('input.json',{'input_id':'one','payload':'write supplied text'}),('result.json',{'status':'succeeded','output':'recorded fixture reply'})]:
        (step/name).write_text(json.dumps(value))
    (step/'framework.jsonl').write_text('{}\n');(step/'spans.jsonl').write_text('{}\n');(out/'manifest.json').write_text(json.dumps({'steps':[{'directory':'steps/0001'}],'run_id':'fixture-run','evidence':'complete'}))
    request=build_request(out,SimpleNamespace(path=unit,agent_id='fixture'),{'case':{'inputs':[{'input_id':'one','payload':'write supplied text'}]},'workspace':{'path':'/home/agent/workspace'}})
    return out,request


def test_judge_receives_verified_actual_file_content(tmp_path,monkeypatch):
    out,r=file_request(tmp_path);seen=[]
    monkeypatch.setattr(provider,'judge_model',lambda e:relay.JudgeModel('https://fixture.example','fixture','fixture-key'))
    def ask(model,steps,**kwargs):
        seen.append(steps[0]['file_evidence']);return {'status':'pass','confidence':'high','reason':'fixture verdict','issues':[],'evidence_gaps':[]},'{}'
    monkeypatch.setattr(provider,'ask_model',ask);reply=provider.judge.judge(r,directory=out,environ={});assert reply['status']=='pass';assert seen[0]['changes'][0]['after']['content']=='actual captured content'


def test_missing_file_evidence_blocks_model_and_pass(tmp_path,monkeypatch):
    from agentbench.sdk.integration.cases import case_bytes,digest
    out,r=file_request(tmp_path);del r['attachments']['steps/0001/file-evidence.json'];r['request_id']=digest(case_bytes({k:v for k,v in r.items() if k!='request_id'}));monkeypatch.setattr(provider,'ask_model',lambda *a,**k:pytest.fail('Missing evidence must not call model'));reply=provider.judge.judge(r,directory=out,environ={});assert reply['status']=='inconclusive' and reply['evidence_gaps']


def test_partial_files_block_model_and_pass(tmp_path,monkeypatch):
    out,r=file_request(tmp_path,partial=True);monkeypatch.setattr(provider,'ask_model',lambda *a,**k:pytest.fail('Partial evidence must not call model'));reply=provider.judge.judge(r,directory=out,environ={});assert reply['status']=='inconclusive'


def test_generation_budget_not_increased_by_judge_override(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from agentbench.sdk.plugin.local import generation
    seen=[]
    def selected(environ):
        seen.append(environ);return relay.JudgeModel('https://fixture.example','fixture','fixture-key')
    def ask(model,steps,normalize,**kwargs):
        assert model.max_tokens==2048
        return normalize({'inputs':[{'input_id':'one','payload':'fixture task'}]},set()),'{}'
    monkeypatch.setattr(generation,'judge_model',selected);monkeypatch.setattr(generation,'ask_model',ask);original={'ABB_LOCAL_JUDGE_MAX_TOKENS':'8192'};generation.generate_cases(SimpleNamespace(case_count=1),limit=1,environ=original,output=tmp_path,context={'input_type':'text','references':{}});assert 'ABB_LOCAL_JUDGE_MAX_TOKENS' not in seen[0] and original['ABB_LOCAL_JUDGE_MAX_TOKENS']=='8192'


def test_total_and_entry_bounds_mark_partial(tmp_path):
    for name in ('a','b','c'):(tmp_path/name).write_text('12345678')
    limited=collector(tmp_path,max_total_bytes=12).capture();assert limited['status']=='partial';assert sum(v.get('size_bytes',0) for v in limited['entries'].values() if 'content' in v)<=12
    entries=collector(tmp_path,max_entries=2).capture();assert entries['status']=='partial' and 'entry_limit' in entries['errors']


def test_sensitive_filename_not_published_as_dictionary_key(tmp_path):
    root=tmp_path/'work';root.mkdir();c=collector(root,secrets=('fixture-super-secret-name',));before=c.capture();(root/'fixture-super-secret-name').write_text('ordinary content');out=Artifacts(tmp_path/'output',environ={});m=c.publish(before,c.capture(),out,'steps/0001',export=True,diff=True);assert m['status']=='partial';assert 'fixture-super-secret-name' not in (out.directory/'steps/0001/file-evidence.json').read_text()
