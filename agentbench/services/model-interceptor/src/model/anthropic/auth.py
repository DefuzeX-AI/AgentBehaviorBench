"""Anthropic source API key authentication."""
import hmac
from defuzex_model_interceptor.error import InterceptorAuthenticationError


class AnthropicApiKeyAuthentication:
    name = "anthropic-api-key"

    def authorize(
        self,
        headers: object,
        *,
        temporary_token: str,
        upstream_secret: str,
    ) -> None:
        # SDKs use either Anthropic's API-key header or Bearer authentication.
        # If both are supplied, both must identify this run; never accept a
        # matching secondary header alongside an unrelated credential.
        incoming = []
        if headers.get("x-api-key"):
            incoming.append(headers.get("x-api-key"))
        authorization = headers.get("authorization")
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer":
                raise InterceptorAuthenticationError("Invalid per-run model token")
            incoming.append(token)
        if not incoming or not all(hmac.compare_digest(value, temporary_token) for value in incoming):
            raise InterceptorAuthenticationError("Invalid per-run model token")
        headers.pop("x-api-key", None)  # type: ignore[attr-defined]
        headers["authorization"] = f"Bearer {upstream_secret}"  # type: ignore[index]


ANTHROPIC_API_KEY_AUTH = AnthropicApiKeyAuthentication()
