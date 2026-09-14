"""Public manual-recovery actions derived from persisted provider-neutral evidence."""

ACTIVE_STATES = frozenset({'dispatched', 'running', 'retrying', 'retry_wait',
                            'waiting_judge', 'reconciling'})
NONTERMINAL_REQUESTS = frozenset({'prepared', 'queued', 'pending', 'accepted', 'submitted',
                                 'running', 'in_progress', 'unknown', 'uncertain'})


def manual_recovery(case):
    """Return a capability, never infer safe replay from an error message or retryable flag."""
    def blocked(reason):
        return {'can_retry': False, 'recovery_action': None, 'recovery_reason': reason}

    status = case['execution_status']
    if status == 'completed':
        return blocked('This Case already has a completed evaluation')
    if status in ACTIVE_STATES:
        return blocked('An active or interrupted Attempt must be reconciled by Suite recovery')
    result = case.get('result') or {}
    artifacts = result.get('artifacts') or {}
    recovery = artifacts.get('recovery') or {}
    prepared = case.get('prepared_case')
    reusable = bool(prepared and prepared.get('artifact_path') and prepared.get('artifact_sha256'))
    if prepared and not reusable:
        return blocked('This Case has no persisted artifact that can be reused')
    action = recovery.get('action')
    if action in {'resume_request', 'inspect_attempt'} and reusable:
        return {'can_retry': True, 'recovery_action': 'resume_request',
                'recovery_reason': recovery.get('reason', 'Recover the original Attempt without Agent replay')}
    if action == 'inspect_request' or recovery.get('allow_replay') is False:
        return blocked(recovery.get('reason', 'The original request must be inspected before submitting new work'))
    request = artifacts.get('sdk_request') or {}
    if request.get('status') in NONTERMINAL_REQUESTS:
        return blocked('The original SDK request has not reached a confirmed terminal state')
    if artifacts.get('cleanup_status') not in (None, 'succeeded'):
        return blocked('The previous execution has not confirmed resource cleanup')
    if reusable:
        return {'can_retry': True, 'recovery_action': 'replay_case',
                'recovery_reason': 'Reuse the saved Case in a new isolated Attempt from its first Input'}
    if case.get('attempts'):
        return blocked('The original Case artifact is required before this Attempt can be recovered')
    error = artifacts.get('sdk_error') or {}
    if ((error.get('client_request_id') or error.get('request_id')) and not request
            and recovery.get('allow_replay') is not True):
        return blocked('The original generation request needs a confirmed disposition before replacement')
    return {'can_retry': True, 'recovery_action': 'generate_case',
            'recovery_reason': 'Generate only this missing Case slot'}
