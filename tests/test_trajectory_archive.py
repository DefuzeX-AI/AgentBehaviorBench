import json
from pathlib import Path

import pytest

from agentbench.observe.archive import artifact_file, compact_trajectory, restore_archive
from agentbench.observe.view_api import RunViewAPI
from agentbench.sdk.common.artifacts import Artifacts


def saved_run(tmp_path):
    root = tmp_path / 'cases/case-one/trajectory/one'
    files = Artifacts(root)
    files.save('run.json', {'agent_id': 'alpha', 'run_id': 'one', 'case_id': 'c',
        'status': 'succeeded', 'cleanup_status': 'succeeded', 'host_trace_validation': 'succeeded'})
    files.save('evaluation/manifest.json', {'judge': 'received', 'steps': [{'directory': 'inputs/0001'}]})
    files.save('evaluation/judge/report.json', {'status': 'issue'})
    case = {'case_id': 'c', 'inputs': [{'input_id': 'i', 'payload': 'hello'}]}
    Artifacts(root.parent.parent).save('case.json', {'case': case})
    files.save('evaluation/case.json', case)
    submission = {'output': 'answer', 'extensions': {'trace_evidence': {'spans': ['test']}}}
    files.save('evaluation/inputs/0001/input.json', case['inputs'][0])
    files.save('evaluation/inputs/0001/mapped-input.json', 'hello')
    files.save('evaluation/inputs/0001/submission.json', submission)
    files.save('evaluation/inputs/0001/result.json', {'output': 'answer'})
    files.save('evaluation/inputs/0001/evidence.json', submission['extensions']['trace_evidence'])
    files.save('evaluation/inputs/0001/otel-status.json', {'status': 'complete'})
    files.save('evaluation/inputs/0001/otel-payloads/a.json', {'text': 'hello'})
    files.save('evaluation/inputs/0001/otel-payloads/b.json', {'text': 'hello'})
    files.save('evaluation/judge/context.json', {'case': case, 'history': [
        {'test_input': case['inputs'][0], 'submission': submission}], 'run_status': 'completed'})
    files.save('channel/response/00000000/result.json', {'output': 'answer'})
    return root


def test_archive_roundtrip_preserves_every_evidence_byte_and_reader(tmp_path):
    root = saved_run(tmp_path)
    originals = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*')
                 if p.is_file() and 'channel' not in p.parts}
    compact_trajectory(root)
    assert not (root / 'channel').exists()
    assert not (root / 'evaluation').exists()
    assert (root / 'steps/0001/result.json').is_file()
    assert len(list((root / 'blobs').iterdir())) == 1
    api = RunViewAPI(root)
    assert api.outputs() == ['evaluation/inputs/0001']
    assert api.evaluation()['judge']['status'] == 'issue'
    for name, raw in originals.items():
        assert artifact_file(root, name).read_bytes() == raw, name
    assert json.loads((root / 'judge/context.json').read_bytes())['references']
    restore_archive(root)
    for name, raw in originals.items():
        assert (root / name).read_bytes() == raw


def test_archive_detects_tampered_payload_and_reference_escape(tmp_path):
    root = saved_run(tmp_path)
    compact_trajectory(root)
    next((root / 'blobs').iterdir()).write_bytes(b'changed')
    with pytest.raises(ValueError, match='digest mismatch'):
        artifact_file(root, 'evaluation/inputs/0001/otel-payloads/a.json').read_bytes()
    with pytest.raises(ValueError, match='leaves'):
        artifact_file(root, '../../outside')


def test_incomplete_execution_keeps_transport_for_recovery(tmp_path):
    root = saved_run(tmp_path)
    (root / 'evaluation/judge/report.json').unlink()
    compact_trajectory(root)
    assert (root / 'channel/response/00000000/result.json').exists()
    assert not (root / 'manifest.json').exists()


def test_suite_records_are_references_and_case_slots_do_not_alias(tmp_path):
    from tests.test_suite_store import registration, prepared
    from agentbench.harness.session import SuiteStore, read_suite
    from agentbench.sdk.integration.artifacts import FileArtifactStore
    agent = registration(tmp_path)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_one', [agent]) as store:
        case = store.retain_case(agent.agent_id, prepared(tmp_path))
        first = FileArtifactStore(store.directory).case(agent.agent_id, 0)
        assert case.artifact_path == first.directory / 'case.json'
        assert first.attempt('one').directory.parent.name == 'trajectory'
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
            'case_result': {'output': 'unique-output-evidence'}})
        raw = store.path.read_text(encoding='utf-8')
        assert 'unique-output-evidence' not in raw
        assert 'abb.artifact-reference.v1' in raw
        assert read_suite(store.directory)[1][-1]['case_result']['output'] == 'unique-output-evidence'
        assert set(p.name for p in store.directory.iterdir()) == {'.writer.lock', 'plan.json', 'events.json'}
    with SuiteStore.begin(tmp_path / 'suites', 'suite_two', [agent]) as store:
        assert FileArtifactStore(store.directory).case(agent.agent_id, 0).directory != first.directory


def test_managed_gt_results_live_with_agent_and_suite_only_references(tmp_path, monkeypatch):
    from tests.test_gt_matching import setup
    from tests.test_ground_truth import write_json
    f, run = setup(tmp_path, monkeypatch)
    f.plan['artifact_layout'] = 'agent-trajectories-v1'
    write_json(f.directory / 'plan.json', f.plan)
    result = run(lambda *a, **k: {'match': False, 'reason': 'Different defect'})
    assert result['status'] == 'completed'
    assert not (f.directory / 'ground_truth').exists()
    refs = json.loads((f.directory / 'gt.json').read_bytes())
    assert refs['references'][0]['agent_id'] == 'alpha'
    assert (f.directory / refs['references'][0]['path']).is_file()
    def forbidden(*args, **kwargs):
        raise AssertionError('Saved evaluation must be reused')
    assert run(forbidden)['cache_reused']


def test_sdk_ledgers_are_flattened_and_failed_archive_can_retry(tmp_path, monkeypatch):
    from agentbench.observe import archive
    root = saved_run(tmp_path)
    ledger = 'sdk-repo/.kuma/runs/run_0123456789abcdef/submissions/step-0000.json'
    Artifacts(root).save(ledger, {'submission_id': 'original-remote-request'})
    original = (root / ledger).read_bytes()
    write = archive.atomic_bytes
    failed = False
    def fail_once(path, data):
        nonlocal failed
        if 'sdk-state' in path.parts and not failed:
            failed = True
            raise OSError('Simulated archive write failure')
        return write(path, data)
    monkeypatch.setattr(archive, 'atomic_bytes', fail_once)
    with pytest.raises(OSError, match='archive write failure'):
        compact_trajectory(root)
    assert (root / ledger).read_bytes() == original
    assert not (root / 'manifest.json').exists()
    compact_trajectory(root)
    assert artifact_file(root, ledger).read_bytes() == original
    assert len(list((root / 'sdk-state').glob('*.json'))) == 1
    assert not (root / '.archive-pending.json').exists()
