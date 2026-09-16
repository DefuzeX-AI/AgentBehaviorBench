"""Explicit plugin options aligned with the pinned public Kuma SDK contract."""
from collections.abc import Mapping
import math


def request_options(value=None):
    """Validate explicit HTTP options; omitted keys retain official SDK defaults.

    Args:
        value: Optional mapping of timeout, operation_wait_timeout and max_retries.
            Timeouts are seconds; these do not change the container deadline.
    Returns:
        A new JSON-safe mapping for create_run or resume_request.
    Raises:
        ValueError: On unknown keys or values outside the pinned 0.2.7 contract.
    """
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError('sdk_request_options must be a mapping')
    result = dict(value)
    unknown = set(result) - {'timeout', 'operation_wait_timeout', 'max_retries'}
    if unknown:
        raise ValueError(f'Unknown SDK request options: {sorted(unknown)}')
    for key, item in result.items():
        if key == 'max_retries':
            if type(item) is not int or not 0 <= item <= 5:
                raise ValueError('SDK max_retries must be an integer from 0 to 5')
        elif isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or item <= 0:
            raise ValueError(f'SDK {key} must be finite and positive')
    return result


def api_key(environ):
    """Return (credential, variable name), preferring KUMA over the BBA alias."""
    for name in ('KUMA_API_KEY', 'DEFUZEX_API_KEY'):
        value = environ.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip(), name
    raise ValueError('KUMA_API_KEY or DEFUZEX_API_KEY is required')
