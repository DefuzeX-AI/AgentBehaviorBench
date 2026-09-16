"""Bounded OpenRouter structured-output requests with sanitized failures."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from agentbench.runtime.interception.providers import OpenRouterProvider

from .settings import ASSETS, BuildSettings
from .http_errors import describe_http_error
from .request_schema import build_request_schema
from ..common.errors import BuildError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the bearer credential to a redirect target.
        return None


class OpenRouterClient:
    def __init__(self, settings: BuildSettings, environ: Mapping[str, str], *, model=None):
        chosen = model or settings.model or environ.get("OPENROUTER_BUILD_MODEL")
        self.target = OpenRouterProvider(model=chosen).resolve(environ)
        parsed = urlsplit(self.target.base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise BuildError("OpenRouter base URL must not include credentials, query or fragment")
        self.key = environ.get(self.target.credential_env, "").strip()
        if not self.key:
            raise BuildError("OPENROUTER_API_KEY is required for -b")
        self.settings = settings
        self._error_environ = dict(environ)
        self.opener = build_opener(_NoRedirect())

    def generate(self, payload: dict, *, prompt: str, schema: dict) -> dict:
        """Return one structured stage response using its supplied prompt/schema.

        payload contains sanitized source evidence and an SDK contract. This makes
        a paid model request; no Agent code or Docker build is executed here.
        """
        # The caller retains the full schema for validation and repair feedback.
        schema = build_request_schema(schema)
        paths = [item["path"] for item in payload.get("context", {}).get("files", [])]
        if paths:
            schema["properties"]["evidence"]["items"]["enum"] = paths
        body = {"model": self.target.model, "max_tokens": self.settings.max_output_tokens,
                "messages": [
                    {"role": "system", "content": (ASSETS / "system.md").read_text() + "\n\n" + prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                "provider": {"require_parameters": True},
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "agent_environment", "strict": True, "schema": schema}}}
        request = Request(self.target.base_url + "/chat/completions",
                          data=json.dumps(body).encode(), method="POST", headers={
                              **self.target.headers, "Content-Type": "application/json",
                              "Authorization": f"Bearer {self.key}"})
        for attempt in range(self.settings.retries + 1):
            try:
                with self.opener.open(request, timeout=self.settings.timeout_seconds) as response:
                    raw = response.read(self.settings.max_response_bytes + 1)
                return self._decode(raw)
            except HTTPError as exc:
                retry = exc.code == 429 or 500 <= exc.code <= 599
                try:
                    error = describe_http_error(exc, environ=self._error_environ,
                                                api_key=self.key, max_bytes=self.settings.max_response_bytes)
                finally:
                    exc.close()
            except (URLError, TimeoutError, ConnectionError):
                retry, error = True, "OpenRouter connection failed or timed out"
            if not retry or attempt == self.settings.retries:
                raise BuildError(error + "; earlier completed files remain saved") from None
            time.sleep(min(2 ** attempt, 8))
        raise AssertionError("unreachable")

    def _decode(self, raw: bytes) -> dict:
        if len(raw) > self.settings.max_response_bytes:
            raise BuildError("OpenRouter response exceeds max_response_bytes")
        try:
            response = json.loads(raw)
            choice = response["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise BuildError("OpenRouter did not finish the configuration; check output token budget")
            result = json.loads(choice["message"]["content"])
            if not isinstance(result, dict):
                raise ValueError
            return result
        except BuildError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError):
            raise BuildError("OpenRouter returned an invalid structured configuration") from None
