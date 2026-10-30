"""Local workspace evidence: all fixtures are real temporary files; no model calls."""
import hashlib, importlib, json
from pathlib import Path
from types import SimpleNamespace
import pytest


def module():
    return importlib.import_module('agentbench.sdk.plugin.local.file_evidence')


def policy():
    from agentbench.sdk.common.workspace import WorkspacePolicy
    return WorkspacePolicy(path='/workspace/project', initial_state='empty', track_files=True, export_changed_files=True)


def test_real_final_snapshot_records_path_size_and_digest(tmp_path):
    root=tmp_path/'workspace';root.mkdir();data=b'print("hello")\n';(root/'hello.py').write_bytes(data)
    destination=tmp_path/'artifacts';destination.mkdir()
    captured=module().capture_workspace(root,destination,policy(),environ={})
    assert captured['status']=='complete' and captured['capture_point']=='after_agent_cleanup_before_workspace_deletion'
    assert captured['workspace']=='/workspace/project' and captured['files']==[{'path':'hello.py','size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]
    assert json.loads((destination/'local-workspace-evidence.json').read_text())==captured


def test_sensitive_and_linked_files_are_omitted_and_mark_partial(tmp_path):
    root=tmp_path/'workspace';root.mkdir();dst=tmp_path/'artifacts';dst.mkdir()
    (root/'hello.py').write_text('print("hello")\n');(root/'.env').write_text('private value')
    (root/'memo.txt').write_text('note: fixture-secret-1234567890');outside=tmp_path/'outside';outside.write_text('external')
    (root/'link').symlink_to(outside)
    captured=module().capture_workspace(root,dst,policy(),environ={'TEST_API_KEY':'fixture-secret-1234567890'})
    assert captured['status']=='partial' and [x['path'] for x in captured['files']]==['hello.py']
    text=(dst/'local-workspace-evidence.json').read_text();assert 'fixture-secret-1234567890' not in text and 'external' not in text
    assert captured['omitted_count']>=3
    assert captured['omitted_reasons']['sensitive_path']==1
    assert captured['omitted_reasons']['sensitive_content']==1
    assert captured['omitted_reasons']['unreadable_or_linked_file']==1


def build_case(root):
    (root/'steps/0001').mkdir(parents=True)
    (root/'manifest.json').write_text(json.dumps({'run_id':'r','evidence':'complete','steps':[{'directory':'steps/0001'}]}))
    (root/'steps/0001/input.json').write_text(json.dumps({'input_id':'s','payload':'Write hello.py'}))
    (root/'steps/0001/result.json').write_text(json.dumps({'status':'succeeded','output':'done'}))
    (root/'steps/0001/spans.jsonl').write_text('{}\n')
    (root/'steps/0001/framework.jsonl').write_text('{}\n')
    return {'case':{'case_id':'c','inputs':[{'input_id':'s','payload':'Write hello.py'}]},'workspace':{'path':'/workspace/project','initial_state':'empty'}}


def test_snapshot_is_hash_bound_and_reaches_judge(tmp_path,monkeypatch):
    from agentbench.sdk import judges
    from agentbench.sdk.plugin.local import provider
    root=tmp_path/'run';root.mkdir();document=build_case(root);workspace=tmp_path/'workspace';workspace.mkdir();(workspace/'hello.py').write_text('hello\n')
    module().capture_workspace(workspace,root,policy(),environ={})
    request=judges.build_request(root,SimpleNamespace(agent_id='openaeon'),document)
    assert request['workspace_evidence']=='local-workspace-evidence.json' and request['workspace_evidence'] in request['attachments']
    seen=[];monkeypatch.setattr(provider,'judge_model',lambda _:SimpleNamespace(model='fixture',base_url='https://fixture.invalid'))
    def fake(model,steps,**kw):
        seen.append(kw['payload']['workspace_evidence'])
        return {'status':'pass','confidence':'high','reason':'fixture','issues':[],'evidence_gaps':[]},'{}'
    monkeypatch.setattr(provider,'ask_model',fake)
    answer=provider.judge.judge(request,directory=root,environ={})
    assert answer['status']=='pass' and seen[0]['files'][0]['path']=='hello.py'
    (root/'local-workspace-evidence.json').write_text('{}')
    with pytest.raises(ValueError,match='evidence changed'):provider.judge.judge(request,directory=root,environ={})


def test_partial_snapshot_reaches_judge_without_hiding_omissions(tmp_path,monkeypatch):
    from agentbench.sdk import judges
    from agentbench.sdk.plugin.local import provider
    root=tmp_path/'run';root.mkdir();document=build_case(root);workspace=tmp_path/'workspace';workspace.mkdir();(workspace/'.env').write_text('hidden');(workspace/'hello.py').write_text('hello')
    captured=module().capture_workspace(workspace,root,policy(),environ={})
    assert captured['status']=='partial' and captured['omitted_count']==1
    request=judges.build_request(root,SimpleNamespace(agent_id='openaeon'),document)
    seen=[];monkeypatch.setattr(provider,'judge_model',lambda _:SimpleNamespace(model='fixture',base_url='https://fixture.invalid'))
    def fake(model,steps,**kw):
        seen.append(kw['payload']['workspace_evidence'])
        return {'status':'inconclusive','confidence':'medium','reason':'fixture','issues':[],'evidence_gaps':['omitted data may matter']},'{}'
    monkeypatch.setattr(provider,'ask_model',fake)
    result=provider.judge.judge(request,directory=root,environ={})
    assert result['status']=='inconclusive' and result['evidence_gaps']==['omitted data may matter']
    assert seen[0]['status']=='partial' and seen[0]['omitted_count']==1 and seen[0]['files'][0]['path']=='hello.py'


def test_local_runner_selects_capture_only_for_execution(monkeypatch):
    from agentbench.sdk.plugin.native.runner import NativeRunner
    from agentbench.sdk.plugin.local.native_runner import LocalRunner
    monkeypatch.setattr(NativeRunner,'_run',lambda self,registration,**kw:kw)
    obj=object.__new__(LocalRunner)
    execute=obj._run(None,settings={'mode':'execute'},context=None,on_progress=None)
    context=obj._run(None,settings={'mode':'context'},context=None,on_progress=None)
    assert callable(execute['capture_workspace']) and 'capture_workspace' not in context


def test_host_captures_after_both_containers_stop_before_workspace_cleanup(tmp_path):
    from agentbench.sdk.integration.execution import run_evaluation
    from tests.test_sdk_execution import fake_services, source_agent, unchanged_stage
    from tests.test_sdk_execution_lifecycle import context
    agent=source_agent(tmp_path)
    with (agent.path/'agent.toml').open('a') as f:
        f.write('[evaluation.workspace]\npath="/workspace/project"\ninitial_state="empty"\n[evaluation.file_evidence]\ntrack_files=true\n')
    services,calls=fake_services();original=services.create_docker_runtime;observed=[]
    def create_runtime(**options):
        runtime=original(**options);start=runtime.start
        def launch(*args,**kwargs):
            result=start(*args,**kwargs)
            if options['run_id'].endswith('-agent'):
                host_path=options['policy'].repository
                (host_path/'hello.py').write_text('hello\n')
                observed.append(host_path)
            return result
        runtime.start=launch;return runtime
    services.create_docker_runtime=create_runtime
    def capture(root,dest,policy,*,environ):
        assert all(call['closed']==1 for call in calls) and root.is_dir()
        return module().capture_workspace(root,dest,policy,environ=environ)
    result=run_evaluation(agent,context=context(services),output=tmp_path/'runs',stage_agent=unchanged_stage,capture_workspace=capture)
    saved=json.loads((result/'local-workspace-evidence.json').read_text())
    assert saved['status']=='complete' and saved['files'][0]['path']=='hello.py'
    assert json.loads((result/'run.json').read_text())['workspace_evidence']=='complete'
    assert observed and not observed[0].exists()


def test_snapshot_expected_by_host_cannot_disappear_before_judging(tmp_path):
    from agentbench.sdk import judges
    root=tmp_path/'run';root.mkdir();document=build_case(root)
    (root/'run.json').write_text(json.dumps({'workspace_evidence':'complete'}))
    with pytest.raises(ValueError,match='workspace evidence is missing'):
        judges.build_request(root,SimpleNamespace(agent_id='openaeon'),document)


def test_bounded_file_scan_never_claims_complete_when_files_are_omitted(tmp_path,monkeypatch):
    root=tmp_path/'workspace';root.mkdir();out=tmp_path/'out';out.mkdir()
    (root/'a').write_text('a');(root/'b').write_text('b');m=module();monkeypatch.setattr(m,'MAX_FILES',1)
    result=m.capture_workspace(root,out,policy(),environ={})
    assert result['status']=='partial' and result['omitted_count']>=1 and result['omitted_reasons']['file_count_limit']>=1


def test_capture_failure_is_recorded_without_fabricating_workspace_evidence(tmp_path):
    from agentbench.sdk.integration.execution import run_evaluation
    from tests.test_sdk_execution import fake_services, source_agent, unchanged_stage
    from tests.test_sdk_execution_lifecycle import context
    agent=source_agent(tmp_path)
    with (agent.path/'agent.toml').open('a') as f:
        f.write('[evaluation.workspace]\npath="/workspace/project"\ninitial_state="empty"\n[evaluation.file_evidence]\ntrack_files=true\n')
    services,calls=fake_services()
    def fail(*args,**kwargs):raise OSError('fixture')
    result=run_evaluation(agent,context=context(services),output=tmp_path/'runs',stage_agent=unchanged_stage,capture_workspace=fail)
    status=json.loads((result/'run.json').read_text());snapshot=json.loads((result/'local-workspace-evidence.json').read_text())
    assert status['status']=='succeeded' and status['workspace_evidence']=='failed'
    assert snapshot['status']=='failed' and snapshot['error_type']=='OSError' and 'files' not in snapshot
    assert all(x['closed']==1 for x in calls)


def test_contradictory_pass_with_gaps_remains_inconclusive():
    from agentbench.sdk.plugin.local.provider import conservative_verdict
    raw={'status':'pass','confidence':'medium','reason':'fixture','issues':[],'evidence_gaps':['a required file is missing']}
    value=conservative_verdict(raw,{'s'})
    assert value['status']=='inconclusive' and value['evidence_gaps']==raw['evidence_gaps'] and raw['status']=='pass'
