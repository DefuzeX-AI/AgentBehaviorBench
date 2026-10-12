"""Classify the native exception, never an unrelated last network event."""
import math
import re

CONNECTION_ERRORS = frozenset({'ConnectionError', 'ConnectTimeout', 'ReadTimeout',
    'ConnectError', 'ReadError', 'RemoteProtocolError', 'APIConnectionError', 'APITimeoutError',
    'OpenAIConnectionError', 'AnthropicConnectionError', 'OpenAITimeoutError'})


def dependency_failure(native):
    if not native:
        return None
    kind = native.get('error_type')
    code = native.get('error_code')
    message = str(native.get('error') or '').lower()
    try:
        status = int(native.get('http_status') or 0)
    except (TypeError, ValueError):
        status = 0
    if not status:
        matched = re.search(r'(?:error code[: ]+|http[: ]+)(429|432|502|503|504)\b', message)
        status = int(matched[1]) if matched else 0
    if status == 432 or code == 'quota_exhausted' or any(text in message for text in (
            'quota exhausted', 'insufficient_quota', 'exceeds your plan', 'usage limit', 'payment required')):
        reason, automatic = 'quota_exhausted', False
    elif status in (401, 403) or code in ('invalid_api_key', 'forbidden'):
        reason, automatic = 'dependency_configuration', False
    elif status == 429 or kind == 'RateLimitError' or code == 'rate_limited':
        reason, automatic = 'rate_limited', True
    elif status in (502, 503, 504) or kind in CONNECTION_ERRORS or 'selected model provider timed out' in message:
        reason, automatic = 'dependency_unavailable', True
    else:
        return None
    try:
        delay = float(native.get('retry_after') or 60)
    except (TypeError, ValueError):
        from email.utils import parsedate_to_datetime
        import time
        try:
            delay = max(0, parsedate_to_datetime(str(native.get('retry_after'))).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            delay = 60
    if not math.isfinite(delay) or delay < 0:
        delay = 60
    return {'reason': reason, 'automatic': automatic and delay <= 3600, 'retry_after': delay,
            'host': native.get('dependency_host'), 'input_id': native.get('input_id')}
