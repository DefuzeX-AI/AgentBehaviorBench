"""GT references retain complete native Case trees, with no archive or hash gate."""
import json
from types import SimpleNamespace
import pytest
from agentbench.harness.ground_truth.manifests import load_manifest, MANIFEST_SCHEMA


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
              'reference_attempts': ['reference']}
    document = defect
    path = unit / 'ground_truth/path-truncation/gt.json'
    write_json(path, document)
    write_json(path.parent / 'case.json', {'case_id': 'reference-case'})
    folder = path.parent / 'attempts/reference/evaluation/inputs/0001'
    write_json(folder / 'input.json', {'path': 'a b.txt'})
    write_json(folder / 'result.json', {'output': 'a'})
    write_json(folder / 'otel-payloads/tool-output.json', 'a')
    span = {'source': 'otel', 'event': 'span', 'data': {'span_id': 'ref-1', 'trace_id': 't',
            'name': 'tool', 'attributes': {'abb.kind': 'tool',
            'abb.output_ref': 'otel-payloads/tool-output.json'}}}
    (folder / 'otel.jsonl').write_text(json.dumps(span) + '\n', encoding='utf-8')
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


def test_complete_case_is_loaded_without_flattening_trace(tmp_path):
    from agentbench.harness.ground_truth.traces import read_reference_traces
    f = ground_truth_fixture(tmp_path)
    loaded = load_manifest(f.unit, 'alpha')
    assert loaded == [{**f.defect, '_case_directory': f.manifest_path.parent}]
    assert 'sha256' not in f.manifest_path.read_text(encoding='utf-8')
    assert 'traces' not in loaded[0]
    trace = read_reference_traces(loaded[0])[0]
    assert trace['events'][-1]['id'] == 'reference/evaluation/inputs/0001/ref-1'
    assert trace['events'][-1]['output'] == 'a'


@pytest.mark.parametrize('change', ['empty', 'duplicate', 'escape', 'missing_summary', 'missing_case', 'missing_attempt'])
def test_malformed_references_rejected(tmp_path, change):
    f = ground_truth_fixture(tmp_path)
    if change == 'empty': f.defect['reference_attempts'] = []
    if change == 'duplicate': f.defect['reference_attempts'] *= 2
    if change == 'escape': f.defect['reference_attempts'] = ['../../elsewhere']
    if change == 'missing_summary': del f.defect['summary']
    if change == 'missing_case': (f.manifest_path.parent / 'case.json').unlink()
    if change == 'missing_attempt': f.defect['reference_attempts'] = ['missing']
    write_json(f.manifest_path, f.manifest)
    with pytest.raises(ValueError):
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


def test_copied_case_trace_does_not_depend_on_original_location(tmp_path):
    from agentbench.harness.ground_truth.traces import read_reference_traces
    f = ground_truth_fixture(tmp_path)
    f.defect['provenance'] = {'source_case_directory': str(f.manifest_path.parent)}
    write_json(f.manifest_path, f.defect)
    moved = f.unit.with_name('relocated')
    f.unit.rename(moved)
    assert not f.unit.exists()
    loaded = load_manifest(moved, 'alpha')
    assert read_reference_traces(loaded[0])[0]['events'][-1]['output'] == 'a'
