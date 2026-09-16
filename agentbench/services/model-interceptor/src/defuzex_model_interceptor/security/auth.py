"""Shared authentication mechanisms."""
import hmac
from ..error import InterceptorAuthenticationError


class BearerTokenAuthentication:
    name = "bearer-token"

    def authorize(
        self,
        headers: object,
        *,
        temporary_token: str,
        upstream_secret: str,
    ) -> None:
        incoming = headers.get("authorization", "")  # type: ignore[attr-defined]
        expected = f"Bearer {temporary_token}"
        if not hmac.compare_digest(incoming, expected):
            raise InterceptorAuthenticationError("Invalid per-run model token")
        headers["authorization"] = f"Bearer {upstream_secret}"  # type: ignore[index]


BEARER_TOKEN_AUTH = BearerTokenAuthentication()


class NetworkIsolatedAuthentication:
    """For declared local protocols without API keys, e.g. Ollama.

    Only safe behind the per-Agent private network namespace. Never expose this
    proxy as a public shared gateway. This authentication mode must be explicitly
    configured, including when a wire adapter recognizes the request itself.
    """
    name = "network-isolated"

    def authorize(self, headers, *, temporary_token, upstream_secret):
        headers["authorization"] = f"Bearer {upstream_secret}"
