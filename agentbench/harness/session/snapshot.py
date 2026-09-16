"""Pure projection of persisted ordered events into the live multi-Case view."""

from collections import Counter
from copy import deepcopy

from .attempts import apply_case_event, new_case
from .capabilities import manual_recovery


def suite_snapshot(plan, events):
    """Build all planned slots plus Attempt history; newer activity reopens a Suite."""
    suite_id = plan['suite_id']
    jobs = {agent['agent_id']: {'agent_id': agent['agent_id'], 'registration_index': index,
                               'job_id': None, 'status': 'queued', 'generation_status': 'queued',
                               'cases': [new_case(suite_id, agent['agent_id'], slot)
                                         for slot in range(agent['case_count'])]}
            for index, agent in enumerate(plan['agents'])}
    state, summary, error, revision = 'planned', None, None, 0
    commands = {}
    for event in events:
        revision = event.get('sequence', revision + 1)
        kind = event.get('event')
        if kind in {'suite_resumed', 'suite_started', 'run_started', 'suite_resume_started'}:
            state, summary, error = 'running', None, None
        elif kind == 'suite_completed':
            state, summary = 'complete', deepcopy(event.get('summary'))
        elif kind in {'suite_failed', 'suite_interrupted'}:
            state, error = 'interrupted', deepcopy(event.get('error'))
        if event.get('command_id'):
            commands[event['command_id']] = deepcopy(event)
        job = jobs.get(event.get('agent_id'))
        if job is None:
            continue
        if kind in {'agent_queued', 'agent_started'}:
            job['job_id'] = event.get('job_id') or job['job_id']
            job['status'] = 'queued' if kind == 'agent_queued' else 'running'
        if event.get('phase') == 'generate' and event.get('event') == 'progress':
            job['generation_status'] = {'started': 'running'}.get(event.get('status'), event.get('status'))
        index = event.get('case_index')
        if type(index) is int and 0 <= index < len(job['cases']):
            apply_case_event(job['cases'][index], event)
            if kind in {'attempt_dispatched', 'case_started', 'case_attempt_started', 'retry_scheduled', 'case_retry_scheduled',
                        'case_recovery_started', 'case_reconciling'}:
                state, summary, error = 'running', None, None
        if kind == 'agent_completed':
            item = event.get('item') or {}
            for result in item.get('case_results', ()):
                index = result.get('case_index')
                if type(index) is not int or not 0 <= index < len(job['cases']):
                    continue
                case = job['cases'][index]
                # Aggregates are only fallback records. Case events own current attempts.
                if case['result'] is None and not case['attempts']:
                    apply_case_event(case, {**result, 'event': 'case_completed', 'case_result': result,
                                            'timestamp': event.get('timestamp')})
            job['status'] = item.get('status') or event.get('status', 'failed')
            job['preparation_error'] = item.get('preparation_error')
    cases = [case for job in jobs.values() for case in job['cases']]
    for job in jobs.values():
        job['counts'] = dict(Counter(case['execution_status'] for case in job['cases']))
        if any(case['execution_status'] in {'dispatched', 'running', 'retrying', 'waiting_judge', 'reconciling', 'retry_wait'}
               for case in job['cases']):
            job['status'] = 'running'
        for case in job['cases']:
            case['agent_job_id'] = job['job_id']
            case.update(manual_recovery(case))
    counts = dict(Counter(case['execution_status'] for case in cases))
    counts.update(planned=len(cases), completed=sum(case['execution_status'] == 'completed' for case in cases),
                  judge_received=sum(case['judge_status'] is not None for case in cases),
                  host_accepted=sum(case['host_acceptance'] == 'accepted' for case in cases))
    return {'schema': 'abb.suite.snapshot.v1', 'suite_id': suite_id, 'revision': revision,
            'origin_suite_id': plan.get('origin_suite_id'),
            'state': state, 'jobs': list(jobs.values()), 'counts': counts,
            'judge_counts': dict(Counter(case['judge_status'] for case in cases if case['judge_status'])),
            'summary': summary, 'error': error, 'commands': list(commands.values()),
            'selected_agent_ids': list(jobs),
            'selected_case_counts': {job['agent_id']: len(job['cases']) for job in jobs.values()}}
