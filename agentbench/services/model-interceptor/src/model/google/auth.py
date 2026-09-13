"""Google source API key authentication, including query credentials."""
import hmac
from defuzex_model_interceptor.error import InterceptorAuthenticationError


class GoogleApiKeyAuthentication:
    name = "google-api-key"

    def authorize_request(self, request, *, temporary_token, upstream_secret):
        keys = request.query.get_all("key")
        header = request.headers.get("x-goog-api-key")
        if len(keys) > 1 or (keys and header and keys[0] != header):
            raise InterceptorAuthenticationError("Ambiguous Google API key")
        if keys:
            request.headers["x-goog-api-key"] = keys[0]
            del request.query["key"]
        self.authorize(request.headers, temporary_token=temporary_token, upstream_secret=upstream_secret)

    def authorize(self, headers, *, temporary_token, upstream_secret):
        if not hmac.compare_digest(headers.get("x-goog-api-key", ""), temporary_token):
            raise InterceptorAuthenticationError("Invalid per-run Google token")
        headers.pop("x-goog-api-key", None)
        headers["authorization"] = f"Bearer {upstream_secret}"


GOOGLE_API_KEY_AUTH = GoogleApiKeyAuthentication()
