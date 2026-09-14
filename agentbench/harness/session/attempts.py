"""Reduce Case and Attempt events without confusing Judge verdicts with execution."""

from copy import deepcopy


def new_case(suite_id, agent_id, index):
    return {'suite_id': suite_id, 'agent_id': agent_id, 'case_index': index,
            'case_id': None, 'status': 'queued', 'execution_status': 'pending_generation',
            'judge_status': None, 'phase': 'generate', 'stage': None,
            'job_id': None, 'artifact_run_id': None, 'prepared_case': None,
            'active_attempt_id': None, 'attempts': [], 'retry_count': 0,
            'retry_at': None, 'can_retry': False, 'recovery_action': None,
            'result': None, 'error': None, 'host_acceptance': None, 'resumable': False,
            'report_received': False, 'received_report': None}


def execution_status(result):
    if result.get('execution_status'):
        return result['execution_status']
    benchmark = result.get('benchmark') or {}
    if benchmark.get('report') is not None and not result.get('error'):
        return 'completed'
    return {'succeeded': 'completed', 'failed': 'needs_attention',
            'cancelled': 'cancelled', 'skipped': 'skipped'}.get(result.get('status'), 'needs_attention')


def find_attempt(case, event, *, create=False):
    attempt_id = event.get('attempt_id') or event.get('job_id')
    if attempt_id is None:
        attempt_id = case['active_attempt_id']
    match = next((value for value in case['attempts'] if value['attempt_id'] == attempt_id), None)
    if match is None and create and attempt_id is not None:
        number = event.get('attempt_number') or len(case['attempts']) + 1
        match = {'attempt_id': attempt_id, 'attempt_number': number,
                 'job_id': event.get('job_id'), 'artifact_run_id': None,
                 'status': 'running', 'execution_status': 'running', 'phase': 'execute',
                 'error': None, 'judge_status': None, 'result': None,
                 'host_acceptance': None, 'started_at': event.get('timestamp')}
        case['attempts'].append(match)
        case['attempts'].sort(key=lambda value: value['attempt_number'])
        case['active_attempt_id'] = case['attempts'][-1]['attempt_id']
    return match


def apply_case_event(case, event):
    kind = event.get('event')
    result = event.get('case_result')
    data = {**event, **({key: value for key, value in result.items() if value is not None}
                        if isinstance(result, dict) else {})}
    if kind == 'case_retry_cancelled':
        case.update(execution_status='cancelled', status='cancelled', retry_at=None)
        return
    if kind == 'case_reused':
        case['origin'] = deepcopy(event.get('origin'))
        return
    if kind == 'case_prepared':
        prepared = event.get('prepared_case') or event.get('case')
        if isinstance(prepared, dict):
            case['prepared_case'] = deepcopy(prepared)
            case['case_id'] = prepared.get('case_id')
            case['resumable'] = bool(prepared.get('artifact_path') and prepared.get('artifact_sha256'))
        if not case['attempts']:
            case.update(execution_status='ready', status='queued', phase='execute', error=None,
                        result=None, can_retry=False, recovery_action=None)
        return
    if kind in {'case_preparation_failed', 'case_generation_failed'}:
        case.update(execution_status='needs_attention', status='failed', phase='generate',
                    error=event.get('error'), can_retry=bool(event.get('can_retry', False)),
                    recovery_action=event.get('recovery_action'))
        return
    artifacts = data.get('artifacts') or {}
    generation = data.get('phase') == 'generate' or artifacts.get('phase') == 'case_generation'
    before_execution = generation or artifacts.get('phase') == 'case_reuse'
    if generation:
        data['phase'] = 'generate'
    create = (kind in {'attempt_dispatched', 'case_started', 'case_attempt_started', 'case_attempt_failed'}
              or kind == 'case_completed' and data.get('status') != 'skipped' and not before_execution)
    attempt = find_attempt(case, data, create=create)
    target = attempt if attempt is not None else case
    for key in ('job_id', 'artifact_run_id', 'phase', 'stage', 'case_id', 'artifact_directory',
                'recovery_action', 'can_retry', 'retry_at', 'retry_count', 'host_acceptance'):
        if data.get(key) is not None:
            target[key] = deepcopy(data[key])
    artifacts = data.get('artifacts') or {}
    if isinstance(artifacts, dict):
        target['artifact_run_id'] = artifacts.get('artifact_run_id') or target.get('artifact_run_id')
    if kind == 'attempt_dispatched':
        target.update(status='dispatched', execution_status='dispatched', retry_at=None, error=None)
    elif kind in {'case_started', 'case_attempt_started'}:
        retrying = target['attempt_number'] > 1 or event.get('status') == 'retrying'
        target.update(status='running', execution_status='retrying' if retrying else 'running',
                      retry_at=None, error=None)
    elif kind == 'case_queued':
        target.update(status='queued', execution_status='queued')
    elif kind in {'retry_scheduled', 'case_retry_scheduled'}:
        target.update(status='retry_wait', execution_status='retry_wait', can_retry=False,
                      retry_at=event.get('retry_at'), error=event.get('error') or target.get('error'))
    elif kind in {'case_reconciling', 'case_recovery_started'}:
        target.update(status='running', execution_status='reconciling', phase='recover')
    elif kind in {'case_completed', 'case_attempt_failed'}:
        target['status'] = data.get('status', 'failed')
        target['result'] = deepcopy(result)
        target['error'] = data.get('error')
        target['execution_status'] = execution_status(data)
        report = ((result or {}).get('benchmark') or {}).get('report') or {}
        received = artifacts.get('received_report') or {}
        target['received_report'] = deepcopy(received) or None
        target['report_received'] = bool(report or received)
        target['judge_status'] = data.get('judge_status') or report.get('status') or received.get('status')
        acceptance = ('accepted' if report and not target['error'] else
                      'accepted' if received.get('host_accepted') is True else 'rejected' if received else None)
        target['host_acceptance'] = data.get('host_acceptance', acceptance)
        target['finished_at'] = event.get('timestamp')
        target['retry_at'] = None
    elif kind in {'progress', 'step_started', 'step_completed', 'step_failed'}:
        if target.get('execution_status') not in {'completed', 'needs_attention', 'blocked', 'cancelled', 'skipped', 'retry_wait'}:
            target['execution_status'] = 'waiting_judge' if event.get('stage') in {'judge', 'judging', 'judge_wait'} else target.get('execution_status', 'running')
    # Delayed events for an old Attempt update its history, never the current row.
    if attempt is not None and attempt['attempt_id'] == case['active_attempt_id']:
        for key in ('status', 'execution_status', 'judge_status', 'phase', 'stage', 'job_id',
                    'artifact_run_id', 'artifact_directory', 'result', 'error', 'retry_at',
                    'host_acceptance', 'can_retry', 'recovery_action', 'report_received', 'received_report'):
            case[key] = deepcopy(attempt.get(key))
        case['retry_count'] = max(0, attempt['attempt_number'] - 1, attempt.get('retry_count') or 0)
        if attempt.get('case_id'):
            case['case_id'] = attempt['case_id']
