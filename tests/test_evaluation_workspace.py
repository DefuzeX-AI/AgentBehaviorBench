from pathlib import Path
import json
import pytest
from agentbench.sdk.common.workspace import workspace_policy, prepare_workspace
from agentbench.sdk.plugin.kuma.file_artifacts import ChangedFileExporter
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.service import EvaluationPolicy


def manifest(**evidence):
    return {'framework': 'acp', 'adapter': {'cwd': '/home/agent/workspace'}, 'evaluation': {
        'workspace': {'path': '/home/agent/workspace', 'initial_state': 'empty'},
        'file_evidence': {'track_files': True, 'upload_diff': True, **evidence}}}


def test_policy_mounts_actual_workspace_and_preserves_ledger(tmp_path):
    policy = workspace_policy(manifest())
    root = tmp_path / 'workspace'
    contract = prepare_workspace(tmp_path, root, policy)
    args = EvaluationPolicy(tmp_path / 'sdk-repo/.kuma', repository=root,
                            target=policy.path, writable=True).run_arguments()
    assert f'type=bind,source={root},target=/home/agent/workspace' in args
    assert f'type=bind,source={tmp_path}/sdk-repo/.kuma,target=/home/agent/workspace/.kuma' in args
    assert contract == prepare_workspace(tmp_path, tmp_path / 'another', policy)
    assert workspace_policy({}).track_files is False


@pytest.mark.parametrize('path', ['/opt/agent', '/home/agent', '/run/workspace', '/home/agent/../code'])
def test_workspace_cannot_mask_program_or_home(path):
    data = manifest();data['evaluation']['workspace']['path'] = path
    with pytest.raises(ValueError): workspace_policy(data)


def test_fixture_identity_and_no_symlinks(tmp_path):
    source = tmp_path / 'evaluation/seed';source.mkdir(parents=True)
    (source / 'hello.txt').write_text('hello')
    data=manifest();data['evaluation']['workspace'].update(initial_state='fixture', fixture='evaluation/seed')
    policy=workspace_policy(data)
    a=prepare_workspace(tmp_path, tmp_path/'one', policy)
    (source/'hello.txt').write_text('different')
    b=prepare_workspace(tmp_path, tmp_path/'two', policy)
    assert a['fixture_sha256'] != b['fixture_sha256']
    (source/'link').symlink_to('/etc/passwd')
    with pytest.raises(ValueError): prepare_workspace(tmp_path,tmp_path/'three',policy)


def test_final_files_export_sdk_snapshot_limits_and_secrets(tmp_path):
    root=tmp_path/'workspace';root.mkdir()
    (root/'remove.txt').write_text('delete')
    files=Artifacts(tmp_path/'out', environ={'MINIMAX_API_KEY':'fake-regression-credential-12345'})
    exporter=ChangedFileExporter(root,files)
    (root/'remove.txt').unlink()
    (root/'unicode.txt').write_text('你好\n')
    (root/'secret.txt').write_text('fake-regression-credential-12345')
    (root/'binary').write_bytes(b'\x00\xff')
    (root/'huge').write_text('x' * (1024*1024+1))
    (root/'escape').symlink_to('/etc/passwd')
    (root/'.kuma').mkdir();(root/'.kuma/hidden').write_text('runtime ledger')
    result=exporter.finish(); items={i['path']:i for i in result['files']}
    assert result['status']=='partial'
    assert items['unicode.txt']['status']=='exported'
    assert items['remove.txt']['status']=='deleted'
    assert items['secret.txt']['reason']=='sensitive_content'
    assert items['binary']['reason']=='binary'
    assert items['huge']['reason']=='size_limit'
    assert items['escape']['reason']=='non_regular_file'
    assert not any(name.startswith('.kuma') for name in items)
    assert 'fake-regression-credential-12345' not in '\n'.join(p.read_text() for p in (tmp_path/'out').rglob('*.json'))


def test_sdk_three_round_diffs_use_per_input_baseline(tmp_path):
    from kuma import create_run
    root=tmp_path/'workspace';root.mkdir()
    from tests.sdk_fixtures.issue_run import profile
    run=create_run(repo_path=root, agent_profile_path=profile(root), allow_local=True, track_files=True, upload_diff=True, max_steps=3,
        case_provider=lambda ctx: {'case_id':'files', 'input_type':'text', 'inputs':[
            {'input_id':f'step-{i}', 'payload_type':'text','payload':word}
            for i,word in enumerate(('create','modify','delete'))]},
        judge_provider=lambda ctx:{'status':'pass','summary':'Local evidence contract','issues':[]})
    target=root/'file.txt'
    try:
        run.get_input();target.write_text('one\n');run.submit(output='created')
        run.get_input();target.write_text('two\n');run.submit(output='modified')
        run.get_input();target.unlink();run.submit(output='deleted')
        changes=[h.submission.file_evidence.changes for h in run.history]
        assert [[c.change_type for c in step] for step in changes]==[['created'],['modified'],['deleted']]
        assert '-one\n+two' in changes[1][0].diff
        assert '-two' in changes[2][0].diff
    finally:
        if run.state in ('ready','input_delivered'):run.cancel()


def test_prepared_environment_survives_suite_retention_and_restore(tmp_path):
    import hashlib
    from agentbench.sdk.contracts import PreparedCase
    from agentbench.harness.session.cases import retain_prepared
    from agentbench.harness.session.codec import prepared_from_json
    from agentbench.harness.session.codec import json_value
    source=tmp_path/'case.json';source.write_text('{"signed":"original bytes"}')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    case=PreparedCase(0,'case',source,'a'*64,digest,'b'*64)
    retained=retain_prepared(tmp_path/'suite','agent',case)
    restored=prepared_from_json(json_value(retained))
    assert restored.environment_sha256=='b'*64
    assert restored.artifact_path.read_bytes()==source.read_bytes()
