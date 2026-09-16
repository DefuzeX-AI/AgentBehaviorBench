"""Attempt projection remains correct across retries, old aggregates and refresh."""

from agentbench.harness.session.snapshot import suite_snapshot


PLAN = {'suite_id': 'suite_state', 'agents': [{'agent_id': 'react', 'case_count': 2},
                                           {'agent_id': 'research', 'case_count': 3}]}


def event(kind, *, number=1, agent='react', index=0, **data):
    return {'event': kind, 'agent_id': agent, 'case_index': index,
            'attempt_id': f'attempt-{number}', 'attempt_number': number,
            'job_id': f'job-{number}', **data}


def test_retry_history_and_all_cases_survive_old_completed_suite_and_late_events():
    failure = {'agent_id': 'react', 'case_index': 0, 'job_id': 'job-1', 'status': 'failed',
               'error': {'type': 'TimeoutError', 'message': 'timeout'}, 'benchmark': None}
    rows = [event('case_started', artifact_run_id='run-1'),
            event('case_attempt_failed', case_result=failure),
            {'event': 'suite_completed', 'summary': {'failed': 1}},
            {'event': 'suite_resumed'},
            event('retry_scheduled', retry_at='2026-09-14T17:00:00Z'),
            event('case_started', number=2, artifact_run_id='run-2'),
            event('case_completed', case_result=failure)]
    snapshot = suite_snapshot(PLAN, rows)
    case = snapshot['jobs'][0]['cases'][0]
    assert snapshot['state'] == 'running' and snapshot['summary'] is None
    assert snapshot['counts']['planned'] == 5
    assert case['execution_status'] == 'retrying' and case['artifact_run_id'] == 'run-2'
    assert case['active_attempt_id'] == 'attempt-2' and case['retry_count'] == 1
    assert len(case['attempts']) == 2 and case['attempts'][0]['error']['type'] == 'TimeoutError'


def test_waiting_retry_is_distinct_from_an_unrecoverable_failure():
    rows = [event('case_started'), event('case_attempt_failed', status='failed',
                                          error={'type': 'ConnectionError', 'message': 'closed'}),
            event('retry_scheduled', retry_at='2026-09-14T17:00:00Z')]
    snapshot = suite_snapshot(PLAN, rows)
    case = snapshot['jobs'][0]['cases'][0]
    assert case['execution_status'] == 'retry_wait'
    assert case['retry_at'] == '2026-09-14T17:00:00Z'
    assert case['error']['type'] == 'ConnectionError'


def test_behavior_issue_is_a_completed_evaluation_and_not_a_retry_candidate():
    result = {'agent_id': 'react', 'case_index': 0, 'job_id': 'job-1', 'status': 'failed',
              'benchmark': {'report': {'status': 'issue'}}, 'error': None}
    snapshot = suite_snapshot(PLAN, [event('case_started'), event('case_completed', case_result=result)])
    case = snapshot['jobs'][0]['cases'][0]
    assert case['status'] == 'failed' and case['execution_status'] == 'completed'
    assert case['judge_status'] == 'issue' and case['can_retry'] is not True
    assert snapshot['counts']['completed'] == snapshot['counts']['judge_received'] == 1


def test_partial_case_preparation_preserves_original_slot_indices():
    rows = [{'event': 'case_prepared', 'agent_id': 'research', 'case_index': index,
             'prepared_case': {'case_index': index, 'case_id': f'case-{index}'}} for index in (0, 2)]
    rows.append({'event': 'case_generation_failed', 'agent_id': 'research', 'case_index': 1,
                 'error': {'type': 'GenerationError', 'message': 'invalid'}})
    cases = suite_snapshot(PLAN, rows)['jobs'][1]['cases']
    assert [case['case_index'] for case in cases] == [0, 1, 2]
    assert [case['execution_status'] for case in cases] == ['ready', 'needs_attention', 'ready']


