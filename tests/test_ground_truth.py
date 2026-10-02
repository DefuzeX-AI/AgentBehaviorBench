"""Explicit reviewed evidence, never execution progress, measures discovery."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.harness.ground_truth import (
    ASSESSMENTS_SCHEMA, MANIFEST_SCHEMA, GroundTruthError, benchmark_ground_truth,
    digest_json, file_digest, load_manifest, validate_assessment,
)
from agentbench.harness.ground_truth.files import EVIDENCE_LIMIT, JSON_LIMIT, read_json

SOURCE_SHA = 'a' * 64
CONFIRMED_AT = '2026-10-02T12:00:00+00:00'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def ground_truth_fixture(root, agent_id='alpha', suite_id='suite_first'):
    """Small real files for consumers testing the public read-only interface."""
    root = Path(root)
    unit = root / 'resources' / 'agents' / agent_id
    directory = unit / 'ground_truth'
    directory.mkdir(parents=True)
    (unit / 'agent.toml').write_text(f'agent_id = "{agent_id}"\n', encoding='utf-8')
    registry = root / 'resources' / 'registry.toml'
    existing = registry.read_text() if registry.exists() else ''
    registry.write_text(existing + f'\n[[agents]]\nagent_id = "{agent_id}"\npath = "resources/agents/{agent_id}"\n')
    original_case_hash = hashlib.sha256(b'original retained Case').hexdigest()
    observations = []
    for index in range(2):
        evidence = directory / f'observation-{index}.txt'
        evidence.write_text(f'Human-reviewed reproduction {index}')
        observations.append({'id': f'observation-{index}', 'case_sha256': original_case_hash,
                             'evidence_path': evidence.name, 'evidence_sha256': file_digest(evidence)})
    defect = {'id': 'known-defect', 'title': 'Confirmed missing constraint',
              'expected_behavior': 'Preserve the required constraint',
              'observed_behavior': 'Constraint is lost', 'source_sha256': SOURCE_SHA,
              'case_sha256': original_case_hash, 'confirmed_by': 'human-reviewer',
              'confirmed_at': CONFIRMED_AT, 'observations': observations}
    manifest = {'schema': MANIFEST_SCHEMA, 'agent_id': agent_id, 'defects': [defect]}
    manifest_path = directory / 'manifest.json'
    write_json(manifest_path, manifest)
    suite = root / 'results' / 'suites' / suite_id
    artifact = suite / 'cases' / agent_id / '0' / 'case.json'
    write_json(artifact, {'task': 'Another Case that reproduces the same defect'})
    result = {'status': 'succeeded', 'execution_status': 'completed',
              'benchmark': {'report': {'status': 'issue', 'reason': 'Model finding'}}}
    attempt = {'attempt_id': 'attempt-1', 'execution_status': 'completed',
               'host_acceptance': 'accepted', 'evidence_status': 'captured',
               'host_trace_validation': 'passed', 'result': result}
    case = {'case_index': 0, 'prepared_case': {'artifact_path': str(artifact),
            'artifact_sha256': file_digest(artifact)}, 'attempts': [attempt]}
    record = {'directory': suite,
              'plan': {'suite_id': suite_id, 'agents': [{'agent_id': agent_id, 'source_sha256': SOURCE_SHA}]},
              'snapshot': {'suite_id': suite_id, 'jobs': [{'agent_id': agent_id, 'cases': [case]}]}}
    review = {'agent_id': agent_id, 'case_index': 0, 'attempt_id': 'attempt-1',
              'ground_truth_id': defect['id'], 'ground_truth_sha256': digest_json(defect),
              'case_sha256': file_digest(artifact), 'result_sha256': digest_json(result),
              'case_reproduced': True, 'judge_detected': True, 'reviewed_by': 'human-reviewer',
              'reviewed_at': CONFIRMED_AT, 'rationale': 'Execution and Judge both identify the confirmed constraint defect.'}
    assessment_path = suite / 'ground_truth' / 'assessments.json'

    def save_reviews(*reviews):
        write_json(assessment_path, {'schema': ASSESSMENTS_SCHEMA, 'suite_id': suite_id,
                                     'assessments': list(reviews)})

    return SimpleNamespace(root=root, unit=unit, directory=directory, defect=defect, manifest=manifest,
                           manifest_path=manifest_path, record=record, case=case, attempt=attempt,
                           result=result, artifact=artifact, review=review, assessment_path=assessment_path,
                           save_reviews=save_reviews)


@pytest.fixture
def ground_truth(tmp_path):
    return ground_truth_fixture(tmp_path)


def summary(fixture, agent_ids=('alpha',)):
    return benchmark_ground_truth(fixture.root, [fixture.record], agent_ids)


def test_missing_ground_truth_is_not_a_zero_discovery_rate(tmp_path):
    result = benchmark_ground_truth(tmp_path, [], ['alpha', 'beta'])
    assert result['totals']['status'] == 'not_configured'
    assert result['totals']['unconfigured_agent_count'] == 2
    assert result['totals']['discovery_rate'] is None
    assert not result['warnings']


def test_registered_manifest_without_saved_suites_is_included(ground_truth):
    result = benchmark_ground_truth(ground_truth.root, [], [])
    assert result['agents']['alpha']['status'] == 'not_assessed'
    assert result['totals']['configured_agent_count'] == 1
    assert result['totals']['defect_count'] == 1
    assert result['totals']['discovery_rate'] is None
    assert 'evidence_path' not in json.dumps(result)
    assert 'expected_behavior' not in json.dumps(result)


def test_empty_manifest_is_configured_but_has_no_rate(ground_truth):
    ground_truth.manifest['defects'] = []
    write_json(ground_truth.manifest_path, ground_truth.manifest)
    result = summary(ground_truth)
    assert result['totals']['status'] == 'empty'
    assert result['totals']['configured_agent_count'] == 1
    assert result['totals']['discovery_rate'] is None


@pytest.mark.parametrize(('case', 'judge', 'status', 'found', 'rate'), [
    (None, None, 'not_assessed', 0, None), (True, None, 'partially_assessed', 0, None),
    (False, False, 'assessed', 0, 0.0), (True, False, 'assessed', 0, 0.0),
    (True, True, 'assessed', 1, 1.0),
])
def test_only_explicit_reviews_count(ground_truth, case, judge, status, found, rate):
    ground_truth.save_reviews({**ground_truth.review, 'case_reproduced': case, 'judge_detected': judge})
    result = summary(ground_truth)
    agent = result['agents']['alpha']
    assert not result['warnings']
    assert agent['status'] == status
    assert agent['discovered_defect_count'] == found
    assert agent['discovery_rate'] == rate
    assert agent['case_reproduced_count'] == int(case is True)
    assert agent['assessment_count'] == 1


def test_judge_issue_without_review_never_implies_discovery(ground_truth):
    result = summary(ground_truth)
    assert ground_truth.result['benchmark']['report']['status'] == 'issue'
    assert result['totals']['discovered_defect_count'] == 0
    assert result['totals']['assessment_count'] == 0
    assert result['totals']['discovery_rate'] is None


def test_repeated_attempts_count_one_defect_and_new_retry_preserves_discovery(ground_truth):
    fixture = ground_truth
    second = deepcopy(fixture.attempt)
    second['attempt_id'] = 'attempt-2'
    fixture.case['attempts'].append(second)
    fixture.save_reviews(fixture.review, {**fixture.review, 'attempt_id': 'attempt-2'})
    result = summary(fixture)
    assert result['totals']['assessment_count'] == 2
    assert result['totals']['discovered_defect_count'] == 1
    fixture.case['active_attempt_id'] = 'attempt-3'
    fixture.case['execution_status'] = 'running'
    fixture.case['attempts'].append({'attempt_id': 'attempt-3', 'execution_status': 'running', 'result': None})
    assert summary(fixture)['totals']['discovered_defect_count'] == 1


def test_duplicate_reviews_deduplicate_and_conflicts_fail_closed(ground_truth):
    fixture = ground_truth
    fixture.save_reviews(fixture.review, deepcopy(fixture.review))
    assert summary(fixture)['totals']['assessment_count'] == 1
    fixture.save_reviews(fixture.review, {**fixture.review, 'judge_detected': False})
    result = summary(fixture)
    assert result['totals']['discovered_defect_count'] == 0
    assert result['totals']['assessment_count'] == 0
    assert 'conflicting assessments' in result['warnings'][0]


@pytest.mark.parametrize(('field', 'value'), [
    ('agent_id', 'other'), ('case_index', 1), ('case_index', True), ('attempt_id', 'missing'),
    ('ground_truth_id', 'missing'), ('ground_truth_sha256', 'b' * 64),
    ('case_sha256', 'b' * 64), ('result_sha256', 'b' * 64),
    ('reviewed_by', ''), ('reviewed_at', '2026-10-02'), ('rationale', ''),
    ('case_reproduced', False), ('case_reproduced', 'true'), ('judge_detected', 1),
])
def test_invalid_review_references_and_types_fail_closed(ground_truth, field, value):
    ground_truth.save_reviews({**ground_truth.review, field: value})
    result = summary(ground_truth)
    assert result['totals']['discovered_defect_count'] == 0
    assert result['totals']['assessment_count'] == 0
    assert result['warnings']


@pytest.mark.parametrize('mutation', ['source', 'result', 'case_file', 'evidence_file', 'defect'])
def test_edits_invalidate_association_hashes_without_suite_events(ground_truth, mutation):
    fixture = ground_truth
    fixture.save_reviews(fixture.review)
    assert summary(fixture)['totals']['discovered_defect_count'] == 1
    if mutation == 'source':
        fixture.record['plan']['agents'][0]['source_sha256'] = 'b' * 64
    elif mutation == 'result':
        fixture.result['benchmark']['report']['reason'] = 'Edited report'
    elif mutation == 'case_file':
        fixture.artifact.write_text('changed retained Case')
    elif mutation == 'evidence_file':
        (fixture.directory / 'observation-0.txt').write_text('changed original observation')
    else:
        fixture.defect['title'] = 'Edited defect'
        write_json(fixture.manifest_path, fixture.manifest)
    result = summary(fixture)
    assert result['totals']['discovered_defect_count'] == 0
    assert result['warnings']


@pytest.mark.parametrize(('target', 'field', 'value'), [
    ('attempt', 'execution_status', 'running'), ('attempt', 'error', {'type': 'TimeoutError'}),
    ('attempt', 'host_acceptance', 'rejected'), ('attempt', 'evidence_status', 'missing'),
    ('attempt', 'host_trace_validation', 'failed'), ('result', 'error', {'type': 'RuntimeError'}),
    ('benchmark', 'host_acceptance', 'rejected'), ('benchmark', 'report', None),
    ('artifacts', 'received_report', {'host_accepted': False}),
])
def test_incomplete_rejected_or_invalid_execution_cannot_be_discovered(ground_truth, target, field, value):
    fixture = ground_truth
    obj = fixture.attempt if target == 'attempt' else fixture.result
    if target in {'benchmark', 'artifacts'}:
        obj = fixture.result.setdefault(target, {})
    obj[field] = value
    fixture.save_reviews({**fixture.review, 'result_sha256': digest_json(fixture.result)})
    result = summary(fixture)
    assert result['totals']['assessment_count'] == 0
    assert result['warnings']


def test_case_reproduction_can_be_reviewed_before_a_judge_report_exists(ground_truth):
    fixture = ground_truth
    fixture.result['benchmark'] = None
    fixture.save_reviews({**fixture.review, 'judge_detected': None,
                          'result_sha256': digest_json(fixture.result)})
    result = summary(fixture)
    assert result['totals']['status'] == 'partially_assessed'
    assert result['totals']['case_reproduced_count'] == 1
    assert result['totals']['discovery_rate'] is None


@pytest.mark.parametrize('mutation', ['agent_id', 'duplicate_defect', 'single_observation',
                                    'different_case', 'duplicate_observation_id', 'same_evidence', 'identity'])
def test_invalid_manifest_fails_closed(ground_truth, mutation):
    fixture = ground_truth
    if mutation == 'agent_id':
        fixture.manifest['agent_id'] = 'other'
    elif mutation == 'duplicate_defect':
        fixture.manifest['defects'].append(deepcopy(fixture.defect))
    elif mutation == 'single_observation':
        fixture.defect['observations'].pop()
    elif mutation == 'different_case':
        fixture.defect['observations'][1]['case_sha256'] = 'b' * 64
    elif mutation == 'duplicate_observation_id':
        fixture.defect['observations'][1]['id'] = fixture.defect['observations'][0]['id']
    elif mutation == 'same_evidence':
        fixture.defect['observations'][1]['evidence_path'] = fixture.defect['observations'][0]['evidence_path']
    else:
        (fixture.unit / 'agent.toml').write_text('agent_id = "other"')
    write_json(fixture.manifest_path, fixture.manifest)
    result = summary(fixture)
    assert result['agents']['alpha']['status'] == 'invalid'
    assert result['totals']['defect_count'] == 0
    assert result['totals']['invalid_agent_count'] == 1
    assert result['warnings']


def test_multiple_agent_identities_and_partial_coverage(tmp_path):
    first = ground_truth_fixture(tmp_path)
    second = ground_truth_fixture(tmp_path, 'beta', 'suite_second')
    first.save_reviews(first.review)
    result = benchmark_ground_truth(tmp_path, [first.record, second.record], ['alpha', 'beta', 'gamma'])
    assert result['totals']['configured_agent_count'] == 2
    assert result['totals']['unconfigured_agent_count'] == 1
    assert result['totals']['defect_count'] == 2
    assert result['totals']['discovered_defect_count'] == 1
    assert result['totals']['discovery_rate'] == .5
    assert result['totals']['status'] == 'partially_assessed'


@pytest.mark.parametrize('location', ['manifest', 'evidence', 'assessment', 'artifact', 'registry'])
def test_symlink_escape_is_rejected_without_exposing_external_contents(ground_truth, tmp_path, location):
    fixture = ground_truth
    fixture.save_reviews(fixture.review)
    secret = tmp_path / 'outside' / 'secret.json'
    secret.parent.mkdir()
    secret.write_text('{"secret": "DO_NOT_EXPOSE"}')
    if location == 'manifest':
        path = fixture.manifest_path
    elif location == 'evidence':
        path = fixture.directory / 'observation-0.txt'
    elif location == 'assessment':
        path = fixture.assessment_path
    elif location == 'artifact':
        path = fixture.artifact
    else:
        path = tmp_path / 'resources/registry.toml'
        # Registry boundary is the project root, unlike each evidence boundary.
        secret = tmp_path.parent / f'{tmp_path.name}-external.json'
        secret.write_text('{"secret": "DO_NOT_EXPOSE"}')
    path.unlink()
    path.symlink_to(secret)
    result = summary(fixture)
    assert result['totals']['discovered_defect_count'] == 0
    assert result['warnings']
    assert 'DO_NOT_EXPOSE' not in json.dumps(result)
    assert str(secret) not in json.dumps(result)


def test_parent_relative_evidence_is_rejected_even_with_matching_bytes(ground_truth):
    fixture = ground_truth
    fixture.defect['observations'][0]['evidence_path'] = '../agent.toml'
    fixture.defect['observations'][0]['evidence_sha256'] = file_digest(fixture.unit / 'agent.toml')
    write_json(fixture.manifest_path, fixture.manifest)
    assert summary(fixture)['agents']['alpha']['status'] == 'invalid'


def test_duplicate_or_unsafe_registry_entries_fail_closed(ground_truth):
    fixture = ground_truth
    registry = fixture.root / 'resources' / 'registry.toml'
    registry.write_text(registry.read_text() + '\n[[agents]]\nagent_id = "alpha"\npath = "../external"\n')
    result = benchmark_ground_truth(fixture.root, [], [])
    assert result['agents']['alpha']['status'] == 'invalid'
    assert result['totals']['invalid_agent_count'] == 1


def test_unsupported_or_wrong_suite_document_and_legacy_fail_closed(ground_truth):
    fixture = ground_truth
    fixture.save_reviews(fixture.review)
    fixture.record['plan'] = None
    assert summary(fixture)['totals']['assessment_count'] == 0
    write_json(fixture.assessment_path, {'schema': ASSESSMENTS_SCHEMA, 'suite_id': 'other', 'assessments': [fixture.review]})
    assert 'Suite identity' in summary(fixture)['warnings'][0]


def test_bounded_regular_reads_and_duplicate_json_keys(tmp_path):
    oversized = tmp_path / 'large.json'
    with oversized.open('wb') as stream:
        stream.truncate(JSON_LIMIT + 1)
    with pytest.raises(GroundTruthError, match='size limit'):
        read_json(oversized)
    with oversized.open('wb') as stream:
        stream.truncate(EVIDENCE_LIMIT + 1)
    with pytest.raises(GroundTruthError, match='size limit'):
        file_digest(oversized)
    malformed = tmp_path / 'duplicates.json'
    malformed.write_text('{"defects": [], "defects": []}')
    with pytest.raises(GroundTruthError):
        read_json(malformed)
    fifo = tmp_path / 'fifo'
    os.mkfifo(fifo)
    with pytest.raises(GroundTruthError, match='regular files'):
        file_digest(fifo)
    with pytest.raises(GroundTruthError, match='regular files'):
        read_json(fifo)


def test_fingerprint_cache_detects_same_size_edit_with_preserved_mtime(tmp_path):
    path = tmp_path / 'evidence'
    path.write_bytes(b'first')
    previous = path.stat()
    before = file_digest(path)
    path.write_bytes(b'other')
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert file_digest(path) != before


def test_public_helpers_validate_associations_for_future_producers(ground_truth):
    fixture = ground_truth
    defect = load_manifest(fixture.unit, 'alpha')[0]
    assert defect['ground_truth_sha256'] == digest_json(fixture.defect)
    assert validate_assessment(fixture.review, fixture.record, {('alpha', defect['id']): defect}) == fixture.review
    assert file_digest(fixture.artifact) != fixture.defect['case_sha256']
