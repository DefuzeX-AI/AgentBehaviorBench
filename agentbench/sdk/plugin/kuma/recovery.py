"""KUMA-specific recovery permission projected into a provider-neutral action."""

# Preserve the pinned SDK transport's automatic-retry prohibition, independently
# of its public retryable flag. The host must never retry these as new work.
AUTOMATIC_RETRY_BLOCKED = frozenset({
    'service_busy', 'upstream_unavailable', 'upload_not_configured', 'capacity_exceeded',
    'request_failed', 'operation_failed', 'model_invalid_result', 'model_invalid_response',
    'model_output_policy_conflict', 'model_output_privacy_rejected', 'request_in_progress',
    'strategy_group_invalid', 'invalid_request', 'idempotency_conflict', 'resource_not_found',
    'invalid_api_key', 'forbidden', 'quota_exhausted', 'invalid_case_integrity',
    'case_artifact_invalid', 'case_origin_invalid', 'sensitive_data_blocked',
})
TRANSIENT_AGENT_ERRORS = frozenset({
    'TimeoutError', 'ConnectionError', 'ConnectTimeout', 'ReadTimeout',
    'ConnectError', 'ReadError', 'RemoteProtocolError', 'APIConnectionError', 'APITimeoutError',
})


def classify_failure(artifacts):
    """Choose recovery only from validated identity/status and host evidence.

    This helper performs no I/O. Agent replay requires a separately established
    isolation/idempotence capability, so unknown execution failures stay blocked.
    """
    error = artifacts.get('sdk_error') or {}
    phase = artifacts.get('phase')
    request = artifacts.get('sdk_request') or {}
    blocked = {'action': 'blocked', 'automatic': False, 'phase': phase,
               'reason': 'No safe recovery is established for this failure'}
    if error.get('code') in AUTOMATIC_RETRY_BLOCKED:
        return {**blocked, 'reason': 'SDK error prohibits automatic retry; preserve the original request'}
    native = artifacts.get('native_failure') or {}
    transient_agent_failure = (native.get('error_type') in TRANSIENT_AGENT_ERRORS
                               and (artifacts.get('completion') or {}).get('execution') == 'failed')
    container_timeout = (artifacts.get('host_error_type') == 'TimeoutExpired'
                         and artifacts.get('host_phase') == 'execute' and phase != 'judge')
    if (artifacts.get('safe_case_replay') is True
            and artifacts.get('cleanup_status') == 'succeeded'
            and artifacts.get('host_trace_validation') != 'failed'
            and not request and (transient_agent_failure or container_timeout)):
        return {'action': 'replay_case', 'automatic': True, 'phase': 'execution',
                'reason': 'Audited Agent permits isolated replay after a transient execution failure'}
    if request.get('status') == 'failed':
        return {**blocked, 'reason': 'The original SDK request is terminally failed'}
    if (artifacts.get('cleanup_status') != 'succeeded'
            or artifacts.get('host_trace_validation') != 'succeeded'):
        return {**blocked, 'reason': 'Original cleanup and host trace acceptance are required before recovery'}
    evidence = artifacts.get('completion') or {}
    if any(evidence.get(key) != value for key, value in (
        ('execution', 'succeeded'), ('otel', 'complete'),
        ('submission', 'committed'), ('evidence', 'captured'))):
        return {**blocked, 'reason': 'Original Agent execution and submitted evidence are incomplete'}
    if (phase != 'judge' or request.get('request_type') != 'judgment'
            or not request.get('client_request_id')
            or request.get('status') not in {'prepared', 'queued', 'running', 'succeeded'}):
        return blocked
    return {'action': 'resume_request', 'automatic': True, 'phase': phase,
            'client_request_id': request['client_request_id'],
            'reason': 'Resume the original Judge request without replaying Agent execution'}