def test_old_agent_aggregate_cannot_replace_new_attempt():
    old = {'agent_id': 'react', 'case_index': 0, 'job_id': 'job-1', 'status': 'failed',
           'error': {'type': 'TimeoutError', 'message': 'old'}}
    rows = [event('case_started'), event('case_completed', case_result=old),
            event('case_started', number=2),
            {'event': 'agent_completed', 'agent_id': 'react',
             'item': {'status': 'failed', 'case_results': [old]}}]
    case = suite_snapshot(PLAN, rows)['jobs'][0]['cases'][0]
    assert case['execution_status'] == 'retrying'
    assert case['result'] is None
    assert case['attempts'][0]['result'] == old


def test_dispatched_attempt_survives_before_worker_start_and_does_not_look_completed():
    snapshot = suite_snapshot(PLAN, [event('attempt_dispatched')])
    case = snapshot['jobs'][0]['cases'][0]
    assert case['execution_status'] == 'dispatched'
    assert case['active_attempt_id'] == 'attempt-1'
    assert len(case['attempts']) == 1
    assert snapshot['state'] == 'running'


def test_generation_failure_does_not_invent_execution_attempt():
    result = {'agent_id': 'react', 'case_index': 0, 'job_id': 'generation-job', 'status': 'failed',
              'execution_status': 'blocked', 'attempt_id': None,
              'artifacts': {'phase': 'case_generation'},
              'error': {'type': 'CaseGenerationFailed', 'message': 'invalid'}}
    snapshot = suite_snapshot(PLAN, [{'event': 'case_completed', 'agent_id': 'react',
                                      'case_index': 0, 'case_result': result}])
    case = snapshot['jobs'][0]['cases'][0]
    assert case['attempts'] == [] and case['execution_status'] == 'blocked'
    assert case['result'] == result and case['phase'] == 'generate'


def test_recovery_count_does_not_require_a_new_attempt_and_commands_are_deduplicated():
    rows = [event('case_started'), event('case_recovery_started', retry_count=3),
            {'event': 'command_accepted', 'command_id': 'command-1'},
            {'event': 'command_completed', 'command_id': 'command-1'}]
    snapshot = suite_snapshot(PLAN, rows)
    case = snapshot['jobs'][0]['cases'][0]
    assert case['retry_count'] == 3 and len(case['attempts']) == 1
    assert snapshot['commands'] == [{'event': 'command_completed', 'command_id': 'command-1'}]


def test_host_rejected_report_remains_visible_without_counting_as_completed():
    result = {'agent_id': 'react', 'case_index': 0, 'job_id': 'job-1', 'status': 'failed',
              'error': {'type': 'TraceValidationError', 'message': 'rejected'},
              'artifacts': {'received_report': {'status': 'issue', 'report_id': 'report-1',
                             'host_accepted': False}}}
    snapshot = suite_snapshot(PLAN, [event('case_started'), event('case_completed', case_result=result)])
    case = snapshot['jobs'][0]['cases'][0]
    assert case['judge_status'] == 'issue' and case['report_received'] is True
    assert case['host_acceptance'] == 'rejected'
    assert snapshot['counts']['completed'] == snapshot['counts']['host_accepted'] == 0
    assert snapshot['counts']['judge_received'] == 1


def test_retry_capability_is_separate_from_automatic_replay_capability():
    prepared = {'event': 'case_prepared', 'agent_id': 'react', 'case_index': 0,
                 'prepared_case': {'case_index': 0, 'artifact_path': '/saved/case.json', 'artifact_sha256': 'a' * 64}}
    failure = {'agent_id': 'react', 'case_index': 0, 'job_id': 'job-1', 'status': 'failed',
               'error': {'type': 'ExecutionError', 'message': 'terminal'},
               'artifacts': {'safe_case_replay': False, 'cleanup_status': 'succeeded'}}
    rows = [prepared, event('case_started'), event('case_completed', case_result=failure)]
    case = suite_snapshot(PLAN, rows)['jobs'][0]['cases'][0]
    assert case['can_retry'] is True and case['recovery_action'] == 'replay_case'
    failure['artifacts']['cleanup_status'] = 'failed'
    case = suite_snapshot(PLAN, rows)['jobs'][0]['cases'][0]
    assert case['can_retry'] is False
