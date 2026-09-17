"""Explicit plugin options aligned with the pinned public Kuma SDK contract."""
from collections.abc import Mapping
import math
from urllib.parse import urlsplit

# The pinned SDK's public Backend. The host does not import the SDK to learn it.
DEFAULT_BASE_URL = 'https://defuzex.ai/api/agentdefuze'
# Hosts the SDK itself allows over plain HTTP (local integration).
_PLAIN_HTTP_HOSTS = frozenset({'localhost', '127.0.0.1', '::1', 'host.docker.internal'})


def backend_url(environ) -> str:
    """Return the KUMA Backend the containerized SDK will call, normalized.

    The SDK honours KUMA_BASE_URL. The evaluation container must receive the same
    value and its egress routes must admit exactly that Backend; otherwise an
    override is either silently ignored (the run bills the default Backend) or
    blocked as undeclared egress. Trailing slashes are dropped, as the SDK does.

    Raises:
        ValueError: The override is not an HTTP(S) URL the SDK would accept.
    """
    value = (environ.get('KUMA_BASE_URL') or '').strip() or DEFAULT_BASE_URL
    try:
        parsed = urlsplit(value)
        port = parsed.port
        valid = not (parsed.scheme not in ('https', 'http') or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or (port is not None and not 1 <= port <= 65535)
            or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value
            or any(character in parsed.hostname for character in '*?[]')
            or (parsed.scheme == 'http' and parsed.hostname not in _PLAIN_HTTP_HOSTS))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('KUMA_BASE_URL must be an HTTPS Backend URL without credentials, '
                         'query or fragment (plain HTTP only for local hosts)')
    return value.rstrip('/')

# The SDK needs a repository with its .kuma ledger on the same filesystem, and the
# host reads that ledger afterwards, so both are bind mounts. Mounting them over
# /opt/agent/agent hid everything the Agent image built there -- a virtualenv on
# PATH, installed dependencies -- so the worker fell through to another interpreter.
# The mount source is a copy of the Agent source either way, and the SDK
# fingerprints tree content rather than its path, so only the location changes.
SDK_REPOSITORY = '/opt/abb-sdk-repo'


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
