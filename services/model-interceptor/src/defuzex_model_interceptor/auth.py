"""Built-in upstream credential adapters."""

from __future__ import annotations

import hmac


class InterceptorAuthenticationError(PermissionError):
    pass


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


class AnthropicApiKeyAuthentication:
    name = "anthropic-api-key"

    def authorize(
        self,
        headers: object,
        *,
        temporary_token: str,
        upstream_secret: str,
    ) -> None:
        incoming = headers.get("x-api-key", "")  # type: ignore[attr-defined]
        if not hmac.compare_digest(incoming, temporary_token):
            raise InterceptorAuthenticationError("Invalid per-run model token")
        headers.pop("x-api-key", None)  # type: ignore[attr-defined]
        headers["authorization"] = f"Bearer {upstream_secret}"  # type: ignore[index]


BEARER_TOKEN_AUTH = BearerTokenAuthentication()
ANTHROPIC_API_KEY_AUTH = AnthropicApiKeyAuthentication()


class GoogleApiKeyAuthentication:
    name = "google-api-key"

    def authorize(self, headers, *, temporary_token, upstream_secret):
        if not hmac.compare_digest(headers.get("x-goog-api-key", ""), temporary_token):
            raise InterceptorAuthenticationError("Invalid per-run Google token")
        headers.pop("x-goog-api-key", None)
        headers["authorization"] = f"Bearer {upstream_secret}"


GOOGLE_API_KEY_AUTH = GoogleApiKeyAuthentication()
