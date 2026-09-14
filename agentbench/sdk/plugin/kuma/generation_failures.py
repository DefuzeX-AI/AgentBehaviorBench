"""Stable generation diagnostics; never infer retry permission from a message."""

# Codes from the pinned SDK's public error mapping. A credential/service-wide
# block pauses remaining slots; an ordinary Case rejection affects its own slot.
SHARED_GENERATION_BLOCKS = frozenset({
    'invalid_api_key', 'forbidden', 'strategy_group_forbidden', 'quota_exhausted',
    'rate_limited', 'service_busy', 'upstream_unavailable', 'capacity_exceeded',
    'api_key_service_unavailable', 'strategy_catalog_unavailable',
})


def failure_record(error, case_index, *, repo=None):
    """Return only public diagnostic fields, redacted by the artifact writer."""
    result = {
        'case_index': case_index, 'phase': 'case_generation',
        'error_type': type(error).__name__, 'error_message': str(error),
        **{key: getattr(error, key, None) for key in (
            'code', 'retryable', 'client_request_id', 'request_id')},
    }
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
