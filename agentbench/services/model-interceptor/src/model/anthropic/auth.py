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
        incoming = headers.get("x-api-key", "")  # type: ignore[attr-defined]
        if not hmac.compare_digest(incoming, temporary_token):
            raise InterceptorAuthenticationError("Invalid per-run model token")
        headers.pop("x-api-key", None)  # type: ignore[attr-defined]
        headers["authorization"] = f"Bearer {upstream_secret}"  # type: ignore[index]


ANTHROPIC_API_KEY_AUTH = AnthropicApiKeyAuthentication()
