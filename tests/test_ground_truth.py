"""GT references retain complete native attempts plus the saved trajectory contract."""
import json
from types import SimpleNamespace
import pytest
from agentbench import trajectory
from agentbench.harness.ground_truth.manifests import load_manifest, MANIFEST_SCHEMA, LEGACY_SCHEMA
from tests.trajectory_fixtures import langgraph_attempt


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def reference_attempt(directory, agent):
    """A complete attempt directory with its derived trajectory.json beside the raw records."""
    langgraph_attempt(directory)
    run = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
    write_json(directory / 'run.json', {**run, 'agent_id': agent})
    assert trajectory.write(directory)['status'] == 'complete'
    return directory


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
              'expected_behavior': 'The full path is used.', 'observed_behavior': 'The suffix after the space is lost.',
              'reference_attempts': ['reference'],
              'decisive_step': {'attempt': 'reference', 'step_id': 1, 'agent_name': agent,
                                'reason': 'The first model call issues the tool with the truncated path.'}}
    document = defect
    path = unit / 'ground_truth/path-truncation/gt.json'
    write_json(path, document)
    write_json(path.parent / 'case.json', {'case_id': 'reference-case'})
    reference_attempt(path.parent / 'attempts/reference', agent)
    directory = root / 'results/suites' / suite_id
    plan = {'suite_id': suite_id, 'agents': [{'agent_id': agent, 'source_sha256': 'different-source'}]}
    report = {'status': 'issue', 'issues': [{'message': 'The tool truncates a quoted path'}], 'evidence_gaps': []}
    attempt = {'attempt_id': 'attempt-1', 'execution_status': 'failed',
               'result': {'error': 'GraphRecursionError', 'benchmark': {'report': report}}}
    case = {'case_index': 0, 'attempts': [attempt]}
    snapshot = {'suite_id': suite_id, 'state': 'failed', 'jobs': [{'agent_id': agent, 'cases': [case]}]}
    write_json(directory / 'plan.json', plan)
    write_json(directory / 'events.json', [])
    return SimpleNamespace(root=root, unit=unit, manifest_path=path, manifest=document, defect=defect,
                           directory=directory, plan=plan, snapshot=snapshot, attempt=attempt, report=report,
                           record={'plan': plan, 'snapshot': snapshot, 'directory': directory})


def test_complete_case_is_loaded_with_its_saved_trajectory(tmp_path):
    from agentbench.harness.ground_truth.trajectories import read_reference
    f = ground_truth_fixture(tmp_path)
    loaded = load_manifest(f.unit, 'alpha')
    assert loaded == [{**f.defect, '_case_directory': f.manifest_path.parent}]
    assert 'sha256' not in f.manifest_path.read_text(encoding='utf-8')
    reference = read_reference(loaded[0])
    assert reference[0]['attempt'] == 'reference'
    assert [s['step_id'] for s in reference[0]['steps']] == [1, 2]
    assert reference[0]['steps'][0]['tool_logs'][0]['outputs'] == 'a.txt'
    assert (f.manifest_path.parent / 'attempts/reference/logs/network.jsonl').is_file()  # raw records retained


@pytest.mark.parametrize('change', ['empty', 'duplicate', 'escape', 'missing_summary', 'missing_case', 'missing_attempt',
                                    'missing_decisive', 'decisive_wrong_attempt', 'decisive_wrong_step',
                                    'decisive_agent_mismatch', 'missing_trajectory', 'foreign_trajectory'])
def test_malformed_references_rejected(tmp_path, change):
    f = ground_truth_fixture(tmp_path)
    reference = f.manifest_path.parent / 'attempts/reference'
    if change == 'empty': f.defect['reference_attempts'] = []
    if change == 'duplicate': f.defect['reference_attempts'] *= 2
    if change == 'escape': f.defect['reference_attempts'] = ['../../elsewhere']
    if change == 'missing_summary': del f.defect['summary']
    if change == 'missing_case': (f.manifest_path.parent / 'case.json').unlink()
    if change == 'missing_attempt': f.defect['reference_attempts'] = ['missing']
    if change == 'missing_decisive': del f.defect['decisive_step']
    if change == 'decisive_wrong_attempt': f.defect['decisive_step']['attempt'] = 'other'
    if change == 'decisive_wrong_step': f.defect['decisive_step']['step_id'] = 9
    if change == 'decisive_agent_mismatch': f.defect['decisive_step']['agent_name'] = 'someone-else'
    if change == 'missing_trajectory': (reference / 'trajectory.json').unlink()
    if change == 'foreign_trajectory':
        saved = json.loads((reference / 'trajectory.json').read_text(encoding='utf-8'))
        write_json(reference / 'trajectory.json', {**saved, 'agent_id': 'beta'})
    write_json(f.manifest_path, f.manifest)
    with pytest.raises(ValueError):
        load_manifest(f.unit, 'alpha')


def test_missing_trajectory_names_the_rebuild_command(tmp_path):
    f = ground_truth_fixture(tmp_path)
    (f.manifest_path.parent / 'attempts/reference/trajectory.json').unlink()
    with pytest.raises(ValueError, match='agentbench trajectory build'):
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
    from agentbench.harness.ground_truth.trajectories import read_reference
    f = ground_truth_fixture(tmp_path)
    f.defect['provenance'] = {'source_case_directory': str(f.manifest_path.parent)}
    write_json(f.manifest_path, f.defect)
    moved = f.unit.with_name('relocated')
    f.unit.rename(moved)
    assert not f.unit.exists()
    loaded = load_manifest(moved, 'alpha')
    assert read_reference(loaded[0])[0]['steps'][1]['output']['text'] == 'The file says hello.'
