"""Accept independently validated Case artifacts without losing successful slots."""

from types import MappingProxyType
from agentbench.harness.result import CaseResult


def accept_preparation(scheduler, state, job, outcome):
    """Apply a worker's complete or partial preparation on the coordinator thread."""
    if outcome.error is not None:
        state.preparation_error = outcome.error
        if not scheduler.continue_on_error:
            scheduler.admission = False
        for index in job.case_indices or tuple(state.identities):
            if index not in state.results:
                result = CaseResult(job.registration.agent_id, index, state.identities[index]['job_id'], 'skipped',
                                    error_type='CaseSkipped', error_message='Case batch preparation failed')
                state.results[index] = result
                scheduler._publish_case(state, result)
        return
    # Capture the entire accepted batch identity before any consumer can fail.
    for case in outcome.cases:
        state.identities[case.case_index] = MappingProxyType({**state.identities[case.case_index], 'case_id': case.case_id})
    for case in outcome.cases:
        case = scheduler.retain_case(job.registration.agent_id, case)
        state.prepared[case.case_index] = case
        state.pending.append(case)
        identity = MappingProxyType({**state.identities[case.case_index], 'case_id': case.case_id})
        state.identities[case.case_index] = identity
        scheduler._publish({**identity, 'event': 'case_prepared', 'prepared_case': case, 'status': 'prepared'})
        scheduler._publish({**identity, 'event': 'case_queued', 'status': 'queued'})
    if state.pending and state not in scheduler.ready:
        scheduler.ready.append(state)
    for failure in outcome.failures:
        identity = state.identities[failure.case_index]
        artifacts = dict(failure.artifacts or {})
        artifacts.update(phase=failure.phase, sdk_error={
            'code': failure.code, 'retryable': failure.retryable,
            'client_request_id': failure.client_request_id, 'request_id': failure.request_id})
        result = CaseResult(job.registration.agent_id, failure.case_index, identity['job_id'], 'failed',
                            error_type=failure.error_type, error_message=failure.error_message, artifacts=artifacts)
        state.results[result.case_index] = result
        scheduler._publish_case(state, result)
        if (artifacts.get('recovery') or {}).get('pause_preparation') is True:
            pause_pending_preparation(scheduler, job.registration.agent_id, failure.code)
    for index in outcome.unattempted_indices:
        result = CaseResult(job.registration.agent_id, index, state.identities[index]['job_id'], 'skipped',
                            error_type='CasePreparationBlocked', error_message='Case generation was not attempted')
        state.results[index] = result
        scheduler._publish_case(state, result)
    if (outcome.failures or outcome.unattempted_indices) and not scheduler.continue_on_error:
        scheduler.admission = False


def pause_pending_preparation(scheduler, source_agent_id, code):
    """Pause undispatched preparation sharing this Suite's SDK configuration.

    Already accepted Cases can finish. In-flight preparation owns its own
    cleanup and partial outcomes; the coordinator only removes queued work.
    """
    while scheduler.unprepared:
        state = scheduler.unprepared.popleft()
        state.started = True
        for index in state.preparation.case_indices or tuple(state.identities):
            if index in state.results or index in state.prepared:
                continue
            identity = state.identities[index]
            result = CaseResult(state.preparation.registration.agent_id, index, identity['job_id'], 'skipped',
                error_type='CasePreparationPaused', error_message='Shared SDK configuration blocked new Case generation',
                artifacts={'phase': 'case_generation', 'blocked_by': {'agent_id': source_agent_id, 'code': code},
                           'recovery': {'action': 'generate_case', 'automatic': False}})
            state.results[index] = result
            scheduler._publish_case(state, result)
        scheduler._finish_agent(state)
