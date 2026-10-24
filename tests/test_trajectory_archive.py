"""Historical archives remain readable; new runs have no archive writer."""
import hashlib
import json
import pytest
from agentbench.observe.artifact_paths import artifact_file
from agentbench.sdk.common.artifacts import Artifacts


def test_historical_archive_reads_exact_bytes_without_recreating_files(tmp_path):
    root = tmp_path / 'trajectory/old'
    raw = b'{"output": "retained"}'
    blob = root / 'blobs/payload'
    blob.parent.mkdir(parents=True)
    blob.write_bytes(raw)
    (root / 'manifest.json').write_text(json.dumps({
        'schema': 'abb.trajectory.v1', 'documents': {}, 'files': {
            'evaluation/inputs/0001/result.json': {
                'path': 'blobs/payload', 'size': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest()}}}))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert artifact_file(root, 'steps/0001/result.json').read_bytes() == raw
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()} == before
    blob.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='digest mismatch'):
        artifact_file(root, 'steps/0001/result.json').read_bytes()
    with pytest.raises(ValueError, match='leaves'):
        artifact_file(root, '../outside')


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
