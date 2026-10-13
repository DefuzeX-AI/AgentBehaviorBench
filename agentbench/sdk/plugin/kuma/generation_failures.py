"""Stable generation diagnostics; never infer retry permission from a message."""

from .error_artifacts import exception_record

# Codes from the pinned SDK's public error mapping. A credential/service-wide
# block pauses remaining slots; an ordinary Case rejection affects its own slot.
SHARED_GENERATION_BLOCKS = frozenset({
    'invalid_api_key', 'forbidden', 'strategy_group_forbidden', 'quota_exhausted',
    'rate_limited', 'service_busy', 'upstream_unavailable', 'capacity_exceeded',
    'api_key_service_unavailable', 'strategy_catalog_unavailable',
})


def failure_record(error, case_index, *, repo=None):
    """Return only public diagnostic fields, redacted by the artifact writer."""
    result = exception_record(error, phase='case_generation')
    result.update(case_index=case_index, error_type=result.pop('type'), error_message=result.pop('message'))
    client_id = result.get('client_request_id')
    if client_id and repo is not None:
        from .request_recovery import inspect_requests
        try:
            request = inspect_requests(repo, client_id)
            if request.get('request_type') == 'case_generation':
                result['request'] = request
        except Exception:
            pass  # Unknown acceptance must remain unknown, not trigger a retry.
    return result


def blocks_generation(error):
    """Stop new slots on a shared block, without retrying the failed request."""
    return getattr(error, 'code', None) in SHARED_GENERATION_BLOCKS


# These codes reject the generated candidate, not the supplied Agent Profile.
# A new candidate is permitted even when retryable=False describes the old request.
REGENERATABLE_CANDIDATES = frozenset({
    'model_invalid_result', 'model_invalid_response', 'model_output_policy_conflict',
    'model_output_privacy_rejected', 'invalid_response',
})


def may_regenerate(failure):
    """Never replace an accepted or unknown request merely because it timed out."""
    request = failure.get('request') or {}
    if request.get('status') in {'prepared', 'queued', 'running', 'succeeded'}:
        return False
    # If a public ledger ID exists but inspection failed, its state is unknown.
    if failure.get('client_request_id') and not request:
        return False
    code = failure.get('code')
    if code in REGENERATABLE_CANDIDATES:
        return True
    return (failure.get('retryable') is True and request.get('status') == 'failed'
            and code in {'network_error', 'network_timeout', 'service_busy',
                         'rate_limited', 'upstream_unavailable', 'capacity_exceeded'})
