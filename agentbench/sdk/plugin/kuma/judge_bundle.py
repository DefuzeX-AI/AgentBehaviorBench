"""Persist and restore public KUMA contracts without implementing its upload wire."""
from kuma import (Case, KumaInput, Submission, HistoryItem, CaptureStatus,
                  CaptureComponent, FileEvidence, FileChange, to_json)
from kuma.providers import JudgeContext

SCHEMA = 'abb.kuma.judge-context.v1'


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
