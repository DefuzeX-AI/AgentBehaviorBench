"""Final paths are usable before completion and require no archive transition."""
import json
from pathlib import Path

import pytest

from agentbench.observe.artifact_paths import artifact_file
from agentbench.observe.view_api import RunViewAPI
from agentbench.sdk.common.artifacts import Artifacts


def test_running_failed_and_resumed_execution_use_same_plain_files(tmp_path):
    root = tmp_path / 'attempts/run'
    files = Artifacts(root)
    files.save('manifest.json', {'phase': 'execution', 'steps': [{'directory': 'steps/0001'}]})
    files.save('steps/0001/result.json', {'output': 'committed'})
    original = (root / 'steps/0001/result.json').read_bytes()
    api = RunViewAPI(root)
    assert api.outputs() == ['steps/0001']
    assert api.read('evaluation/inputs/0001/result.json')['output'] == 'committed'
    files.save('manifest.json', {'phase': 'judge', 'judge': 'failed'})
    files.save('judge/report.json', {'status': 'pass'})
    assert api.evaluation()['judge']['status'] == 'pass'
    assert (root / 'steps/0001/result.json').read_bytes() == original
    assert not (root / 'evaluation').exists()


def test_suite_records_are_references_and_case_slots_do_not_alias(tmp_path):
    from tests.test_suite_store import registration, prepared
    from agentbench.harness.session import SuiteStore, read_suite
    from agentbench.sdk.integration.artifacts import FileArtifactStore
    agent = registration(tmp_path)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_one', [agent]) as store:
        case = store.retain_case(agent.agent_id, prepared(tmp_path))
        first = FileArtifactStore(store.directory).case(agent.agent_id, 0)
        assert case.artifact_path == first.directory / 'case.json'
        assert first.attempt('one').directory.parent.name == 'attempts'
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
    f.plan['artifact_layout'] = 'agent-attempts-v1'
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


def test_judge_context_references_committed_files_and_detects_changes(tmp_path, monkeypatch):
    pytest.importorskip('kuma')
    from agentbench.sdk.plugin.kuma import judge_bundle
    case = {'case_id': 'original'}
    item = {'test_input': {'input_id': 'i'}, 'submission': {'output': 'answer'}}
    monkeypatch.setattr(judge_bundle, 'export_context', lambda *a, **k: {
        'schema': judge_bundle.SCHEMA, 'case': case, 'history': [item]})
    files = Artifacts(tmp_path)
    files.save('case.json', case)
    files.save('steps/0001/input.json', item['test_input'])
    files.save('steps/0001/submission.json', item['submission'])
    judge_bundle.save_context(files, None, case)
    value = json.loads((tmp_path / 'judge/context.json').read_bytes())
    assert 'answer' not in json.dumps(value)
    assert judge_bundle.read_context(tmp_path, value)['history'] == [item]
    files.save('steps/0001/submission.json', {'output': 'changed'})
    with pytest.raises(ValueError, match='modified'):
        judge_bundle.read_context(tmp_path, value)
