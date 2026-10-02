"""Bind explicit review decisions to one persisted execution and defect revision."""

from pathlib import Path

from agentbench.harness.session.attempts import execution_status
from agentbench.harness.session.plan import digest_json

from .files import (GroundTruthError, file_digest, hash_field, label, read_json,
                    records_field, text_field, timestamp_field, within)

ASSESSMENTS_SCHEMA = 'abb.ground_truth.assessments.v1'


def assessment_identity(record):
    """Reuse slots and retries remain distinct even when they share a Case ID."""
    index = record.get('case_index')
    if type(index) is not int or index < 0:
        raise GroundTruthError('case_index must be a nonnegative integer')
    return (text_field(record, 'agent_id'), index, text_field(record, 'attempt_id'),
            text_field(record, 'ground_truth_id'))


def _unique_match(rows, key, value, description):
    matches = [row for row in rows if row.get(key) == value]
    if len(matches) != 1:
        raise GroundTruthError(f'{description} reference is missing or ambiguous')
    return matches[0]


def validate_assessment(record, suite_record, defects):
    """Return a valid review; callers must also reject conflicting duplicate reviews.

    ``defects`` maps (Agent ID, defect ID) to a validated manifest defect. This is
    an evidence association check, not an independent verification of the human
    review's factual conclusion. No Judge verdict is converted into a decision.
    """
    agent_id, index, attempt_id, defect_id = assessment_identity(record)
    defect = defects.get((agent_id, defect_id))
    if defect is None:
        raise GroundTruthError('defect reference is unavailable')
    if hash_field(record, 'ground_truth_sha256') != defect['ground_truth_sha256']:
        raise GroundTruthError('defect revision is stale')
    for field in ('case_reproduced', 'judge_detected'):
        if field not in record or record[field] is not None and type(record[field]) is not bool:
            raise GroundTruthError(f'{field} must be a boolean or null')
    if record['judge_detected'] is True and record['case_reproduced'] is not True:
        raise GroundTruthError('Judge discovery requires a reproduced defect')
    text_field(record, 'reviewed_by')
    timestamp_field(record, 'reviewed_at')
    text_field(record, 'rationale')
    plan, snapshot = suite_record.get('plan'), suite_record['snapshot']
    if not isinstance(plan, dict) or plan.get('suite_id') != snapshot.get('suite_id'):
        raise GroundTruthError('canonical Suite provenance is unavailable')
    agent = _unique_match(plan.get('agents', []), 'agent_id', agent_id, 'Agent plan')
    if agent.get('source_sha256') != defect['source_sha256']:
        raise GroundTruthError('Agent source revision does not match the defect')
    job = _unique_match(snapshot.get('jobs', []), 'agent_id', agent_id, 'Agent result')
    case = _unique_match(job.get('cases', []), 'case_index', index, 'Case slot')
    prepared = case.get('prepared_case') or {}
    case_hash = hash_field(record, 'case_sha256')
    if prepared.get('artifact_sha256') != case_hash:
        raise GroundTruthError('evaluated Case digest does not match')
    directory = Path(suite_record['directory']).resolve()
    artifact = text_field(prepared, 'artifact_path')
    artifact_path = within(directory, directory / artifact)
    if file_digest(artifact_path) != case_hash:
        raise GroundTruthError('retained Case artifact digest does not match')
    attempt = _unique_match(case.get('attempts', []), 'attempt_id', attempt_id, 'Attempt')
    result = attempt.get('result')
    if not isinstance(result, dict) or hash_field(record, 'result_sha256') != digest_json(result):
        raise GroundTruthError('persisted Attempt result digest does not match')
    benchmark = result.get('benchmark') or {}
    artifacts = result.get('artifacts') or {}
    states = [attempt, result, benchmark, artifacts]
    if any(not isinstance(state, dict) for state in states):
        raise GroundTruthError('Attempt evidence state is invalid')
    if any(state.get('error') for state in states):
        raise GroundTruthError('Attempt has an execution error')
    if any(state.get('host_acceptance') == 'rejected' for state in states):
        raise GroundTruthError('Attempt evidence was rejected by the host')
    received = artifacts.get('received_report') or {}
    if isinstance(received, dict) and received.get('host_accepted') is False:
        raise GroundTruthError('Attempt report was rejected by the host')
    if any(state.get('evidence_status') in {'missing', 'failed', 'invalid'}
           or state.get('host_trace_validation') in {'failed', 'invalid'} for state in states):
        raise GroundTruthError('Attempt evidence is incomplete or invalid')
    has_decision = any(record[field] is not None for field in ('case_reproduced', 'judge_detected'))
    if has_decision and (attempt.get('execution_status') or execution_status(result)) != 'completed':
        raise GroundTruthError('review decisions require a completed execution')
    if record['judge_detected'] is not None:
        report = benchmark.get('report')
        if not isinstance(report, dict) or not report:
            raise GroundTruthError('Judge assessment requires a persisted report')
    return record


def load_assessments(suite_record, defects):
    """Read every time: review changes do not require a new Suite event."""
    snapshot = suite_record['snapshot']
    suite_id = snapshot.get('suite_id')
    prefix = f'Ground truth Suite {label(suite_id)}'
    try:
        directory = Path(suite_record['directory']).resolve()
        path = within(directory, directory / 'ground_truth' / 'assessments.json')
        if not path.exists():
            return [], []
        document = read_json(path)
        if document.get('schema') != ASSESSMENTS_SCHEMA:
            raise GroundTruthError('unsupported assessments schema')
        if document.get('suite_id') != suite_id:
            raise GroundTruthError('assessment Suite identity does not match')
        records = records_field(document, 'assessments')
    except GroundTruthError as error:
        return [], [f'{prefix}: {error}']
    warnings, groups = [], {}
    for index, record in enumerate(records):
        try:
            identity = assessment_identity(record)
            groups.setdefault(identity, []).append((index, record))
        except GroundTruthError as error:
            warnings.append(f'{prefix} assessment {index}: {error}')
    accepted = []
    for values in groups.values():
        index, record = values[0]
        try:
            if len({digest_json(value) for _, value in values}) != 1:
                raise GroundTruthError('conflicting assessments for the same defect and Attempt')
            accepted.append(validate_assessment(record, suite_record, defects))
        except (GroundTruthError, ValueError, TypeError, RecursionError) as error:
            reason = str(error) if isinstance(error, GroundTruthError) else 'invalid assessment structure'
            warnings.append(f'{prefix} assessment {index}: {reason}')
    return accepted, warnings
