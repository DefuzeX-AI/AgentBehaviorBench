"""Authenticate shared-model metadata without forwarding the proxy token."""
from urllib.parse import urlsplit

from ..error import InterceptorAuthenticationError


def authorize_shared_metadata(request, config, authentication):
    credential = next((c for c in config.credentials if c.credential_id == 'shared'), None)
    if credential is None:
        return
    target = config.target
    if target is None:
        raise InterceptorAuthenticationError('Shared metadata requires one model target')
    parsed = urlsplit(target.base_url)
    if (request.scheme != parsed.scheme or request.pretty_host.rstrip('.').lower() != parsed.hostname
            or request.port != (parsed.port or 443) or request.method != 'GET'
            or request.path != parsed.path.rstrip('/') + '/models'):
        raise InterceptorAuthenticationError('Shared metadata must use the selected model catalog endpoint')
    candidate = request.copy()
    authentication[credential.auth_plugin].authorize(
        candidate.headers, temporary_token=credential.token,
        upstream_secret=target.secret or credential.secret)
    request.headers = candidate.headers
