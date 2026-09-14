"""Build remaining work from verified persisted Case and Attempt records."""

from dataclasses import replace

from agentbench.harness.result import CaseResult
from agentbench.harness.session import SuiteProvenanceError, case_from_json
from agentbench.harness.session.capabilities import manual_recovery
from .state import AgentSeed


def resume_seeds(store, *, selection=None, replay=False):
    """Return Agent seeds; completed verdicts never enter the recovery queue.

    Args:
        store: Locked SuiteStore with a validated plan and intact Case files.
        selection: Optional set of (agent_id, zero-based case_index) positions.
        replay: Explicit permission to rerun a failed Case from its first Input.
    Returns:
        Mapping of Agent ID to scheduling seeds. Unresolved remote operations
        and unconfirmed container cleanup stay blocked instead of being replayed.
    """
    seeds = {}
    snapshot = store.snapshot()
    available = {(job['agent_id'], case['case_index']) for job in snapshot['jobs'] for case in job['cases']}
    if selection is not None and not set(selection).issubset(available):
        raise ValueError('Recovery selection is outside the saved Suite')
    for job in snapshot['jobs']:
        agent = job['agent_id']
        prepared = {}
        seed = AgentSeed(prepared=prepared)
        for case in job['cases']:
            index = case['case_index']
            attempts = case.get('attempts') or []
            seed.attempts[index] = max((attempt['attempt_number'] for attempt in attempts), default=0)
            seed.retries[index] = case.get('retry_count') or 0
            if case['execution_status'] == 'retry_wait' and isinstance(case.get('retry_at'), (int, float)):
                seed.retry_at[index] = case['retry_at']
            prior = case_from_json(case['result']) if case.get('result') else None
            selected = selection is None or (agent, index) in selection
            if prior is not None and (case['execution_status'] == 'completed' or not selected):
                seed.results[index] = prior
                continue
            if not selected:
                seed.results[index] = _blocked(agent, case, 'Not selected for this recovery', 'skipped')
                continue
            try:
                saved = store.prepared_case(agent, index)
                if saved is None and store.plan.get('origin_suite_id'):
                    raise SuiteProvenanceError('A linked Suite requires the original saved Case for every slot; '
                                               'replacement Case generation is disabled')
                if saved is not None and saved.artifact_path is None:
                    raise SuiteProvenanceError('This Case was prepared only in memory and cannot be reused after restart')
                if saved is not None:
                    prepared[index] = saved
            except (SuiteProvenanceError, OSError) as exc:
                seed.results[index] = _blocked(agent, case, str(exc), prevent_replay=True, artifact_block=True)
                continue
            recovery = ((prior.artifacts or {}).get('recovery') or {}) if prior else {}
            if recovery.get('action') == 'restore_case' and index in prepared:
                # Exact bytes are available again. Restore the previous decision;
                # verification does not grant permission to replay an unknown request.
                case = {**case, 'execution_status': recovery['previous_execution_status']}
                if recovery.get('previous_status') is None:
                    prior = None
                else:
                    restored = {**prior.artifacts, 'recovery': recovery.get('previous_recovery', {})}
                    error = recovery.get('previous_error') or {}
                    prior = replace(prior, status=recovery['previous_status'], artifacts=restored,
                                    error_type=error.get('type'), error_message=error.get('message'))
                    from agentbench.harness.session import case_to_json
                    case['result'] = case_to_json(prior)
            if attempts and case['execution_status'] in {'dispatched', 'running', 'retrying', 'waiting_judge', 'reconciling'}:
                directory = case.get('artifact_directory')
                if directory and index in prepared:
                    pending = _blocked(agent, case, 'Reconcile the original Attempt before continuing')
                    seed.recoveries[index] = replace(pending, artifacts={
                        'directory': directory, 'recovery': {'action': 'inspect_attempt', 'automatic': False}})
                else:
                    seed.results[index] = _blocked(agent, case, 'Interrupted Attempt lacks recoverable artifacts',
                                                   prevent_replay=True)
                continue
            if prior is not None:
                recovery = (prior.artifacts or {}).get('recovery') or {}
                capability = manual_recovery(case)
                scheduled = (case['execution_status'] == 'retry_wait'
                             and recovery.get('action') in {'replay_case', 'resume_request'})
                if recovery.get('action') in {'resume_request', 'inspect_attempt'} and index in prepared:
                    seed.recoveries[index] = prior
                elif not capability['can_retry'] and not scheduled:
                    seed.results[index] = prior
                elif index in prepared and (replay or recovery.get('action') == 'replay_case'
                                            or prior.status == 'skipped' and not attempts):
                    pass
                elif index not in prepared and not attempts and (
                        replay or prior.status == 'skipped' or recovery.get('action') == 'generate_case'):
                    pass
                else:
                    seed.results[index] = prior
                if (index in prepared and index not in seed.results
                        and case['execution_status'] in {'retry_wait', 'cancelled'}):
                    seed.waiting_results[index] = prior
        seeds[agent] = seed
    return seeds


def _blocked(agent, case, reason, status='failed', *, prevent_replay=False, artifact_block=False):
    artifacts = dict(((case.get('result') or {}).get('artifacts')) or {})
    if not case.get('attempts'):
        artifacts.setdefault('phase', 'case_reuse')
    if prevent_replay:
        previous = artifacts.get('recovery') or {}
        if artifact_block and previous.get('action') != 'restore_case':
            previous_result = case.get('result') or {}
            artifacts['recovery'] = {'action': 'restore_case', 'automatic': False, 'allow_replay': False,
                'reason': reason, 'previous_recovery': previous,
                'previous_status': previous_result.get('status'), 'previous_error': previous_result.get('error'),
                'previous_execution_status': case['execution_status']}
        elif not artifact_block:
            artifacts['recovery'] = {'action': 'blocked', 'automatic': False, 'allow_replay': False, 'reason': reason}
    return CaseResult(agent, case['case_index'], case.get('job_id') or 'undispatched', status,
                      case_id=case.get('case_id'), error_type='RecoveryRequired', error_message=reason,
                      artifacts=artifacts or None,
                      attempt_id=case.get('active_attempt_id'),
                      attempt_number=max((item['attempt_number'] for item in case.get('attempts', ())), default=1))
