"""Persist and restore public KUMA contracts without implementing its upload wire."""
from kuma import (Case, KumaInput, Submission, HistoryItem, CaptureStatus,
                  CaptureComponent, FileEvidence, FileChange, to_json)
from kuma.providers import JudgeContext

SCHEMA = 'abb.kuma.judge-context.v1'
REFERENCE_SCHEMA = 'abb.kuma.judge-context.refs.v1'


def save_context(files, run, case, *, upload_diff=False):
    """Publish a small Judge context referencing already committed step records."""
    import hashlib
    import json
    from agentbench.observe.store import redact
    value = redact(export_context(run, case, upload_diff=upload_diff), files.secrets)

    def reference(relative, expected):
        raw = (files.directory / relative).read_bytes()
        if json.loads(raw) != expected:
            raise ValueError('Judge reference differs from committed execution: ' + relative)
        return {'path': relative, 'sha256': hashlib.sha256(raw).hexdigest()}

    value['case'] = reference('case.json', value['case'])
    value['history'] = [
        {**item, 'test_input': reference(f'steps/{index:04d}/input.json', item['test_input']),
         'submission': reference(f'steps/{index:04d}/submission.json', item['submission'])}
        for index, item in enumerate(value['history'], 1)]
    value['schema'] = REFERENCE_SCHEMA
    files.save('judge/context.json', value)


def read_context(directory, value):
    """Resolve checked references at Judge execution, without rewriting files."""
    if value.get('schema') != REFERENCE_SCHEMA:
        return value
    import hashlib
    import json
    from agentbench.observe.artifact_paths import artifact_file
    remaining = 32 * 1024 * 1024

    def resolve(ref):
        nonlocal remaining
        path = artifact_file(directory, ref['path'])
        if path.stat().st_size > remaining:
            raise ValueError('Judge context exceeds the persisted evidence limit')
        raw = path.read_bytes()
        remaining -= len(raw)
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('Judge context reference was modified')
        return json.loads(raw)

    return {**value, 'schema': SCHEMA, 'case': resolve(value['case']),
            'history': [{**item, 'test_input': resolve(item['test_input']),
                         'submission': resolve(item['submission'])} for item in value['history']]}


def export_context(run, case, *, upload_diff=False):
    """Detach SDK-committed evidence before its container is released."""
    history = run.history
    return {'schema': SCHEMA, 'case': case, 'history': to_json(history),
            'run_status': 'completed', 'upload_diff': upload_diff,
            'evidence_summary': {
                'history_items': len(history),
                'stopped_early': len(history) < len(case['inputs']),
                'dropped_evidence_count': sum(item.submission.dropped_count for item in history)},
            'run_context': None}


def restore_context(value):
    """Use the SDK's validated public constructors; preserve all evidence fields."""
    if value.get('schema') != SCHEMA:
        raise ValueError('Unsupported Judge context schema')
    case_data = dict(value['case'])
    case_data['inputs'] = tuple(KumaInput(**item) for item in case_data['inputs'])
    case = Case(**case_data)
    history = []
    for item in value['history']:
        submission = dict(item['submission'])
        submission['capture_status'] = CaptureStatus(**{
            key: CaptureComponent(**component)
            for key, component in submission['capture_status'].items()})
        if submission.get('file_evidence') is not None:
            evidence = dict(submission['file_evidence'])
            evidence['changes'] = tuple(FileChange(**change) for change in evidence['changes'])
            submission['file_evidence'] = FileEvidence(**evidence)
        history.append(HistoryItem(KumaInput(**item['test_input']), Submission(**submission)))
    if not history or len(history) > len(case.inputs):
        raise ValueError('Incomplete Judge history')
    run_id = case.inputs[0].run_id
    for expected, item in zip(case.inputs, history):
        if (to_json(expected) != to_json(item.test_input)
                or item.submission.run_id != run_id):
            raise ValueError('Judge history does not match the original Case')
    if value['run_status'] != 'completed':
        raise ValueError('Judge requires completed input processing')
    return JudgeContext(case, tuple(history), value['run_status'],
                        value['evidence_summary'], value['upload_diff'], value.get('run_context'))
