"""GT descriptions load from gt.json beside their original case.json."""
import json
from types import SimpleNamespace
import pytest
from agentbench.harness.ground_truth.manifests import load_manifest, MANIFEST_SCHEMA, LEGACY_SCHEMA


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def ground_truth_fixture(root, agent='alpha', suite_id='suite_test'):
    unit = root / 'resources/agents' / agent
    unit.mkdir(parents=True, exist_ok=True)
    (unit / 'agent.toml').write_text(f'agent_id = "{agent}"\n', encoding='utf-8')
    registry = root / 'resources/registry.toml'
    existing = registry.read_text(encoding='utf-8') if registry.exists() else ''
    if f'agent_id = "{agent}"' not in existing:
        registry.write_text(existing + f'\n[[agents]]\nagent_id = "{agent}"\npath = "resources/agents/{agent}"\n', encoding='utf-8')
    defect = {'schema': MANIFEST_SCHEMA, 'agent_id': agent,
              'id': 'known-defect', 'summary': 'Path truncated at space',
              'explanation': 'The registry must preserve the complete quoted path.',
              'expected_behavior': 'The full path is used.', 'observed_behavior': 'The suffix after the space is lost.'}
    path = unit / 'ground_truth/path-truncation/gt.json'
    write_json(path, defect)
    write_json(path.parent / 'case.json', {'case_id': 'reference-case'})
    directory = root / 'results/suites' / suite_id
    plan = {'suite_id': suite_id, 'agents': [{'agent_id': agent, 'source_sha256': 'different-source'}]}
    report = {'status': 'issue', 'issues': [{'message': 'The tool truncates a quoted path'}], 'evidence_gaps': []}
    attempt = {'attempt_id': 'attempt-1', 'execution_status': 'failed',
               'result': {'error': 'GraphRecursionError', 'benchmark': {'report': report}}}
    case = {'case_index': 0, 'attempts': [attempt]}
    snapshot = {'suite_id': suite_id, 'state': 'failed', 'jobs': [{'agent_id': agent, 'cases': [case]}]}
    write_json(directory / 'plan.json', plan)
    write_json(directory / 'events.json', [])
    return SimpleNamespace(root=root, unit=unit, manifest_path=path, manifest=defect, defect=defect,
                           directory=directory, plan=plan, snapshot=snapshot, attempt=attempt, report=report,
                           record={'plan': plan, 'snapshot': snapshot, 'directory': directory})


def test_complete_case_is_loaded(tmp_path):
    f = ground_truth_fixture(tmp_path)
    loaded = load_manifest(f.unit, 'alpha')
    assert loaded == [{**f.defect, '_case_directory': f.manifest_path.parent}]
    assert 'sha256' not in f.manifest_path.read_text(encoding='utf-8')


@pytest.mark.parametrize('change', ['missing_summary', 'missing_explanation', 'empty_summary', 'missing_case'])
def test_malformed_descriptions_rejected(tmp_path, change):
    f = ground_truth_fixture(tmp_path)
    if change == 'missing_summary': del f.defect['summary']
    if change == 'missing_explanation': del f.defect['explanation']
    if change == 'empty_summary': f.defect['summary'] = ' '
    if change == 'missing_case': (f.manifest_path.parent / 'case.json').unlink()
    write_json(f.manifest_path, f.manifest)
    with pytest.raises(ValueError):
        load_manifest(f.unit, 'alpha')


def test_v1_manifest_requires_regeneration(tmp_path):
    f = ground_truth_fixture(tmp_path)
    write_json(f.manifest_path, {**f.manifest, 'schema': LEGACY_SCHEMA})
    with pytest.raises(ValueError, match='regenerate'):
        load_manifest(f.unit, 'alpha')


@pytest.mark.parametrize('name', ['manifest.json', 'ground_truth.json'])
def test_legacy_reference_requires_explicit_migration(tmp_path, name):
    f = ground_truth_fixture(tmp_path)
    f.manifest_path.unlink()
    write_json(f.unit / 'ground_truth' / name, {'observations': ['fake.zip']})
    with pytest.raises(ValueError, match='migrate'):
        load_manifest(f.unit, 'alpha')


def test_wrong_agent_identity_rejected(tmp_path):
    f = ground_truth_fixture(tmp_path)
    with pytest.raises(ValueError, match='identity'):
        load_manifest(f.unit, 'other')


def test_copied_case_does_not_depend_on_original_location(tmp_path):
    f = ground_truth_fixture(tmp_path)
    f.defect['provenance'] = {'source_case_directory': str(f.manifest_path.parent)}
    write_json(f.manifest_path, f.defect)
    moved = f.unit.with_name('relocated')
    f.unit.rename(moved)
    assert not f.unit.exists()
    loaded, = load_manifest(moved, 'alpha')
    assert loaded['_case_directory'] == moved / 'ground_truth/path-truncation'
